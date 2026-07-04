"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { canAct, useSpaces } from "@/components/SpacesProvider";
import SystemStatus from "@/components/SystemStatus";
import { apiGet } from "@/lib/api";
import type { SystemStatus as SystemStatusData } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  en: string;
}

const CORE_NAV: NavItem[] = [
  { href: "/search", label: "检索", en: "Search" },
  { href: "/notes", label: "笔记", en: "Notes" },
  { href: "/qa", label: "问答", en: "Ask" },
  { href: "/graph", label: "知识图谱", en: "Graph" },
  { href: "/wiki", label: "主题页", en: "Wiki" },
];

const COLLABORATION_NAV: NavItem[] = [
  { href: "/spaces", label: "空间", en: "Spaces" },
  { href: "/history", label: "历史", en: "History" },
  { href: "/governance", label: "知识治理", en: "Governance" },
  { href: "/connectors", label: "企业连接", en: "Connectors" },
  { href: "/notifications", label: "通知", en: "Notices" },
  { href: "/agent", label: "治理 Agent", en: "Agent" },
];

// 仅系统管理员可见。
const ADMIN_NAV: NavItem[] = [
  { href: "/admin/users", label: "用户", en: "Users" },
  { href: "/admin/tags", label: "标签治理", en: "Tags" },
  { href: "/admin/usage", label: "用量", en: "Usage" },
  { href: "/admin/mcp", label: "MCP", en: "MCP" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { spaces } = useSpaces();
  const canIngest = user?.role === "admin" || spaces.some((s) => canAct(s.my_role, "editor"));
  const [status, setStatus] = useState<SystemStatusData | null>(null);
  const [unread, setUnread] = useState(0);
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  useEffect(() => {
    apiGet<SystemStatusData>("/system/status")
      .then(setStatus)
      .catch(() => {});
    apiGet<{ unread: number }>("/notifications?unread_only=true")
      .then((x) => setUnread(x.unread)).catch(() => {});
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
      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3 pb-3">
        <NavGroup
          title="知识工作"
          items={CORE_NAV}
          isActive={isActive}
          defaultOpen
        />
        <NavGroup
          title="协作与治理"
          items={COLLABORATION_NAV.map((item) =>
            item.href === "/notifications" && unread
              ? { ...item, label: `通知 (${unread})` }
              : item
          )}
          isActive={isActive}
        />
        {canIngest && (
          <NavGroup
            title="内容管理"
            items={[
              { href: "/ingest", label: "入库", en: "Ingest" },
              { href: "/trash", label: "回收站", en: "Trash" },
            ]}
            isActive={isActive}
          />
        )}

        {user?.role === "admin" && (
          <NavGroup
            title="系统管理"
            items={ADMIN_NAV}
            isActive={isActive}
          />
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
        <Link
          href="/settings"
          className="mb-2 block w-full rounded-lg border border-line bg-white px-3 py-1.5 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
        >
          修改密码
        </Link>
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

function NavGroup({
  title,
  items,
  isActive,
  defaultOpen = false,
}: {
  title: string;
  items: NavItem[];
  isActive: (href: string) => boolean;
  defaultOpen?: boolean;
}) {
  const hasActiveItem = items.some((item) => isActive(item.href));
  const [open, setOpen] = useState(defaultOpen || hasActiveItem);

  useEffect(() => {
    if (hasActiveItem) setOpen(true);
  }, [hasActiveItem]);

  return (
    <section>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="mt-1 flex w-full items-center justify-between rounded-lg px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-muted2 transition-colors hover:bg-cream hover:text-muted"
      >
        <span>{title}</span>
        <span className={`text-sm transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>
      {open && (
        <div className="flex flex-col gap-1">
          {items.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} />
          ))}
        </div>
      )}
    </section>
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
