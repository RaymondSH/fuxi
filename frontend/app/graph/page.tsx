"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import TypeBadge from "@/components/TypeBadge";
import { layoutGraph, nodeRadius, type PositionedNode } from "@/lib/forceLayout";
import { apiGet } from "@/lib/api";
import type { EntityCat, EntityDetail, GraphData } from "@/lib/types";

const W = 680;
const H = 520;

const CAT_COLOR: Record<EntityCat, string> = {
  concept: "#6E8B5E",
  product: "#B25B3C",
  company: "#5C7796",
};

const FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "concept", label: "概念" },
  { key: "product", label: "产品" },
  { key: "company", label: "公司" },
];

function GraphInner() {
  const searchParams = useSearchParams();
  const targetEntity = searchParams.get("entity"); // 从笔记详情页实体跳来时带上
  const [filter, setFilter] = useState("all");
  const [data, setData] = useState<GraphData | null>(null);
  const [selected, setSelected] = useState<EntityDetail | null>(null);

  useEffect(() => {
    apiGet<GraphData>(`/graph?filter=${filter}`)
      .then(setData)
      .catch(() => setData({ nodes: [], edges: [] }));
  }, [filter]);

  // 力导向布局（数据变了才重算）
  const positioned = useMemo<PositionedNode[]>(
    () => (data ? layoutGraph(data, W, H) : []),
    [data],
  );
  const posById = useMemo(
    () => new Map(positioned.map((n) => [n.id, n])),
    [positioned],
  );

  function pickEntity(id: string) {
    apiGet<EntityDetail>(`/graph/entities/${id}`).then(setSelected);
  }

  // 从笔记详情页带 entity 参数跳来时，自动选中该实体（拉详情 + 展开侧栏）。
  // 仅当节点数据就绪且目标实体在当前过滤结果里时触发，避免无效请求。
  const targetPicked = useRef(false);
  useEffect(() => {
    if (!targetEntity || !data || targetPicked.current) return;
    if (data.nodes.some((n) => n.id === targetEntity)) {
      targetPicked.current = true;
      pickEntity(targetEntity);
    }
  }, [targetEntity, data]);

  const selectedId = selected?.id;

  return (
    <div className="flex h-full">
      {/* 图区 */}
      <div className="flex flex-1 flex-col px-8 py-10">
        <header className="mb-4">
          <h1 className="font-serif text-2xl font-semibold text-ink">知识图谱</h1>
          <p className="mt-1 text-sm text-muted">
            实体共现关系。点击节点查看相关笔记。
          </p>
        </header>

        {/* 过滤 */}
        <div className="mb-4 inline-flex gap-1 self-start rounded-lg bg-panel p-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
                filter === f.key
                  ? "bg-ink font-medium text-cream"
                  : "text-muted hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex-1 rounded-xl border border-line bg-white">
          <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
            {/* 边 */}
            {data?.edges.map(([a, b], i) => {
              const na = posById.get(a);
              const nb = posById.get(b);
              if (!na || !nb) return null;
              const active = selectedId === a || selectedId === b;
              return (
                <line
                  key={i}
                  x1={na.x}
                  y1={na.y}
                  x2={nb.x}
                  y2={nb.y}
                  stroke={active ? "#B25B3C" : "#E0D5C6"}
                  strokeWidth={active ? 1.5 : 1}
                />
              );
            })}
            {/* 节点 */}
            {positioned.map((n) => {
              const r = nodeRadius(n.count);
              const isSel = selectedId === n.id;
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x},${n.y})`}
                  className="cursor-pointer"
                  onClick={() => pickEntity(n.id)}
                >
                  <circle
                    r={r}
                    fill={CAT_COLOR[n.cat]}
                    fillOpacity={isSel ? 1 : 0.85}
                    stroke={isSel ? "#2B2722" : "#fff"}
                    strokeWidth={isSel ? 2.5 : 1.5}
                  />
                  <text
                    textAnchor="middle"
                    dy={r + 13}
                    fontSize={12}
                    fill="#2B2722"
                  >
                    {n.name}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* 图例 */}
        <div className="mt-3 flex gap-4 text-xs text-muted2">
          {(["concept", "product", "company"] as EntityCat[]).map((c) => (
            <span key={c} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ background: CAT_COLOR[c] }}
              />
              {c === "concept" ? "概念" : c === "product" ? "产品" : "公司"}
            </span>
          ))}
        </div>
      </div>

      {/* 侧栏：选中实体 */}
      <aside className="w-80 shrink-0 overflow-y-auto border-l border-line bg-panel px-6 py-10">
        {!selected ? (
          <p className="text-sm text-muted2">点击左侧节点查看实体详情</p>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ background: CAT_COLOR[selected.cat] }}
              />
              <h2 className="font-serif text-xl font-semibold text-ink">
                {selected.name}
              </h2>
            </div>
            <div className="mt-1 font-mono text-xs text-muted2">
              {selected.cat} · 被 {selected.count} 篇提及
            </div>
            {selected.aliases.length > 0 && (
              <div className="mt-2 text-xs text-muted">
                别名：{selected.aliases.join("、")}
              </div>
            )}

            <h3 className="mb-2 mt-6 font-mono text-xs uppercase tracking-widest text-muted2">
              相关笔记
            </h3>
            <ul className="flex flex-col gap-2">
              {selected.notes.map((note) => (
                <li key={note.id}>
                  <Link
                    href={`/notes/${note.id}`}
                    className="block rounded-lg border border-line bg-white px-3 py-2 transition-colors hover:border-brand"
                  >
                    <div className="flex items-center gap-1.5">
                      <TypeBadge type={note.type} />
                      {note.date && (
                        <span className="font-mono text-[10px] text-muted2">
                          {note.date}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-sm text-ink">{note.title}</div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}

// useSearchParams 需在 Suspense 边界内（Next 16 要求），否则 build 会报兜底错误
export default function GraphPage() {
  return (
    <Suspense>
      <GraphInner />
    </Suspense>
  );
}
