"use client";

// 外壳：登录页全屏无侧栏；其余页面在已登录后渲染侧栏 + 内容。
// 与 AuthProvider 配合，未登录时由 Provider 负责跳转，这里只控制布局/占位。

import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import { useAuth } from "@/components/AuthProvider";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading } = useAuth();

  // 登录页：全屏，不套侧栏
  if (pathname === "/login") {
    return <main className="h-screen overflow-y-auto">{children}</main>;
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted2">
        加载中…
      </div>
    );
  }

  // 未登录：Provider 正在跳转 /login，这里先不渲染内容
  if (!user) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
