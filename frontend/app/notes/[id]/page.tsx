"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import TypeBadge from "@/components/TypeBadge";
import { apiGet, ApiError } from "@/lib/api";
import type { EntityCat, Note } from "@/lib/types";

// 实体类别 → 着色 class（静态字符串，便于 Tailwind 提取）
const CAT_CLASS: Record<EntityCat, string> = {
  concept: "text-cat-concept bg-cat-concept-soft",
  product: "text-cat-product bg-cat-product-soft",
  company: "text-cat-company bg-cat-company-soft",
};

export default function NotePage() {
  const { id } = useParams<{ id: string }>();
  const [note, setNote] = useState<Note | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Note>(`/notes/${id}`)
      .then(setNote)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载失败"),
      );
  }, [id]);

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
                href="/graph"
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
    </article>
  );
}
