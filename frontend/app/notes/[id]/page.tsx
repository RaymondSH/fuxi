"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import TypeBadge from "@/components/TypeBadge";
import { useAuth } from "@/components/AuthProvider";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import type { EntityCat, GeneratedQaItem, Note } from "@/lib/types";

// 实体类别 → 着色 class（静态字符串，便于 Tailwind 提取）
const CAT_CLASS: Record<EntityCat, string> = {
  concept: "text-cat-concept bg-cat-concept-soft",
  product: "text-cat-product bg-cat-product-soft",
  company: "text-cat-company bg-cat-company-soft",
};

export default function NotePage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [note, setNote] = useState<Note | null>(null);
  const [qaItems, setQaItems] = useState<GeneratedQaItem[]>([]);
  const [qaGenerating, setQaGenerating] = useState(false);
  const [qaMsg, setQaMsg] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [versions, setVersions] = useState<{ version: number; change_type: string; created_at: string }[]>([]);

  const loadQa = useCallback(async () => {
    try {
      const data = await apiGet<{ items: GeneratedQaItem[] }>(`/notes/${id}/qa`);
      setQaItems(data.items);
    } catch {
      // 静默：没有问答对时列表为空即可
    }
  }, [id]);

  useEffect(() => {
    apiGet<Note>(`/notes/${id}`)
      .then((data) => {
        setNote(data); setDraftTitle(data.title); setDraftContent(data.original.join("\n\n"));
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载失败"),
      );
    loadQa();
  }, [id, loadQa]);

  async function generateQa() {
    setQaGenerating(true);
    setQaMsg("");
    try {
      await apiPost(`/notes/${id}/generate-qa`);
      setQaMsg("已提交生成，稍后刷新查看结果…");
      // 3 秒后拉一次，生成是后台跑的，可能还没完
      setTimeout(loadQa, 3000);
    } catch (err) {
      setQaMsg(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setQaGenerating(false);
    }
  }

  async function saveEdit() {
    await apiPatch(`/notes/${id}`, { title: draftTitle, content: draftContent });
    setNote((prev) => prev ? { ...prev, title: draftTitle, original: draftContent.split("\n\n") } : prev);
    setEditing(false);
  }

  async function loadVersions() {
    const data = await apiGet<{ items: typeof versions }>(`/notes/${id}/versions`);
    setVersions(data.items);
  }

  async function restoreVersion(version: number) {
    await apiPost(`/notes/${id}/versions/${version}/restore`);
    window.location.reload();
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <Link href="/search" className="text-sm text-accent hover:underline">
          ← 返回检索
        </Link>
        <p className="mt-8 text-center text-sm text-[#B23C3C]">{error}</p>
      </div>
    );
  }

  if (!note) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10 text-sm text-muted2">
        加载中…
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-3xl px-8 py-10">
      <Link href="/search" className="text-sm text-accent hover:underline">
        ← 返回检索
      </Link>

      {/* 标题区 */}
      <header className="mt-4">
        <div className="mb-2 flex items-center gap-2">
          <TypeBadge type={note.type} />
          {note.url && (
            <a
              href={note.url}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-[11px] text-muted2 hover:text-accent"
            >
              原文 ↗
            </a>
          )}
        </div>
        <h1 className="font-serif text-2xl font-semibold leading-snug text-ink">
          {note.title}
        </h1>
        {note.can_edit && (
          <div className="mt-3 flex gap-2">
            <button onClick={() => setEditing(!editing)} className="text-xs text-accent">编辑笔记</button>
            <button onClick={loadVersions} className="text-xs text-muted">版本历史</button>
            {note.url?.startsWith("http") && <button onClick={() => apiPost(`/notes/${id}/refresh`)} className="text-xs text-muted">刷新来源</button>}
            {note.can_delete && note.url?.startsWith("http") && (
              <select value={note.refresh_policy || "manual"} onChange={async (e) => {
                const refresh_policy = e.target.value as "manual" | "daily" | "weekly";
                await apiPatch(`/notes/${id}/source`, { refresh_policy });
                setNote({ ...note, refresh_policy });
              }} className="border-0 bg-transparent text-xs text-muted">
                <option value="manual">手动刷新</option><option value="daily">每日刷新</option><option value="weekly">每周刷新</option>
              </select>
            )}
            {note.can_delete && <button onClick={async () => {
              await apiDelete(`/notes/${id}`); window.location.href = "/trash";
            }} className="text-xs text-[#B23C3C]">移到回收站</button>}
          </div>
        )}
        <button onClick={() => apiPost("/subscriptions", {
          space_id: note.space_id, scope_type: "note", scope_value: note.id,
        })} className="mt-3 text-xs text-muted">订阅此笔记</button>
        <div className="mt-1.5 flex items-center gap-2 text-xs text-muted2">
          {note.source && <span>{note.source}</span>}
          {note.date && <span>· {note.date}</span>}
        </div>
        {note.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {note.tags.map((t) => (
              <span
                key={t}
                className="rounded bg-panel px-1.5 py-0.5 text-[11px] text-muted2"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </header>

      {editing && (
        <section className="mt-5 rounded-xl border border-line bg-panel p-4">
          <input value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)}
            className="mb-3 w-full rounded border border-line bg-white px-3 py-2 text-sm" />
          <textarea value={draftContent} onChange={(e) => setDraftContent(e.target.value)}
            rows={14} className="w-full rounded border border-line bg-white px-3 py-2 text-sm leading-6" />
          <div className="mt-3 flex gap-2">
            <button onClick={saveEdit} className="rounded bg-brand px-3 py-1.5 text-xs text-cream">保存并重建索引</button>
            <button onClick={() => setEditing(false)} className="text-xs text-muted">取消</button>
          </div>
        </section>
      )}

      {versions.length > 0 && (
        <section className="mt-5 rounded-xl border border-line bg-white p-4">
          <h2 className="mb-2 font-mono text-xs text-muted2">版本历史</h2>
          {versions.map((v) => (
            <div key={v.version} className="flex items-center justify-between border-t border-line py-2 text-xs">
              <span>v{v.version} · {v.change_type} · {new Date(v.created_at).toLocaleString()}</span>
              {note.can_edit && <button onClick={() => restoreVersion(v.version)} className="text-accent">恢复</button>}
            </div>
          ))}
        </section>
      )}

      {/* 摘要 */}
      {note.summary && (
        <div className="mt-6 rounded-lg border-l-2 border-brand bg-panel px-4 py-3">
          <p className="text-sm leading-relaxed text-ink">{note.summary}</p>
        </div>
      )}

      {/* 要点 */}
      {note.keypoints.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-muted2">
            要点
          </h2>
          <ul className="flex flex-col gap-1.5">
            {note.keypoints.map((k, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink">
                <span className="text-brand">·</span>
                <span>{k}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 实体 */}
      {note.entities.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-muted2">
            实体
          </h2>
          <div className="flex flex-wrap gap-1.5">
            {note.entities.map((e) => (
              <Link
                key={e.id}
                href={`/graph?entity=${e.id}`}
                className={`rounded-full px-2.5 py-1 text-xs ${CAT_CLASS[e.cat]} transition-opacity hover:opacity-80`}
              >
                {e.name}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* 正文 */}
      {note.original.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-muted2">
            正文
          </h2>
          <div className="flex flex-col gap-3">
            {note.original.map((p, i) => (
              <p key={i} className="text-[15px] leading-7 text-ink">
                {p}
              </p>
            ))}
          </div>
        </section>
      )}

      {/* 文档→Q&A（回灌检索用） */}
      <section className="mt-8">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted2">
            问答 · {qaItems.length}
          </h2>
          {user?.role === "admin" && (
            <button
              onClick={generateQa}
              disabled={qaGenerating}
              className="rounded-lg border border-line bg-white px-3 py-1 text-xs text-muted transition-colors hover:border-brand hover:text-accent disabled:opacity-40"
            >
              {qaGenerating ? "生成中…" : qaItems.length > 0 ? "重新生成" : "生成问答"}
            </button>
          )}
        </div>
        {qaMsg && <p className="mb-2 text-xs text-accent">{qaMsg}</p>}
        {qaItems.length > 0 ? (
          <div className="flex flex-col gap-2">
            {qaItems.map((qa, i) => (
              <div
                key={i}
                className="rounded-lg border border-line bg-panel px-4 py-3"
              >
                <p className="text-sm font-medium text-ink">Q：{qa.question}</p>
                <p className="mt-1 text-sm leading-relaxed text-muted">
                  A：{qa.answer}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted2">
            暂无问答对。{user?.role === "admin" ? "可点「生成问答」针对本篇生成。" : ""}
          </p>
        )}
      </section>
    </article>
  );
}
