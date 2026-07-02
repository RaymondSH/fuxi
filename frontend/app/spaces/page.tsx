"use client";

// 空间管理页：列出当前用户可见空间、新建空间、对 space_admin 空间做成员管理。
// 后端权限：任意登录用户可列/建空间；空间内改成员需 space_admin（sysadmin 恒通过）。
// 这里 UI 按各空间的 my_role 决定是否展示「成员」操作区。

import { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { useSpaces, canAct } from "@/components/SpacesProvider";
import type { SpaceMember, SpaceRole, SpaceWithMembership, UserLookup } from "@/lib/types";

const ROLES: SpaceRole[] = ["viewer", "editor", "space_admin"];
const ROLE_LABEL: Record<SpaceRole, string> = {
  viewer: "只读",
  editor: "编辑",
  space_admin: "空间管理员",
};

export default function SpacesPage() {
  const { spaces, loading, reload } = useSpaces();
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  // 新建空间表单
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [desc, setDesc] = useState("");
  const [creating, setCreating] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      await apiPost("/spaces", {
        name: name.trim(),
        slug: slug.trim() || null,
        description: desc.trim() || null,
      });
      setName("");
      setSlug("");
      setDesc("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">空间</h1>
        <p className="mt-1 text-sm text-muted">
          空间是内容隔离的边界。每个空间有独立成员与角色；笔记 / 主题页 / MCP token 都归属某空间。
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-[#B23C3C]">{error}</p>}

      {/* 新建空间 */}
      <form onSubmit={create} className="mb-8 grid gap-2 rounded-xl border border-line bg-panel p-4">
        <label className="font-mono text-xs uppercase tracking-widest text-muted2">新建空间</label>
        <div className="flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="空间名（如：工程团队）"
            className="flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="slug（留空自动，a-z0-9-）"
            className="w-48 rounded-lg border border-line bg-white px-3 py-2 font-mono text-xs outline-none focus:border-brand"
          />
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
          >
            创建
          </button>
        </div>
        <input
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="描述（可选）"
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
      </form>

      {/* 空间列表 */}
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
        可见空间 · {spaces.length}
      </h2>
      {loading ? (
        <p className="rounded-lg border border-line bg-panel px-4 py-8 text-center text-sm text-muted2">
          加载中…
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {spaces.map((s) => (
            <SpaceRow
              key={s.id}
              space={s}
              expanded={expanded === s.id}
              onToggle={() => setExpanded(expanded === s.id ? null : s.id)}
              onChanged={reload}
              onError={setError}
            />
          ))}
          {spaces.length === 0 && (
            <li className="rounded-lg border border-dashed border-line bg-panel px-4 py-6 text-center text-xs text-muted2">
              还没有可见空间。
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

function SpaceRow({
  space,
  expanded,
  onToggle,
  onChanged,
  onError,
}: {
  space: SpaceWithMembership;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const isAdmin = canAct(space.my_role, "space_admin");
  return (
    <li className="overflow-hidden rounded-lg border border-line bg-white">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <span className="text-sm font-medium text-ink">{space.name}</span>
        <code className="rounded bg-panel px-1.5 py-0.5 font-mono text-[11px] text-muted2">
          {space.slug}
        </code>
        {space.is_default && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-accent">默认</span>
        )}
        <RoleBadge role={space.my_role} />
        <span className="font-mono text-[10px] text-muted2">
          {space.member_count} 成员
        </span>
        <button
          onClick={onToggle}
          className="ml-auto rounded-lg border border-line bg-white px-3 py-1 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
        >
          {expanded ? "收起" : "成员"}
        </button>
      </div>
      {expanded && (
        <MembersPanel
          space={space}
          canManage={isAdmin}
          onChanged={onChanged}
          onError={onError}
        />
      )}
    </li>
  );
}

function MembersPanel({
  space,
  canManage,
  onChanged,
  onError,
}: {
  space: SpaceWithMembership;
  canManage: boolean;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [members, setMembers] = useState<SpaceMember[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await apiGet<{ items: SpaceMember[] }>(`/spaces/${space.id}/members`);
      setMembers(res.items);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "加载成员失败");
    } finally {
      setLoading(false);
    }
  }, [space.id, onError]);

  useEffect(() => {
    load();
  }, [load]);

  async function changeRole(m: SpaceMember, role: SpaceRole) {
    try {
      await apiPatch(`/spaces/${space.id}/members/${m.user_id}`, { role });
      load();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "更新角色失败");
    }
  }

  async function remove(m: SpaceMember) {
    if (!confirm(`移除成员「${m.display_name || m.email}」？移除后该用户将无法访问此空间。`)) return;
    try {
      await apiDelete(`/spaces/${space.id}/members/${m.user_id}`);
      load();
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "移除失败");
    }
  }

  return (
    <div className="border-t border-line bg-panel/40 px-4 py-3">
      {loading ? (
        <p className="py-4 text-center text-xs text-muted2">加载中…</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {members.map((m) => (
            <li key={m.user_id} className="flex items-center gap-2 rounded bg-white px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink">{m.display_name || m.email}</div>
                <div className="truncate font-mono text-[10px] text-muted2">{m.email}</div>
              </div>
              {canManage ? (
                <>
                  <select
                    value={m.role}
                    onChange={(e) => changeRole(m, e.target.value as SpaceRole)}
                    className="rounded border border-line bg-white px-2 py-1 text-xs text-muted outline-none focus:border-brand"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => remove(m)}
                    className="rounded border border-line bg-white px-2 py-1 text-xs text-muted transition-colors hover:border-[#B23C3C] hover:text-[#B23C3C]"
                  >
                    移除
                  </button>
                </>
              ) : (
                <RoleBadge role={m.role} />
              )}
            </li>
          ))}
          {members.length === 0 && (
            <li className="py-2 text-center text-xs text-muted2">暂无成员</li>
          )}
        </ul>
      )}

      {canManage && <AddMember spaceId={space.id} onAdded={load} onChanged={onChanged} onError={onError} />}
    </div>
  );
}

function AddMember({
  spaceId,
  onAdded,
  onChanged,
  onError,
}: {
  spaceId: string;
  onAdded: () => void;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<UserLookup[]>([]);
  const [role, setRole] = useState<SpaceRole>("viewer");

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const res = await apiGet<{ items: UserLookup[] }>(
          `/spaces/${spaceId}/members/search?q=${encodeURIComponent(q.trim())}`
        );
        setResults(res.items);
      } catch {
        setResults([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, spaceId]);

  async function add(u: UserLookup) {
    try {
      await apiPost(`/spaces/${spaceId}/members`, { user_id: u.user_id, role });
      setQ("");
      setResults([]);
      onAdded();
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "添加失败");
    }
  }

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="flex items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="按邮箱或姓名搜索用户…"
          className="flex-1 rounded-lg border border-line bg-white px-3 py-1.5 text-sm outline-none focus:border-brand"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as SpaceRole)}
          className="rounded-lg border border-line bg-white px-2 py-1.5 text-xs text-muted outline-none focus:border-brand"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>{ROLE_LABEL[r]}</option>
          ))}
        </select>
      </div>
      {results.length > 0 && (
        <ul className="mt-1 overflow-hidden rounded-lg border border-line bg-white">
          {results.map((u) => (
            <li key={u.user_id} className="flex items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink">{u.display_name || u.email}</div>
                <div className="truncate font-mono text-[10px] text-muted2">{u.email}</div>
              </div>
              <button
                onClick={() => add(u)}
                disabled={u.is_member}
                className="rounded border border-line bg-white px-2 py-1 text-xs text-muted transition-colors hover:border-brand hover:text-accent disabled:opacity-40"
              >
                {u.is_member ? "已加入" : "添加"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RoleBadge({ role }: { role: string | null }) {
  if (!role) return null;
  const color =
    role === "space_admin" ? "text-accent" : role === "editor" ? "text-[#9A4A2F]" : "text-muted2";
  return (
    <span className={`font-mono text-[10px] uppercase tracking-wider ${color}`}>
      {ROLE_LABEL[role as SpaceRole] || role}
    </span>
  );
}
