"use client";

import { useEffect, useState } from "react";
import { apiGet, ApiError } from "@/lib/api";
import type { UsageRow } from "@/lib/types";

export default function UsagePage() {
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [tz, setTz] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<{ items: UsageRow[]; tz: string }>("/auth/usage")
      .then((d) => {
        setRows(d.items);
        setTz(d.tz);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载失败"),
      );
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">今日用量</h1>
        <p className="mt-1 text-sm text-muted">
          各用户当日 token 消耗与额度{tz && ` · 时区 ${tz}`}。次日 0 点重置。
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-[#B23C3C]">{error}</p>}

      <ul className="flex flex-col gap-2">
        {rows.map((r) => {
          const pct =
            r.limit && r.limit > 0
              ? Math.min(100, Math.round((r.used_today / r.limit) * 100))
              : 0;
          const over = r.limit !== null && r.used_today >= r.limit;
          return (
            <li
              key={r.id}
              className="rounded-lg border border-line bg-white px-4 py-3"
            >
              <div className="flex items-center gap-2">
                <span className="flex-1 truncate text-sm font-medium text-ink">
                  {r.display_name || r.email}
                </span>
                {r.role === "admin" && (
                  <span className="rounded bg-brand-soft px-1.5 py-0.5 font-mono text-[10px] text-accent">
                    管理员
                  </span>
                )}
                <span
                  className="font-mono text-[11px]"
                  style={{ color: over ? "#B23C3C" : "#6F675B" }}
                >
                  {r.used_today.toLocaleString()}
                  {" / "}
                  {r.limit === null ? "∞" : r.limit.toLocaleString()}
                </span>
              </div>
              {r.limit !== null && (
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${pct}%`,
                      background: over ? "#B23C3C" : "#B25B3C",
                    }}
                  />
                </div>
              )}
            </li>
          );
        })}
        {rows.length === 0 && !error && (
          <p className="rounded-lg border border-line bg-panel px-4 py-8 text-center text-sm text-muted2">
            暂无用量数据
          </p>
        )}
      </ul>
    </div>
  );
}
