"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { WikiSummary } from "@/lib/types";

export default function WikiListPage() {
  const [items, setItems] = useState<WikiSummary[]>([]);

  useEffect(() => {
    apiGet<{ items: WikiSummary[] }>("/wiki")
      .then((d) => setItems(d.items))
      .catch(() => setItems([]));
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">主题页</h1>
        <p className="mt-1 text-sm text-muted">
          多篇笔记编译出的综合判断，标注观点矛盾。
        </p>
      </header>

      {items.length === 0 ? (
        <p className="rounded-lg border border-line bg-panel px-4 py-8 text-center text-sm text-muted2">
          还没有编译好的主题页
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((w) => (
            <li key={w.slug}>
              <Link
                href={`/wiki/${w.slug}`}
                className="block rounded-lg border border-line bg-white px-4 py-3 transition-colors hover:border-brand"
              >
                <div className="font-serif text-lg font-medium text-ink">
                  {w.title}
                </div>
                <div className="mt-1 font-mono text-xs text-muted2">
                  {w.source_count} 篇来源
                  {w.updated && ` · 更新于 ${w.updated}`}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
