import Link from "next/link";
import TypeBadge from "@/components/TypeBadge";
import type { NoteSummary } from "@/lib/types";

export default function NoteCard({ note }: { note: NoteSummary }) {
  return (
    <Link
      href={`/notes/${note.id}`}
      className="block rounded-lg border border-line bg-white px-4 py-3 transition-colors hover:border-brand"
    >
      <div className="flex items-center gap-2">
        <TypeBadge type={note.type} />
        <span className="flex-1 truncate font-medium text-ink">
          {note.title}
        </span>
        {note.score != null && (
          <span className="shrink-0 font-mono text-[10px] text-muted2">
            {note.score.toFixed(3)}
          </span>
        )}
      </div>

      <div className="mt-1 flex items-center gap-2 text-xs text-muted2">
        {note.source && <span className="truncate">{note.source}</span>}
        {note.date && <span>· {note.date}</span>}
      </div>

      {/* 命中片段：后端已转义，仅含 <em> 高亮 */}
      {note.snippet ? (
        <p
          className="mt-2 text-sm leading-relaxed text-muted [&_em]:bg-brand-soft [&_em]:not-italic [&_em]:text-accent"
          dangerouslySetInnerHTML={{ __html: note.snippet }}
        />
      ) : (
        note.summary && (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted">
            {note.summary}
          </p>
        )
      )}

      {note.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
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
    </Link>
  );
}
