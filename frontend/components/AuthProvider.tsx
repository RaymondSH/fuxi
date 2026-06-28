"use client";

// 全局登录态：挂载时用 token 拉 /auth/me；未登录自动跳 /login。
// 提供 useAuth() 给页面/侧栏读取当前用户与登录/登出动作。

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiGet, apiPost, clearToken, getToken, setToken } from "@/lib/api";
import type { User } from "@/lib/types";

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => void;
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
  const router = useRouter();
  const pathname = usePathname();

  // 首次挂载：有 token 就验，没 token 直接结束（由下方守卫跳登录）
  useEffect(() => {
    let alive = true;
    async function bootstrap() {
      if (!getToken()) {
        if (alive) setLoading(false);
        return;
      }
      try {
        const me = await apiGet<User>("/auth/me");
        if (alive) setUser(me);
      } catch {
        clearToken();
      } finally {
        if (alive) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      alive = false;
    };
  }, []);

  // 守卫：加载完成后，未登录且不在登录页 → 跳登录
  useEffect(() => {
    if (!loading && !user && pathname !== "/login") {
      router.replace("/login");
    }
  }, [loading, user, pathname, router]);

  async function login(identifier: string, password: string) {
    const resp = await apiPost<LoginResponse>("/auth/login", { identifier, password });
    setToken(resp.access_token);
    setUser(resp.user);
    router.replace("/search");
  }

  function logout() {
    clearToken();
    setUser(null);
    router.replace("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
