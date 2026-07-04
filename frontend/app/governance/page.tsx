"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { canAct, useSpaces } from "@/components/SpacesProvider";
import { ApiError, apiGet, apiPatch, apiPost } from "@/lib/api";

interface Issue {
  id: string;
  note_id: string | null;
  type: string;
  severity: "low" | "medium" | "high";
  title: string;
  evidence: Record<string, unknown>;
}

const TYPE_LABEL: Record<string, string> = {
  stale: "可能过期", duplicate: "近似重复", conflict: "内容冲突",
  broken_link: "来源失效", missing_tags: "缺少标签",
};

export default function GovernancePage() {
  const { spaces, activeSpace, loading: spacesLoading, error: spacesError } = useSpaces();
  const [spaceId, setSpaceId] = useState("");
  const [items, setItems] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const selected = spaces.find((s) => s.id === spaceId);

  useEffect(() => {
    if (!spaceId && spaces.length) setSpaceId(activeSpace?.id || spaces[0].id);
  }, [spaces, activeSpace, spaceId]);

  async function load(id = spaceId) {
    if (!id) return;
    setLoading(true);
    setError("");
    setItems([]);
    try {
      const data = await apiGet<{ items: Issue[] }>(`/governance/issues?space_id=${id}&status=open`);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "治理待办加载失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void load(); }, [spaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function scan() {
    setBusy(true);
    setError("");
    try {
      await apiPost("/governance/scans", { space_id: spaceId });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "巡检任务创建失败");
    }
    finally { setBusy(false); }
  }
  async function close(id: string, status: "resolved" | "ignored") {
    setError("");
    try {
      await apiPatch(`/governance/issues/${id}`, { status });
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "治理待办更新失败");
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-ink">知识治理</h1>
          <p className="mt-1 text-sm text-muted">过期、重复、冲突、坏链与缺标签待办。</p>
        </div>
        <div className="flex gap-2">
          <select value={spaceId} onChange={(e) => setSpaceId(e.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
            {spaces.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {canAct(selected?.my_role, "space_admin") && (
            <button onClick={scan} disabled={busy}
              className="rounded-lg bg-brand px-4 py-2 text-sm text-cream disabled:opacity-50">
              {busy ? "已加入队列" : "运行巡检"}
            </button>
          )}
        </div>
      </div>
      {(spacesError || error) && (
        <p className="mb-4 text-sm text-[#B23C3C]">{spacesError || error}</p>
      )}
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.id} className="rounded-xl border border-line bg-panel p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className="mr-2 rounded-full bg-brand-soft px-2 py-0.5 font-mono text-[10px] text-accent">
                  {TYPE_LABEL[item.type] || item.type} · {item.severity}
                </span>
                {item.note_id ? <Link href={`/notes/${item.note_id}`} className="text-sm font-medium text-ink hover:text-accent">{item.title}</Link>
                  : <span className="text-sm font-medium text-ink">{item.title}</span>}
              </div>
              {canAct(selected?.my_role, "editor") && (
                <div className="flex gap-2 text-xs">
                  <button onClick={() => close(item.id, "resolved")} className="text-accent">标记解决</button>
                  <button onClick={() => close(item.id, "ignored")} className="text-muted">忽略</button>
                </div>
              )}
            </div>
          </div>
        ))}
        {(spacesLoading || loading) && (
          <div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted2">加载中…</div>
        )}
        {!spacesLoading && !loading && !spacesError && !error && !items.length && (
          <div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted2">
            当前没有开放待办
          </div>
        )}
      </div>
    </div>
  );
}
