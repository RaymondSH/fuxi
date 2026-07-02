"use client";

// 笔记浏览页：分页列表 + 类型过滤 + 标签过滤 + 关键词模糊。
// 复用检索页的 NoteCard 卡片；分页为首例（手写上一页/下一页）。
// useSearchParams 需 Suspense 包裹（Next 16 要求）。

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import NoteCard from "@/components/NoteCard";
import { apiGet, ApiError } from "@/lib/api";
import type { NoteListResponse, NoteType } from "@/lib/types";

const TYPES: { key: NoteType | "all"; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "link", label: "链接" },
  { key: "pdf", label: "PDF" },
  { key: "word", label: "Word" },
  { key: "excel", label: "Excel" },
  { key: "image", label: "图片" },
];

const PAGE_SIZE = 20;

function NotesInner() {
  const searchParams = useSearchParams();
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [type, setType] = useState<NoteType | "all">("all");
  const [tag, setTag] = useState(searchParams.get("tag") ?? "");
  const [tags, setTags] = useState<{ name: string; count: number }[]>([]);
  const [data, setData] = useState<NoteListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 标签云（用于点选过滤）
  useEffect(() => {
    apiGet<{ items: { name: string; count: number }[] }>("/tags")
      .then((d) => setTags(d.items))
      .catch(() => {});
  }, []);

  const fetchNotes = useCallback(async (p: number) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: String(p), size: String(PAGE_SIZE) });
      if (q.trim()) params.set("q", q.trim());
      if (type !== "all") params.set("type", type);
      if (tag) params.set("tag", tag);
      const resp = await apiGet<NoteListResponse>(`/notes?${params.toString()}`);
      setData(resp);
      setPage(p);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [q, type, tag]);

  // 首次 + 过滤条件变化时回到第 1 页重新拉取
  useEffect(() => {
    fetchNotes(1);
  }, [fetchNotes]);

  function pickTag(name: string) {
    setTag((cur) => (cur === name ? "" : name));
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">笔记</h1>
        <p className="mt-1 text-sm text-muted">按类型 / 标签浏览全部知识库笔记。</p>
      </header>

      {/* 关键词 + 类型 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          fetchNotes(1);
        }}
        className="flex flex-wrap gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="按标题或摘要筛选…"
          className="min-w-0 flex-1 rounded-lg border border-line bg-white px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted2 focus:border-brand"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
        >
          筛选
        </button>
      </form>

      <div className="mt-3 inline-flex rounded-lg bg-panel p-1">
        {TYPES.map((t) => (
          <button
            key={t.key}
            onClick={() => setType(t.key)}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              type === t.key ? "bg-ink font-medium text-cream" : "text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 标签云（点选即过滤） */}
      {tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {tags.map((t) => {
            const on = tag === t.name;
            return (
              <button
                key={t.name}
                onClick={() => pickTag(t.name)}
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

      {/* 列表 */}
      <section className="mt-8">
        {error && <p className="text-sm text-[#B23C3C]">{error}</p>}

        {data && !error && (
          <>
            <div className="mb-3 font-mono text-xs text-muted2">
              共 {data.total} 篇 · 第 {data.page} / {totalPages} 页
            </div>
            {data.items.length === 0 ? (
              <p className="rounded-lg border border-line bg-panel px-4 py-8 text-center text-sm text-muted2">
                没有匹配的笔记
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.items.map((note) => (
                  <li key={note.id}>
                    <NoteCard note={note} />
                  </li>
                ))}
              </ul>
            )}

            {/* 分页 */}
            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-center gap-3">
                <button
                  onClick={() => fetchNotes(page - 1)}
                  disabled={page <= 1 || loading}
                  className="rounded-lg border border-line bg-white px-4 py-2 text-sm text-muted transition-colors hover:border-brand hover:text-accent disabled:opacity-40"
                >
                  上一页
                </button>
                <span className="font-mono text-xs text-muted2">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => fetchNotes(page + 1)}
                  disabled={page >= totalPages || loading}
                  className="rounded-lg border border-line bg-white px-4 py-2 text-sm text-muted transition-colors hover:border-brand hover:text-accent disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

export default function NotesPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-3xl px-8 py-10 text-sm text-muted2">加载中…</div>}>
      <NotesInner />
    </Suspense>
  );
}
