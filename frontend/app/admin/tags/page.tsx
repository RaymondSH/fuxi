"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";

type TagVocab = {
  name: string;
  aliases: string[];
  description: string | null;
  status: "active" | "merged" | "deprecated";
  merged_into: string | null;
};

type TagCloud = { name: string; count: number };

export default function TagsAdminPage() {
  const [vocab, setVocab] = useState<TagVocab[]>([]);
  const [cloud, setCloud] = useState<TagCloud[]>([]);
  const [error, setError] = useState("");

  // 新建标签
  const [newName, setNewName] = useState("");
  const [newAliases, setNewAliases] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);

  // 归并
  const [mergeFrom, setMergeFrom] = useState("");
  const [mergeTo, setMergeTo] = useState("");
  const [merging, setMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [v, c] = await Promise.all([
        apiGet<{ items: TagVocab[] }>("/tags/vocab"),
        apiGet<{ items: TagCloud[] }>("/tags"),
      ]);
      setVocab(v.items);
      setCloud(c.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createTag(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError("");
    try {
      await apiPost("/tags", {
        name: newName.trim(),
        aliases: newAliases
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        description: newDesc.trim() || null,
      });
      setNewName("");
      setNewAliases("");
      setNewDesc("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "新建失败");
    } finally {
      setCreating(false);
    }
  }

  async function patchTag(name: string, body: Record<string, unknown>) {
    setError("");
    try {
      await apiPatch(`/tags/${encodeURIComponent(name)}`, body);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function mergeTag(e: React.FormEvent) {
    e.preventDefault();
    if (!mergeFrom.trim() || !mergeTo.trim() || mergeFrom.trim() === mergeTo.trim())
      return;
    setMerging(true);
    setError("");
    setMergeResult(null);
    try {
      const res = await apiPost<{ affected_notes: number; from: string; to: string }>(
        "/tags/merge",
        { from_tag: mergeFrom.trim(), to_tag: mergeTo.trim() },
      );
      setMergeResult(`已归并 ${res.from} → ${res.to}，受影响笔记 ${res.affected_notes} 篇`);
      setMergeFrom("");
      setMergeTo("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "归并失败");
    } finally {
      setMerging(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">标签治理</h1>
        <p className="mt-1 text-sm text-muted">
          受控词表（规范名 + 别名）、状态与归并。归并会物理回写所有笔记的 tags 并同步索引。
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-[#B23C3C]">{error}</p>}

      <div className="grid gap-8 lg:grid-cols-2">
        {/* 左：受控词表 + 新建 */}
        <section>
          <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
            受控词表 · {vocab.length}
          </h2>

          <form
            onSubmit={createTag}
            className="mb-4 grid gap-2 rounded-xl border border-line bg-panel p-4"
          >
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="规范名（如：机器学习）"
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <input
              value={newAliases}
              onChange={(e) => setNewAliases(e.target.value)}
              placeholder="别名，逗号分隔（如：ML, machine learning）"
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="描述（可选）"
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={creating || !newName.trim()}
              className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
            >
              新建规范标签
            </button>
          </form>

          <ul className="flex flex-col gap-2">
            {vocab.map((t) => (
              <li
                key={t.name}
                className="rounded-lg border border-line bg-white px-4 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-ink">{t.name}</span>
                  <StatusBadge status={t.status} />
                  {t.merged_into && (
                    <span className="font-mono text-[10px] text-muted2">
                      → {t.merged_into}
                    </span>
                  )}
                  <select
                    value={t.status}
                    onChange={(e) =>
                      patchTag(t.name, { status: e.target.value })
                    }
                    className="ml-auto rounded-lg border border-line bg-white px-2 py-1 text-xs outline-none focus:border-brand"
                  >
                    <option value="active">active</option>
                    <option value="deprecated">deprecated</option>
                    <option value="merged">merged</option>
                  </select>
                </div>
                {t.aliases.length > 0 && (
                  <div className="mt-1 font-mono text-[11px] text-muted2">
                    别名：{t.aliases.join(" · ")}
                  </div>
                )}
                {t.description && (
                  <div className="mt-1 text-xs text-muted">{t.description}</div>
                )}
              </li>
            ))}
            {vocab.length === 0 && (
              <li className="rounded-lg border border-dashed border-line bg-panel px-4 py-6 text-center text-xs text-muted2">
                还没有受控词表。新建一个规范标签，或直接用归并把同义旧名收口。
              </li>
            )}
          </ul>
        </section>

        {/* 右：标签云 + 归并 */}
        <section>
          <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
            当前标签云 · {cloud.length}
          </h2>
          <div className="mb-6 flex flex-wrap gap-2 rounded-xl border border-line bg-panel p-4">
            {cloud.map((t) => (
              <button
                key={t.name}
                onClick={() => setMergeFrom(t.name)}
                title={`点此填入归并的「旧标签」`}
                className="rounded-full border border-line bg-white px-3 py-1 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
              >
                {t.name}
                <span className="ml-1 font-mono text-[10px] text-muted2">
                  {t.count}
                </span>
              </button>
            ))}
            {cloud.length === 0 && (
              <span className="text-xs text-muted2">暂无 done 笔记的标签。</span>
            )}
          </div>

          <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
            归并同义标签
          </h2>
          <form
            onSubmit={mergeTag}
            className="grid gap-2 rounded-xl border border-line bg-panel p-4"
          >
            <input
              value={mergeFrom}
              onChange={(e) => setMergeFrom(e.target.value)}
              placeholder="旧标签名（被归并）"
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <input
              value={mergeTo}
              onChange={(e) => setMergeTo(e.target.value)}
              placeholder="规范名（归并到）"
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={
                merging ||
                !mergeFrom.trim() ||
                !mergeTo.trim() ||
                mergeFrom.trim() === mergeTo.trim()
              }
              className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
            >
              执行归并
            </button>
            {mergeResult && (
              <p className="text-xs text-accent">{mergeResult}</p>
            )}
          </form>
          <p className="mt-2 text-xs text-muted2">
            归并会改写所有笔记的 tags（旧名→规范名）、重建 ES 索引、并在词表里标记旧名为 merged。
          </p>
        </section>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: TagVocab["status"] }) {
  const map: Record<TagVocab["status"], { label: string; cls: string }> = {
    active: { label: "active", cls: "text-muted2" },
    merged: { label: "merged", cls: "text-[#B23C3C]" },
    deprecated: { label: "deprecated", cls: "text-muted2" },
  };
  const s = map[status];
  return (
    <span className={`font-mono text-[10px] uppercase tracking-wider ${s.cls}`}>
      {s.label}
    </span>
  );
}
