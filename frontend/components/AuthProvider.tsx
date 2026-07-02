"use client";

// 全局登录态：Web token 由后端写入 httpOnly Cookie，前端 JS 不持久化凭证。
// 挂载时直接拉 /auth/me；401 时 api.ts 用 refresh Cookie 自动续期。
// 提供 useAuth() 给页面/侧栏读取当前用户与登录/登出动作。

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";
import type { User } from "@/lib/types";

interface LoginResponse {
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
  const router = useRouter();
  const pathname = usePathname();

  // 首次挂载：Cookie 不可由 JS 读取，直接请求 /auth/me。
  useEffect(() => {
    let alive = true;
    async function bootstrap() {
      try {
        const me = await apiGet<User>("/auth/me");
        if (alive) setUser(me);
      } catch {
        // 未登录或 refresh 已失效。
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
    const resp = await apiPost<LoginResponse>("/auth/login", { identifier, password, client: "web" });
    setUser(resp.user);
    router.replace("/search");
  }

  async function logout() {
    // 后端从 Cookie 取双 token 并撤销；失败也不阻塞前端退出。
    try {
      await apiPost("/auth/logout", {});
    } catch {
      /* 后端登出失败不阻塞 UI */
    }
    setUser(null);
    router.replace("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
