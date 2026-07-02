// 全局登录态：挂载时预载 token → 拉 /auth/me 校验；未登录自动跳 /login。
// 提供 useAuth() 给页面读取当前用户与登录/登出动作。
// 对齐 frontend/components/AuthProvider.tsx，差异：
//   - 双 token 走 expo-secure-store（异步，需 loadTokens 预载）
//   - 路由守卫用 expo-router 的 useSegments/router，替代 next/navigation
//   - 注册 onUnauthorized 回调，让 api.ts 在 refresh 失败时能触发跳登录

import { createContext, useContext, useEffect, useState } from "react";
import { router, useSegments } from "expo-router";

import {
  apiGet,
  apiPost,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  loadTokens,
  setOnUnauthorized,
  setTokens,
} from "@/lib/api";
import type { User } from "@/lib/types";

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const segments = useSegments();

  // 首次挂载：预载 token → 有则拉 /auth/me 校验，无则结束（由下方守卫跳登录）
  useEffect(() => {
    let alive = true;
    async function bootstrap() {
      await loadTokens();
      if (!getAccessToken()) {
        if (alive) setLoading(false);
        return;
      }
      try {
        const me = await apiGet<User>("/auth/me");
        if (alive) setUser(me);
      } catch {
        // access 失效且 refresh 也失败时 api.ts 已清 token；这里兜底再清一次
        await clearTokens();
      } finally {
        if (alive) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      alive = false;
    };
  }, []);

  // 注册 401 回调：refresh 失败时清登录态，交由下方守卫跳登录。
  // 仅在已加载后挂入，避免 bootstrap 期间重复触发。
  useEffect(() => {
    if (loading) return;
    setOnUnauthorized(() => {
      setUser(null);
    });
    return () => setOnUnauthorized(null);
  }, [loading]);

  // 守卫：加载完成后，未登录且不在登录页 → 跳登录
  useEffect(() => {
    if (loading) return;
    const inLogin = segments[0] === "login";
    if (!user && !inLogin) {
      router.replace("/login");
    }
    if (user && inLogin) {
      router.replace("/");
    }
  }, [loading, user, segments]);

  async function login(identifier: string, password: string) {
    const resp = await apiPost<LoginResponse>("/auth/login", {
      identifier,
      password,
      client: "mobile",
    });
    if (!resp.access_token || !resp.refresh_token) {
      throw new Error("移动端登录未返回 token");
    }
    await setTokens(resp.access_token, resp.refresh_token);
    setUser(resp.user);
    router.replace("/");
  }

  async function logout() {
    // 先通知后端撤销 token（refresh 撤销 + access 拉黑），失败也不影响前端登出
    const refresh = getRefreshToken();
    try {
      if (refresh) {
        await apiPost("/auth/logout", { refresh_token: refresh });
      }
    } catch {
      /* 后端登出失败不阻塞：继续清本地 token */
    }
    await clearTokens();
    setUser(null);
    router.replace("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
