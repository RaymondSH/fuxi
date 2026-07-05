// 底部 5-tab 导航。设计稿用绝对定位 + grid 5 列，
// RN 用 SafeArea bottom + flex-row 实现。
// active 态：文字加粗 + icon-wrap 用 brand-soft 背景色。

import { Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Icon } from "@/components/Icons";

const TABS = [
  { id: "index", label: "首页", icon: "home" },
  { id: "chat", label: "AI 对话", icon: "chat" },
  { id: "note", label: "笔记", icon: "note" },
  { id: "graph", label: "图谱", icon: "graph" },
  { id: "settings", label: "设置", icon: "settings" },
] as const;

interface BottomNavProps {
  current: string;
  onNavigate: (id: string) => void;
}

export function BottomNav({ current, onNavigate }: BottomNavProps) {
  const insets = useSafeAreaInsets();
  return (
    <View
      className="border-t border-line bg-white"
      style={{ paddingBottom: Math.max(insets.bottom, 12), paddingTop: 8 }}
    >
      <View className="flex-row">
        {TABS.map((tab) => {
          const active = current === tab.id;
          return (
            <Pressable
              key={tab.id}
              onPress={() => onNavigate(tab.id)}
              className="flex-1 items-center gap-0.5 py-1"
              hitSlop={4}
            >
              <View
                className={`h-7 min-w-[40px] items-center justify-center rounded-2xl px-2 ${
                  active ? "bg-brand-soft" : ""
                }`}
              >
                <Icon
                  name={tab.icon}
                  size={20}
                  color={active ? "#9a4a2f" : "#6f675b"}
                />
              </View>
              <Text
                className={`text-[10px] ${active ? "font-semibold text-ink" : "text-muted"}`}
              >
                {tab.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
