// 轻量力导向布局：斥力（库仑）+ 边弹簧 + 向心力。
// 节点不多（几十个），同步迭代算到收敛即可，无需引入 d3。
// 移植自 frontend/lib/forceLayout.ts，算法完全一致。

import type { GraphData } from "@/lib/types";

export interface PositionedNode {
  id: string;
  name: string;
  cat: GraphData["nodes"][number]["cat"];
  count: number;
  x: number;
  y: number;
}

export function layoutGraph(
  data: GraphData,
  width: number,
  height: number,
  iterations = 400,
): PositionedNode[] {
  const cx = width / 2;
  const cy = height / 2;
  const n = data.nodes.length;
  if (n === 0) return [];

  // 初始位置：均匀撒在中心圆上
  const radius = Math.min(width, height) * 0.32;
  const nodes: PositionedNode[] = data.nodes.map((node, i) => ({
    ...node,
    x: cx + Math.cos((2 * Math.PI * i) / n) * radius,
    y: cy + Math.sin((2 * Math.PI * i) / n) * radius,
  }));
  const index = new Map(nodes.map((nd, i) => [nd.id, i]));

  const REPULSION = 9000; // 斥力强度
  const SPRING = 0.012; // 边弹簧系数
  const SPRING_LEN = 110; // 理想边长
  const CENTER = 0.01; // 向心力

  for (let iter = 0; iter < iterations; iter++) {
    const cooling = 1 - iter / iterations; // 退火：步长逐渐变小
    const fx = new Array(n).fill(0);
    const fy = new Array(n).fill(0);

    // 节点两两斥力
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = nodes[i].x - nodes[j].x;
        let dy = nodes[i].y - nodes[j].y;
        let d2 = dx * dx + dy * dy || 0.01;
        const f = REPULSION / d2;
        const d = Math.sqrt(d2);
        const ux = dx / d;
        const uy = dy / d;
        fx[i] += ux * f;
        fy[i] += uy * f;
        fx[j] -= ux * f;
        fy[j] -= uy * f;
      }
    }

    // 边弹簧（拉近相连节点到理想长度）
    for (const [a, b] of data.edges) {
      const ia = index.get(a);
      const ib = index.get(b);
      if (ia === undefined || ib === undefined) continue;
      const dx = nodes[ib].x - nodes[ia].x;
      const dy = nodes[ib].y - nodes[ia].y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = SPRING * (d - SPRING_LEN);
      const ux = dx / d;
      const uy = dy / d;
      fx[ia] += ux * f;
      fy[ia] += uy * f;
      fx[ib] -= ux * f;
      fy[ib] -= uy * f;
    }

    // 向心力 + 应用位移
    for (let i = 0; i < n; i++) {
      fx[i] += (cx - nodes[i].x) * CENTER;
      fy[i] += (cy - nodes[i].y) * CENTER;
      nodes[i].x += fx[i] * cooling * 0.5;
      nodes[i].y += fy[i] * cooling * 0.5;
      // 限制在画布内（留边距）
      nodes[i].x = Math.max(40, Math.min(width - 40, nodes[i].x));
      nodes[i].y = Math.max(40, Math.min(height - 40, nodes[i].y));
    }
  }

  return nodes;
}

export function nodeRadius(count: number): number {
  return 14 + Math.min(count, 8) * 3.5;
}
