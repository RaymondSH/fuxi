"use client";

// 管理后台守卫：仅管理员可进；非管理员显示无权限提示。
// 登录态由根布局的 AuthProvider 保证，这里只额外卡 role。

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted2">
        加载中…
      </div>
    );
  }

  if (!user || user.role !== "admin") {
    return (
      <div className="mx-auto max-w-md px-8 py-20 text-center">
        <h1 className="font-serif text-xl font-semibold text-ink">需要管理员权限</h1>
        <p className="mt-2 text-sm text-muted">此页面仅管理员可访问。</p>
        <Link
          href="/search"
          className="mt-4 inline-block rounded-lg bg-ink px-4 py-2 text-sm text-cream"
        >
          返回检索
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
