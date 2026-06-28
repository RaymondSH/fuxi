import type { NoteType } from "@/lib/types";

// 来源角标色值源自设计稿 typeMeta
const META: Record<NoteType, { label: string; fg: string; bg: string }> = {
  link: { label: "LINK", fg: "#5C7796", bg: "#E4EAF1" },
  pdf: { label: "PDF", fg: "#9A4A2F", bg: "#F5E7DE" },
  word: { label: "WORD", fg: "#3E6B8A", bg: "#E1ECF3" },
  excel: { label: "XLSX", fg: "#4E7A4E", bg: "#E6F0E6" },
  image: { label: "IMG·OCR", fg: "#9A7A2E", bg: "#F2EAD6" },
};

export default function TypeBadge({ type }: { type: NoteType }) {
  const m = META[type] ?? META.link;
  return (
    <span
      className="inline-flex shrink-0 items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wider"
      style={{ color: m.fg, background: m.bg }}
    >
      {m.label}
    </span>
  );
}
