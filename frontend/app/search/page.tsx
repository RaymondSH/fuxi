"use client";

import { useCallback, useEffect, useState } from "react";
import NoteCard from "@/components/NoteCard";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { NoteSummary, SearchMode } from "@/lib/types";

const MODES: { key: SearchMode; label: string }[] = [
  { key: "hybrid", label: "混合 Hybrid" },
  { key: "keyword", label: "关键词" },
  { key: "semantic", label: "语义" },
];

interface SearchResponse {
  query: string;
  mode: SearchMode;
  took_ms: number;
  total: number;
  results: NoteSummary[];
}

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [tags, setTags] = useState<{ name: string; count: number }[]>([]);
  const [resp, setResp] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 标签云
  useEffect(() => {
    apiGet<{ items: { name: string; count: number }[] }>("/tags")
      .then((d) => setTags(d.items))
      .catch(() => {});
  }, []);

  const runSearch = useCallback(
    async (query: string, searchMode: SearchMode, tagList: string[]) => {
      if (!query.trim()) return;
      setLoading(true);
      setError("");
      try {
        const data = await apiPost<SearchResponse>("/search", {
          q: query,
          mode: searchMode,
          tags: tagList,
          time_filter: "all",
        });
        setResp(data);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "检索失败");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  function submit(e: React.FormEvent) {
    e.preventDefault();
    runSearch(q, mode, activeTags);
  }

  function toggleTag(name: string) {
    const next = activeTags.includes(name)
      ? activeTags.filter((t) => t !== name)
      : [...activeTags, name];
    setActiveTags(next);
    if (resp) runSearch(q, mode, next); // 已有结果时即时重搜
  }

  function pickMode(m: SearchMode) {
    setMode(m);
    if (resp) runSearch(q, m, activeTags);
  }

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">检索</h1>
        <p className="mt-1 text-sm text-muted">关键词、语义、混合检索知识库。</p>
      </header>

      {/* 搜索框 */}
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索笔记…"
          className="flex-1 rounded-lg border border-line bg-white px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted2 focus:border-brand"
        />
        <button
          type="submit"
          disabled={loading || !q.trim()}
          className="rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
        >
          检索
        </button>
      </form>

      {/* 模式切换 */}
      <div className="mt-3 inline-flex rounded-lg bg-panel p-1">
        {MODES.map((m) => (
          <button
            key={m.key}
            onClick={() => pickMode(m.key)}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              mode === m.key
                ? "bg-ink font-medium text-cream"
                : "text-muted hover:text-ink"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* 标签云 */}
      {tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {tags.map((t) => {
            const on = activeTags.includes(t.name);
            return (
              <button
                key={t.name}
                onClick={() => toggleTag(t.name)}
                className={`rounded-full px-2.5 py-1 text-xs transition-colors ${
                  on ? "bg-brand text-cream" : "bg-panel text-muted hover:text-ink"
                }`}
              >
                {t.name}
                <span className="ml-1 opacity-60">{t.count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* 结果 */}
      <section className="mt-8">
        {error && <p className="text-sm text-[#B23C3C]">{error}</p>}

        {resp && !error && (
          <>
            <div className="mb-3 font-mono text-xs text-muted2">
              {resp.total} 条结果 · {resp.mode} · {resp.took_ms}ms
              {resp.mode !== mode && "（语义不可用，已降级）"}
            </div>
            {resp.results.length === 0 ? (
              <p className="rounded-lg border border-line bg-panel px-4 py-8 text-center text-sm text-muted2">
                没有匹配的笔记
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {resp.results.map((n) => (
                  <li key={n.id}>
                    <NoteCard note={n} />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {!resp && !error && (
          <p className="text-center text-sm text-muted2">输入关键词开始检索</p>
        )}
      </section>
    </div>
  );
}
