"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { href: string; label: string; en: string }[] = [
  { href: "/search", label: "检索", en: "Search" },
  { href: "/qa", label: "问答", en: "Ask" },
  { href: "/graph", label: "知识图谱", en: "Graph" },
  { href: "/wiki", label: "主题页", en: "Wiki" },
  { href: "/ingest", label: "入库", en: "Ingest" },
  { href: "/history", label: "历史", en: "History" },
];

export default function Sidebar() {
  const pathname = usePathname();

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
            知识库
          </div>
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex flex-col gap-1 px-3">
        {NAV.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
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
        })}
      </nav>

      <div className="mt-auto px-6 py-4 font-mono text-[10px] text-muted2">
        FUXI · v0.1
      </div>
    </aside>
  );
}
