"use client";

// 左下角「系统情况」：存储后端 + 版本、知识库规模、数据库占用、磁盘容量条（剩余可用）。
// 纯展示，数据由 Sidebar 拉取后传入。

import type { SystemStatus } from "@/lib/types";

function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

export default function SystemStatus({ data }: { data: SystemStatus | null }) {
  if (!data) return null;

  const disk = data.disk;
  const usedPct =
    disk && disk.total_bytes > 0
      ? Math.min(100, Math.round((disk.used_bytes / disk.total_bytes) * 100))
      : 0;
  const near = usedPct >= 85;

  const storageLabel = data.storage_backend === "r2" ? "R2" : "本地盘";

  return (
    <div className="px-4 pb-3 pt-1">
      <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted2">
        系统情况
      </div>

      {/* 存储后端 + 版本 */}
      <div className="font-mono text-[11px] leading-relaxed text-muted">
        存储 {storageLabel}
        {data.pgvector_version && <> · pgvector {data.pgvector_version}</>}
        {data.pg_version && <> · PG {data.pg_version}</>}
      </div>

      {/* 知识库规模 + 数据库占用 */}
      <div className="font-mono text-[11px] leading-relaxed text-muted2">
        {data.notes} 笔记 · {data.entities} 实体 · {data.wikis} 主题
      </div>
      <div className="font-mono text-[11px] leading-relaxed text-muted2">
        数据库 {fmtBytes(data.db_size_bytes)}
      </div>

      {/* 容量条：磁盘已用 / 总量，强调剩余可用 */}
      {disk && (
        <div className="mt-2">
          <div className="h-1.5 overflow-hidden rounded-full bg-cream">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${usedPct}%`,
                background: near ? "#B23C3C" : "#B25B3C",
              }}
            />
          </div>
          <div className="mt-1 flex justify-between font-mono text-[10px] text-muted2">
            <span>{storageLabel}</span>
            <span style={near ? { color: "#B23C3C" } : undefined}>
              剩余 {fmtBytes(disk.free_bytes)} / {fmtBytes(disk.total_bytes)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
