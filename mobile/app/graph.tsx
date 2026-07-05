// 知识图谱页：SVG + 力导向布局 + 节点点击展开关联。
// 对齐设计稿 renderGraph / drawGraph / hoverNode：
//   - GET /graph?filter=all → { nodes:[{id,name,cat,count}], edges:[[id,id]] }
//   - 用 layoutGraph 算节点位置（力导向，与 Web 端算法一致）
//   - SVG 渲染边（线）+ 节点（圆 + 文字），节点按 cat 着色、按 count 算半径
//   - 点节点显示底部 sheet（实体名 + 关联笔记数）

import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import Svg, { Circle, Line, Text as SvgText } from "react-native-svg";

import { AppBar } from "@/components/AppBar";
import { useSnack } from "@/contexts/SnackProvider";
import { ApiError, apiGet } from "@/lib/api";
import { layoutGraph, nodeRadius, type PositionedNode } from "@/lib/forceLayout";
import type { EntityCat, GraphData } from "@/lib/types";

const CAT_COLORS: Record<EntityCat, string> = {
  concept: "#6e8b5e",
  product: "#b25b3c",
  company: "#5c7796",
};

const CANVAS_W = 360;
const CANVAS_H = 480;

export default function GraphScreen() {
  const { notify } = useSnack();
  const [data, setData] = useState<GraphData | null>(null);
  const [positions, setPositions] = useState<PositionedNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PositionedNode | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const graph = await apiGet<GraphData>("/graph?filter=all");
        setData(graph);
        if (graph.nodes && graph.nodes.length > 0) {
          const pos = layoutGraph(graph, CANVAS_W, CANVAS_H);
          setPositions(pos);
        }
      } catch (e) {
        notify(e instanceof ApiError ? e.message : "图谱加载失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [notify]);

  return (
    <View className="flex-1 bg-cream">
      <AppBar
        title="知识图谱"
        subtitle="触控节点以展开关联"
        right={
          <Pressable
            onPress={() => notify("筛选器已打开")}
            className="h-11 w-11 items-center justify-center rounded-full"
            hitSlop={8}
          >
            <Text className="text-base text-muted">⋯</Text>
          </Pressable>
        }
      />

      <View className="flex-1 items-center justify-center">
        {loading ? (
          <View className="items-center gap-2">
            <ActivityIndicator color="#6f675b" />
            <Text className="text-xs text-muted">加载图谱中…</Text>
          </View>
        ) : !data || data.nodes.length === 0 ? (
          <Text className="px-6 text-center text-sm text-muted">还没有知识关联</Text>
        ) : (
          <View className="relative">
            <Svg width={CANVAS_W} height={CANVAS_H}>
              {/* 边 */}
              {data.edges.map(([a, b], i) => {
                const pa = positions.find((p) => p.id === a);
                const pb = positions.find((p) => p.id === b);
                if (!pa || !pb) return null;
                return (
                  <Line
                    key={`e-${i}`}
                    x1={pa.x}
                    y1={pa.y}
                    x2={pb.x}
                    y2={pb.y}
                    stroke="#d4c8b8"
                    strokeWidth={1}
                  />
                );
              })}
              {/* 节点 */}
              {positions.map((node) => {
                const r = nodeRadius(node.count);
                const color = CAT_COLORS[node.cat] || "#8c8273";
                const isSelected = selected?.id === node.id;
                return (
                  <Pressable
                    key={node.id}
                    onPress={() => {
                      setSelected(node);
                    }}
                  >
                    <Circle
                      cx={node.x}
                      cy={node.y}
                      r={r}
                      fill={color}
                      fillOpacity={isSelected ? 1 : 0.85}
                      stroke={isSelected ? "#2b2722" : color}
                      strokeWidth={isSelected ? 2 : 0}
                    />
                    <SvgText
                      x={node.x}
                      y={node.y + r + 12}
                      fontSize={10}
                      fill="#2b2722"
                      textAnchor="middle"
                    >
                      {node.name}
                    </SvgText>
                  </Pressable>
                );
              })}
            </Svg>

            {/* 图例 */}
            <View className="mt-2 flex-row justify-center gap-3">
              {(["concept", "product", "company"] as EntityCat[]).map((cat) => (
                <View key={cat} className="flex-row items-center gap-1">
                  <View
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: CAT_COLORS[cat] }}
                  />
                  <Text className="text-[10px] text-muted2">
                    {cat === "concept" ? "概念" : cat === "product" ? "产品" : "公司"}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </View>

      {/* 底部 sheet */}
      {selected ? (
        <View className="mx-4 mb-2 rounded-xl border border-line bg-white p-4">
          <View className="flex-row items-center justify-between">
            <Text className="font-serif text-base font-semibold text-ink">
              {selected.name}
            </Text>
            <Pressable onPress={() => setSelected(null)} hitSlop={8}>
              <Text className="text-base text-muted2">✕</Text>
            </Pressable>
          </View>
          <Text className="mt-1 text-xs text-muted">
            {selected.count > 0
              ? `${selected.count} 个关联笔记`
              : "暂无关联"}
          </Text>
          <View className="mt-2 flex-row gap-1.5">
            <View
              className="rounded-full px-2 py-0.5"
              style={{ backgroundColor: CAT_COLORS[selected.cat] + "22" }}
            >
              <Text className="text-[10px]" style={{ color: CAT_COLORS[selected.cat] }}>
                {selected.cat === "concept"
                  ? "概念"
                  : selected.cat === "product"
                    ? "产品"
                    : "公司"}
              </Text>
            </View>
          </View>
        </View>
      ) : null}
    </View>
  );
}
