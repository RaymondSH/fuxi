"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import SystemStatus from "@/components/SystemStatus";
import { apiGet } from "@/lib/api";
import type { SystemStatus as SystemStatusData } from "@/lib/types";

const NAV: { href: string; label: string; en: string }[] = [
  { href: "/search", label: "检索", en: "Search" },
  { href: "/qa", label: "问答", en: "Ask" },
  { href: "/graph", label: "知识图谱", en: "Graph" },
  { href: "/wiki", label: "主题页", en: "Wiki" },
  { href: "/history", label: "历史", en: "History" },
];

// 仅管理员可见（入库等策展操作收进管理后台）
const ADMIN_NAV: { href: string; label: string; en: string }[] = [
  { href: "/admin/ingest", label: "入库", en: "Ingest" },
  { href: "/admin/users", label: "用户", en: "Users" },
  { href: "/admin/usage", label: "用量", en: "Usage" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [status, setStatus] = useState<SystemStatusData | null>(null);
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  useEffect(() => {
    apiGet<SystemStatusData>("/system/status")
      .then(setStatus)
      .catch(() => {});
  }, []);

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-panel">
      {/* 品牌 */}
      <div className="flex items-center gap-3 px-6 py-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand">
          <span className="font-serif text-xl font-semibold text-cream">复</span>
        </div>
        <div className="leading-tight">
          <div className="font-serif text-lg font-semibold text-ink">fuxi</div>
          <div className="font-mono text-[10px] tracking-widest text-muted2">
            知识库{status?.version && ` · v${status.version}`}
          </div>
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex flex-col gap-1 px-3">
        {NAV.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}

        {user?.role === "admin" && (
          <>
            <div className="mt-4 mb-1 px-3 font-mono text-[10px] uppercase tracking-widest text-muted2">
              管理
            </div>
            {ADMIN_NAV.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item.href)} />
            ))}
          </>
        )}
      </nav>

      {/* 系统情况 */}
      <div className="mt-auto border-t border-line pt-3">
        <SystemStatus data={status} />
      </div>

      {/* 当前用户 + 登出 */}
      <div className="border-t border-line px-4 py-4">
        {user && (
          <div className="mb-2">
            <div className="truncate text-sm font-medium text-ink">
              {user.display_name || user.email}
            </div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted2">
              {user.role === "admin" ? "管理员" : "成员"}
            </div>
          </div>
        )}
        <button
          onClick={logout}
          className="w-full rounded-lg border border-line bg-white px-3 py-1.5 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
        >
          退出登录
        </button>
      </div>
    </aside>
  );
}

function NavLink({
  item,
  active,
}: {
  item: { href: string; label: string; en: string };
  active: boolean;
}) {
  return (
    <Link
      href={item.href}
      className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-brand-soft font-semibold text-accent"
          : "text-muted hover:bg-cream"
      }`}
    >
      <span>{item.label}</span>
      <span className="font-mono text-[10px] uppercase tracking-wider text-muted2">
        {item.en}
      </span>
    </Link>
  );
}
