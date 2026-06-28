"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import TypeBadge from "@/components/TypeBadge";
import { apiGet, ApiError } from "@/lib/api";
import type { WikiDetail } from "@/lib/types";

export default function WikiDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [wiki, setWiki] = useState<WikiDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<WikiDetail>(`/wiki/${slug}`)
      .then(setWiki)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载失败"),
      );
  }, [slug]);

  // note id -> 来源序号（1 起），用于正文里的 [n] 角标
  const sourceIndex = useMemo(() => {
    const m = new Map<string, number>();
    wiki?.source_ids.forEach((id, i) => m.set(id, i + 1));
    return m;
  }, [wiki]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <Link href="/wiki" className="text-sm text-accent hover:underline">
          ← 返回主题页
        </Link>
        <p className="mt-8 text-center text-sm text-[#B23C3C]">{error}</p>
      </div>
    );
  }
  if (!wiki) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10 text-sm text-muted2">
        加载中…
      </div>
    );
  }

  const Cite = ({ id }: { id: string }) => {
    const n = sourceIndex.get(id);
    return (
      <Link
        href={`/notes/${id}`}
        className="ml-0.5 align-super text-[10px] text-accent hover:underline"
      >
        [{n ?? "·"}]
      </Link>
    );
  };

  return (
    <article className="mx-auto max-w-3xl px-8 py-10">
      <Link href="/wiki" className="text-sm text-accent hover:underline">
        ← 返回主题页
      </Link>

      <header className="mt-4">
        <h1 className="font-serif text-3xl font-semibold text-ink">
          {wiki.title}
        </h1>
        <div className="mt-1.5 font-mono text-xs text-muted2">
          {wiki.sources.length} 篇来源
          {wiki.updated && ` · 更新于 ${wiki.updated}`}
        </div>
      </header>

      {/* 正文章节 */}
      {wiki.sections.map((sec, i) => (
        <section key={i} className="mt-7">
          <h2 className="mb-2 font-serif text-lg font-semibold text-ink">
            {sec.heading}
          </h2>
          <div className="flex flex-col gap-3">
            {sec.paragraphs.map((p, j) => (
              <p key={j} className="text-[15px] leading-7 text-ink">
                {p.text}
                {p.cites.map((c) => (
                  <Cite key={c} id={c} />
                ))}
              </p>
            ))}
          </div>
        </section>
      ))}

      {/* 观点矛盾 */}
      {wiki.conflict && (
        <section className="mt-8 rounded-xl border border-line bg-panel p-5">
          <div className="mb-3 flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
              观点矛盾
            </span>
            <span className="text-sm font-medium text-ink">
              {wiki.conflict.topic}
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {wiki.conflict.sides.map((side, i) => {
              const src = wiki.sources.find((s) => s.id === side.note_id);
              return (
                <div
                  key={i}
                  className="rounded-lg border border-line bg-white px-4 py-3"
                >
                  <p className="text-sm leading-relaxed text-ink">
                    {side.claim}
                  </p>
                  {src && (
                    <Link
                      href={`/notes/${src.id}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs text-muted hover:text-accent"
                    >
                      <TypeBadge type={src.type} />
                      <span className="max-w-[180px] truncate">
                        {src.title}
                      </span>
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 来源 */}
      {wiki.sources.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-muted2">
            来源
          </h2>
          <ol className="flex flex-col gap-1.5">
            {wiki.source_ids.map((id, i) => {
              const src = wiki.sources.find((s) => s.id === id);
              if (!src) return null;
              return (
                <li key={id} className="flex items-center gap-2 text-sm">
                  <span className="font-mono text-xs text-muted2">
                    [{i + 1}]
                  </span>
                  <TypeBadge type={src.type} />
                  <Link
                    href={`/notes/${src.id}`}
                    className="text-ink hover:text-accent"
                  >
                    {src.title}
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </article>
  );
}
