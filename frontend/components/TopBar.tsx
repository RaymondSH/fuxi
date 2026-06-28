"use client";

// 全局顶栏：检索全部知识（⌘K 唤起）+ 新建入库（仅管理员）。
// 检索框回车跳到 /search?q=...，由检索页读取并自动执行。

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function TopBar() {
  const router = useRouter();
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K 聚焦检索框
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const v = q.trim();
    if (!v) return;
    router.push(`/search?q=${encodeURIComponent(v)}`);
  }

  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b border-line bg-cream/60 px-6 backdrop-blur">
      <form onSubmit={submit} className="relative flex-1 max-w-2xl">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted2">
          {/* 放大镜 */}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </span>
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="检索全部知识…"
          className="w-full rounded-lg border border-line bg-white py-2 pl-9 pr-14 text-sm text-ink outline-none placeholder:text-muted2 focus:border-brand"
        />
        <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-line bg-panel px-1.5 py-0.5 font-mono text-[10px] text-muted2">
          ⌘K
        </kbd>
      </form>

      <div className="ml-auto flex items-center gap-3">
        {user?.role === "admin" && (
          <Link
            href="/admin/ingest"
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-cream transition-opacity hover:opacity-90"
          >
            <span className="text-base leading-none">＋</span>
            新建入库
          </Link>
        )}
      </div>
    </header>
  );
}
