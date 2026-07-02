"use client";

import { useEffect, useState } from "react";
import { apiGet, ApiError } from "@/lib/api";
import type { UsageAlert, UsageRow, UsageTrendPoint } from "@/lib/types";

type UsageData = {
  items: UsageRow[];
  tz: string;
  org_today: number;
  org_trend: UsageTrendPoint[];
  alerts: UsageAlert[];
};

// 手绘 7 日趋势折线（SVG），无图表库依赖。
function TrendChart({ trend }: { trend: UsageTrendPoint[] }) {
  if (trend.length === 0) return null;
  const W = 320;
  const H = 80;
  const padX = 8;
  const padY = 12;
  const max = Math.max(1, ...trend.map((p) => p.total));
  const stepX = (W - padX * 2) / Math.max(1, trend.length - 1);
  const pts = trend.map((p, i) => {
    const x = padX + i * stepX;
    const y = H - padY - (p.total / max) * (H - padY * 2);
    return { x, y, ...p };
  });
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-20 w-full" preserveAspectRatio="none">
      {/* 基线 */}
      <line x1={padX} y1={H - padY} x2={W - padX} y2={H - padY} stroke="#e7ddd0" strokeWidth="1" />
      {/* 折线 */}
      <path d={path} fill="none" stroke="#b25b3c" strokeWidth="1.5" strokeLinejoin="round" />
      {/* 数据点 */}
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="2" fill="#b25b3c" />
      ))}
    </svg>
  );
}

export default function UsagePage() {
  const [data, setData] = useState<UsageData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<UsageData>("/auth/usage?days=7")
      .then(setData)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载失败"),
      );
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <p className="text-sm text-[#B23C3C]">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10 text-sm text-muted2">加载中…</div>
    );
  }

  const rows = data.items;
  const tz = data.tz;

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-ink">用量看板</h1>
        <p className="mt-1 text-sm text-muted">
          各用户当日 token 消耗与额度{tz && ` · 时区 ${tz}`}。次日 0 点重置。
        </p>
      </header>

      {/* 概览：组织今日合计 + 7 日趋势 */}
      <section className="mb-6 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-line bg-panel px-4 py-3">
          <div className="font-mono text-[11px] uppercase tracking-wider text-muted2">
            今日组织合计
          </div>
          <div className="mt-1 font-serif text-2xl font-semibold text-ink">
            {data.org_today.toLocaleString()}
          </div>
          <div className="mt-1 text-xs text-muted2">tokens</div>
        </div>
        <div className="rounded-xl border border-line bg-panel px-4 py-3">
          <div className="mb-1 font-mono text-[11px] uppercase tracking-wider text-muted2">
            近 7 日趋势
          </div>
          <TrendChart trend={data.org_trend} />
        </div>
      </section>

      {/* 告警：今日已达额度 80% 的用户 */}
      {data.alerts.length > 0 && (
        <section className="mb-6 rounded-xl border border-[#E0C9C0] bg-[#FBF1EE] px-4 py-3">
          <div className="mb-1 font-mono text-[11px] uppercase tracking-wider text-[#B23C3C]">
            额度告警 · {data.alerts.length}
          </div>
          <ul className="flex flex-col gap-1">
            {data.alerts.map((a) => (
              <li key={a.id} className="flex items-center gap-2 text-sm text-ink">
                <span className="flex-1 truncate">
                  {a.display_name || a.email}
                </span>
                <span className="font-mono text-[11px] text-[#B23C3C]">
                  {a.pct}% · {a.used_today.toLocaleString()}/{a.limit.toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 用户明细 */}
      <ul className="flex flex-col gap-2">
        {rows.map((r) => {
          const pct =
            r.limit && r.limit > 0
              ? Math.min(100, Math.round((r.used_today / r.limit) * 100))
              : 0;
          const over = r.limit !== null && r.used_today >= r.limit;
          const warn = r.limit !== null && r.used_today >= r.limit * 0.8 && !over;
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
                {warn && (
                  <span className="rounded bg-[#FBF1EE] px-1.5 py-0.5 font-mono text-[10px] text-[#B23C3C]">
                    接近上限
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
                      background: over ? "#B23C3C" : warn ? "#C8923C" : "#B25B3C",
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
