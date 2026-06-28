"use client";

import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!identifier.trim() || !password) return;
    setSubmitting(true);
    setError("");
    try {
      await login(identifier.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败");
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-cream px-6">
      <div className="w-full max-w-sm">
        {/* 品牌 */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-brand">
            <span className="font-serif text-2xl font-semibold text-cream">复</span>
          </div>
          <div className="text-center">
            <div className="font-serif text-xl font-semibold text-ink">fuxi 知识库</div>
            <div className="mt-1 font-mono text-[10px] tracking-widest text-muted2">
              KNOWLEDGE BASE
            </div>
          </div>
        </div>

        <form
          onSubmit={submit}
          className="flex flex-col gap-3 rounded-2xl border border-line bg-white p-6"
        >
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">用户名或邮箱</span>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="username"
              className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink outline-none focus:border-brand"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">密码</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink outline-none focus:border-brand"
            />
          </label>

          {error && <p className="text-sm text-[#B23C3C]">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !identifier.trim() || !password}
            className="mt-1 rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
          >
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-muted2">
          账号由管理员创建。如需开通，请联系管理员。
        </p>
      </div>
    </div>
  );
}
