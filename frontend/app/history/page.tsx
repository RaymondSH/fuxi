"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiPut } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

interface SearchHistoryItem {
  id: string;
  q: string;
  mode: string;
  hits: number;
  relative: string;
}

interface QaHistoryItem {
  id: string;
  question: string;
  answer_preview: string;
  source_count: number;
  relative: string;
}

export default function HistoryPage() {
  const { user } = useAuth();
  const [searches, setSearches] = useState<SearchHistoryItem[]>([]);
  const [qas, setQas] = useState<QaHistoryItem[]>([]);
  const [allUsers, setAllUsers] = useState(false); // 管理员看全部

  const isAdmin = user?.role === "admin";

  useEffect(() => {
    const scope = isAdmin && allUsers ? "?scope=all" : "";
    apiGet<{ items: SearchHistoryItem[] }>(`/search/history${scope}`)
      .then((d) => setSearches(d.items))
      .catch(() => {});
    apiGet<{ items: QaHistoryItem[] }>(`/qa/history${scope}`)
      .then((d) => setQas(d.items))
      .catch(() => {});
  }, [isAdmin, allUsers]);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-6 flex items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-ink">历史</h1>
          <p className="mt-1 text-sm text-muted">
            {isAdmin && allUsers ? "全部用户的检索与问答记录。" : "你的检索与问答记录。"}
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => setAllUsers((v) => !v)}
            className="shrink-0 rounded-lg border border-line bg-white px-3 py-1.5 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
          >
            {allUsers ? "只看自己" : "看全部用户"}
          </button>
        )}
      </header>

      {/* 问答历史 */}
      <section className="mb-8">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
          问答历史
        </h2>
        {qas.length === 0 ? (
          <p className="text-sm text-muted2">还没有问答记录</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {qas.map((item) => (
              <li
                key={item.id}
                className="rounded-lg border border-line bg-white px-4 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="font-medium text-ink">{item.question}</span>
                  <span className="shrink-0 font-mono text-[11px] text-muted2">
                    {item.relative}
                  </span>
                </div>
                <p className="mt-1 line-clamp-1 text-sm text-muted">
                  {item.answer_preview}
                </p>
                <div className="mt-1 font-mono text-[11px] text-muted2">
                  {item.source_count} 条来源
                </div>
                {!allUsers && <div className="mt-2 flex gap-3 text-xs text-muted2">
                  <button onClick={() => apiPut(`/qa/history/${item.id}/feedback`, {rating:"up"})}>有帮助</button>
                  <button onClick={() => apiPut(`/qa/history/${item.id}/feedback`, {rating:"down"})}>没帮助</button>
                </div>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 搜索历史 */}
      <section>
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
          搜索历史
        </h2>
        {searches.length === 0 ? (
          <p className="text-sm text-muted2">还没有搜索记录</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {searches.map((item) => (
              <li key={item.id}>
                <Link
                  href="/search"
                  className="flex items-center justify-between gap-3 rounded-lg border border-line bg-white px-4 py-2.5 transition-colors hover:border-brand"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-ink">{item.q}</span>
                    <span className="rounded bg-panel px-1.5 py-0.5 font-mono text-[10px] text-muted2">
                      {item.mode}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-muted2">
                    {item.hits} 命中 · {item.relative}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
