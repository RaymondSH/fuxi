"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import type { User, UserRole } from "@/lib/types";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");

  // 建号表单
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [limit, setLimit] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<{ items: User[] }>("/auth/users");
      setUsers(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    if (username.trim().length < 2 || !email.trim() || password.length < 6) return;
    setCreating(true);
    setError("");
    try {
      await apiPost("/auth/users", {
        username: username.trim(),
        email: email.trim(),
        display_name: name.trim() || null,
        password,
        role,
        daily_token_limit: limit.trim() ? Number(limit) : null,
      });
      setUsername("");
      setEmail("");
      setName("");
      setPassword("");
      setRole("member");
      setLimit("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "建号失败");
    } finally {
      setCreating(false);
    }
  }

  async function patch(id: string, body: Record<string, unknown>) {
    setError("");
    try {
      await apiPatch(`/auth/users/${id}`, body);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function resetPassword(id: string) {
    const pw = window.prompt("输入新密码（至少 6 位）");
    if (!pw) return;
    if (pw.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    patch(id, { password: pw });
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">用户管理</h1>
        <p className="mt-1 text-sm text-muted">建号、改角色与每日额度、停用账号。</p>
      </header>

      {error && <p className="mb-4 text-sm text-[#B23C3C]">{error}</p>}

      {/* 建号 */}
      <form
        onSubmit={createUser}
        className="mb-8 grid grid-cols-2 gap-3 rounded-xl border border-line bg-panel p-4 md:grid-cols-3"
      >
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="用户名（登录用，≥2 位）"
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          type="email"
          placeholder="邮箱"
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="显示名（可选）"
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          placeholder="初始密码（≥6 位）"
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as UserRole)}
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        >
          <option value="member">成员</option>
          <option value="admin">管理员</option>
        </select>
        <input
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
          type="number"
          placeholder="每日额度（留空=默认）"
          className="rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <button
          type="submit"
          disabled={creating || username.trim().length < 2 || !email.trim() || password.length < 6}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
        >
          建号
        </button>
      </form>

      {/* 用户列表 */}
      <ul className="flex flex-col gap-2">
        {users.map((u) => (
          <li
            key={u.id}
            className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-white px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-ink">
                {u.display_name || u.email}
                {!u.is_active && (
                  <span className="ml-2 rounded bg-panel px-1.5 py-0.5 font-mono text-[10px] text-[#B23C3C]">
                    已停用
                  </span>
                )}
              </div>
              <div className="truncate font-mono text-[11px] text-muted2">
                {u.username ? `@${u.username} · ` : ""}{u.email} · 额度{" "}
                {u.daily_token_limit ?? "默认"}
              </div>
            </div>

            <select
              value={u.role}
              onChange={(e) => patch(u.id, { role: e.target.value })}
              className="rounded-lg border border-line bg-white px-2 py-1 text-xs outline-none focus:border-brand"
            >
              <option value="member">成员</option>
              <option value="admin">管理员</option>
            </select>

            <button
              onClick={() => resetPassword(u.id)}
              className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs text-muted hover:border-brand hover:text-accent"
            >
              改密码
            </button>

            <button
              onClick={() => patch(u.id, { is_active: !u.is_active })}
              className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs text-muted hover:border-brand hover:text-accent"
            >
              {u.is_active ? "停用" : "启用"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
