"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { NoteListResponse } from "@/lib/types";

export default function TrashPage() {
  const [data, setData] = useState<NoteListResponse | null>(null);
  const load = () => apiGet<NoteListResponse>("/notes/trash").then(setData);
  useEffect(() => { load().catch(() => {}); }, []);
  async function restore(id: string) {
    await apiPost(`/notes/${id}/restore`);
    setData((prev) => prev ? { ...prev, items: prev.items.filter((n) => n.id !== id), total: prev.total - 1 } : prev);
  }
  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <h1 className="font-serif text-2xl font-semibold text-ink">回收站</h1>
      <p className="mt-1 text-sm text-muted">软删除内容不会进入检索、问答、图谱、Wiki 或 MCP。</p>
      <div className="mt-6 space-y-3">
        {data?.items.map((note) => (
          <div key={note.id} className="flex items-center justify-between rounded-xl border border-line bg-panel p-4">
            <div><div className="text-sm font-medium text-ink">{note.title}</div><div className="text-xs text-muted2">{note.source}</div></div>
            <button onClick={() => restore(note.id)} className="text-xs text-accent">恢复</button>
          </div>
        ))}
        {data && !data.items.length && <p className="text-sm text-muted2">回收站为空</p>}
      </div>
    </div>
  );
}
