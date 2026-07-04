"use client";

import { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import type { McpToken, McpTokenCreated, SpaceWithMembership } from "@/lib/types";

export default function McpAdminPage() {
  const [tokens, setTokens] = useState<McpToken[]>([]);
  const [spaces, setSpaces] = useState<SpaceWithMembership[]>([]);
  const [error, setError] = useState("");

  // 新建 token
  const [name, setName] = useState("");
  const [spaceId, setSpaceId] = useState(""); // 留空 = default 空间
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<McpTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [tokRes, spRes] = await Promise.all([
        apiGet<{ items: McpToken[] }>("/mcp-admin/tokens"),
        apiGet<{ items: SpaceWithMembership[] }>("/spaces"),
      ]);
      setTokens(tokRes.items);
      setSpaces(spRes.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    setCreated(null);
    setCopied(false);
    try {
      const res = await apiPost<McpTokenCreated>("/mcp-admin/tokens", {
        name: name.trim(),
        space_id: spaceId || null,
      });
      setCreated(res);
      setName("");
      setSpaceId("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }

  async function changeSpace(t: McpToken, sid: string) {
    setError("");
    try {
      // 空 = default 空间。后端 _resolve_space(None) 落 default。
      await apiPatch(`/mcp-admin/tokens/${t.id}`, { space_id: sid || null });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function toggle(t: McpToken) {
    setError("");
    try {
      await apiPatch(`/mcp-admin/tokens/${t.id}`, { is_active: !t.is_active });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function remove(t: McpToken) {
    if (!confirm(`确认删除 token「${t.name}」？删除后该 token 立即失效。`)) return;
    setError("");
    try {
      await apiDelete(`/mcp-admin/tokens/${t.id}`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function copyToken() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* 剪贴板不可用时静默，用户可手动选中复制 */
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">MCP Token</h1>
        <p className="mt-1 text-sm text-muted">
          为外部 Agent（Claude Desktop / 自建 Agent）颁发访问 token，调用
          <code className="mx-1 rounded bg-panel px-1 font-mono text-xs text-accent">
            /mcp
          </code>
          端点。明文仅在创建时显示一次，库里只存哈希。
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-[#B23C3C]">{error}</p>}

      {/* 新建 */}
      <form
        onSubmit={create}
        className="mb-6 grid gap-2 rounded-xl border border-line bg-panel p-4"
      >
        <label className="font-mono text-xs uppercase tracking-widest text-muted2">
          新建 token
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="名字（如：Claude Desktop）"
            className="flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <select
            value={spaceId}
            onChange={(e) => setSpaceId(e.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm text-muted outline-none focus:border-brand"
          >
            <option value="">绑定空间（默认）</option>
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
          >
            生成
          </button>
        </div>
        <p className="text-xs text-muted2">
          token 绑定空间后，该 token 调用 MCP 工具时只能读该空间的内容（等价于该空间只读访问）。
        </p>

        {created && (
          <div className="mt-2 rounded-lg border border-[#C8923C] bg-[#fbf6ec] p-3">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#C8923C]">
                ⚠ 仅此一次
              </span>
              <span className="text-xs text-muted">复制保存，关闭后无法再取回</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 break-all rounded bg-white px-2 py-1.5 font-mono text-xs text-ink">
                {created.token}
              </code>
              <button
                type="button"
                onClick={copyToken}
                className="shrink-0 rounded-lg border border-line bg-white px-3 py-1.5 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
              >
                {copied ? "已复制" : "复制"}
              </button>
            </div>
            <p className="mt-2 text-xs text-muted2">
              在 Claude Desktop 配置里填 <code className="font-mono">Authorization: Bearer {created.token}</code>，
              端点与接入边界见 <code className="font-mono">docs/architecture.md</code>。
            </p>
            <button
              type="button"
              onClick={() => setCreated(null)}
              className="mt-2 text-xs text-muted2 underline hover:text-accent"
            >
              我已保存，关闭
            </button>
          </div>
        )}
      </form>

      {/* token 列表 */}
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
        已颁发 · {tokens.length}
      </h2>
      <ul className="flex flex-col gap-2">
        {tokens.map((t) => (
          <li
            key={t.id}
            className="rounded-lg border border-line bg-white px-4 py-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-ink">{t.name}</span>
              <ActiveBadge active={t.is_active} />
              <code className="rounded bg-panel px-1.5 py-0.5 font-mono text-[11px] text-muted2">
                {t.prefix}…
              </code>
              <select
                value={t.space_id || ""}
                onChange={(e) => changeSpace(t, e.target.value)}
                className="rounded border border-line bg-white px-2 py-0.5 text-[11px] text-muted outline-none focus:border-brand"
                title="token 绑定的空间"
              >
                <option value="">默认空间</option>
                {spaces.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              <span className="font-mono text-[10px] text-muted2">
                创建 {fmtDate(t.created_at)}
              </span>
              {t.last_used_at && (
                <span className="font-mono text-[10px] text-muted2">
                  最近使用 {fmtDate(t.last_used_at)}
                </span>
              )}
              <div className="ml-auto flex gap-2">
                <button
                  onClick={() => toggle(t)}
                  className={`rounded-lg border px-3 py-1 text-xs transition-colors ${
                    t.is_active
                      ? "border-line bg-white text-muted hover:border-[#B23C3C] hover:text-[#B23C3C]"
                      : "border-brand bg-brand-soft text-accent hover:border-brand"
                  }`}
                >
                  {t.is_active ? "停用" : "启用"}
                </button>
                <button
                  onClick={() => remove(t)}
                  className="rounded-lg border border-line bg-white px-3 py-1 text-xs text-muted transition-colors hover:border-[#B23C3C] hover:text-[#B23C3C]"
                >
                  删除
                </button>
              </div>
            </div>
          </li>
        ))}
        {tokens.length === 0 && (
          <li className="rounded-lg border border-dashed border-line bg-panel px-4 py-6 text-center text-xs text-muted2">
            还没有 token。新建一个，把明文复制给 Agent 客户端即可。
          </li>
        )}
      </ul>
    </div>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="font-mono text-[10px] uppercase tracking-wider text-accent">
      active
    </span>
  ) : (
    <span className="font-mono text-[10px] uppercase tracking-wider text-muted2">
      disabled
    </span>
  );
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
