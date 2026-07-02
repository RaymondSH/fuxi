"use client";

import { useState } from "react";
import { ApiError, apiPost } from "@/lib/api";

export default function SettingsPage() {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setOk(false);
    if (!oldPw || !newPw) return;
    if (newPw !== confirm) {
      setError("两次输入的新密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      await apiPost("/auth/change-password", {
        old_password: oldPw,
        new_password: newPw,
      });
      setOk(true);
      setOldPw("");
      setNewPw("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "修改失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-6 py-12">
      <div className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">修改密码</h1>
        <p className="mt-1 text-xs text-muted2">
          密码需至少 8 位，且包含字母与数字。
        </p>
      </div>

      <form
        onSubmit={submit}
        className="flex flex-col gap-3 rounded-2xl border border-line bg-white p-6"
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">当前密码</span>
          <input
            type="password"
            value={oldPw}
            onChange={(e) => setOldPw(e.target.value)}
            autoComplete="current-password"
            className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink outline-none focus:border-brand"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">新密码</span>
          <input
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            autoComplete="new-password"
            className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink outline-none focus:border-brand"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">确认新密码</span>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink outline-none focus:border-brand"
          />
        </label>

        {error && <p className="text-sm text-[#B23C3C]">{error}</p>}
        {ok && <p className="text-sm text-emerald-600">密码已更新。</p>}

        <button
          type="submit"
          disabled={submitting || !oldPw || !newPw || !confirm}
          className="mt-1 rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
        >
          {submitting ? "提交中…" : "更新密码"}
        </button>
      </form>
    </div>
  );
}
