"use client";

// 空间切换器：顶栏下拉，切换「当前活动空间」。选项 = 当前用户可见空间 + 「全部空间」。
// 切换写入 SpacesProvider（持久化到 localStorage）。用于入库目标选择等。
// 仅在有多个空间时显示；单空间或加载中不渲染，避免占位噪声。

import { useEffect, useRef, useState } from "react";
import { useSpaces } from "@/components/SpacesProvider";

export default function SpaceSwitcher() {
  const { spaces, loading, activeId, activeSpace, setActiveId } = useSpaces();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 点外部收起
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // 单空间或加载中：不渲染（默认空间唯一时无需切换）
  if (loading || spaces.length <= 1) return null;

  const label = activeSpace ? activeSpace.name : "全部空间";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-sm text-muted transition-colors hover:border-brand hover:text-accent"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
        <span className="max-w-[10rem] truncate">{label}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <ul className="absolute right-0 z-30 mt-1 w-52 overflow-hidden rounded-lg border border-line bg-white py-1 shadow-lg">
          <li>
            <button
              onClick={() => {
                setActiveId("__all__");
                setOpen(false);
              }}
              className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-cream ${
                activeId === "__all__" ? "font-medium text-accent" : "text-muted"
              }`}
            >
              <span>全部空间</span>
              {activeId === "__all__" && <CheckMark />}
            </button>
          </li>
          <li className="my-1 border-t border-line" />
          {spaces.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => {
                  setActiveId(s.id);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-cream ${
                  activeId === s.id ? "font-medium text-accent" : "text-muted"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="max-w-[8rem] truncate">{s.name}</span>
                  {s.is_default && (
                    <span className="rounded bg-panel px-1 font-mono text-[9px] text-muted2">默认</span>
                  )}
                </span>
                {activeId === s.id && <CheckMark />}
              </button>
            </li>
          ))}
          <li className="my-1 border-t border-line" />
          <li>
            <a
              href="/spaces"
              className="block px-3 py-2 text-xs text-muted2 transition-colors hover:bg-cream hover:text-accent"
            >
              管理空间 →
            </a>
          </li>
        </ul>
      )}
    </div>
  );
}

function CheckMark() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}
