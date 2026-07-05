// 顶部栏：title + subtitle + 左侧 back（可选）+ 右侧 action（可选）。
// 对齐设计稿 appBar 组件结构。

import { Pressable, Text, View } from "react-native";

import { Icon } from "@/components/Icons";

interface AppBarProps {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: React.ReactNode;
}

export function AppBar({ title, subtitle, onBack, right }: AppBarProps) {
  return (
    <View className="min-h-[56px] flex-row items-center gap-2.5 border-b border-line bg-cream px-4 pb-2 pt-1.5">
      {onBack ? (
        <Pressable
          onPress={onBack}
          className="h-11 w-11 items-center justify-center rounded-full"
          hitSlop={8}
        >
          <Icon name="back" size={21} color="#2b2722" />
        </Pressable>
      ) : null}
      <View className="min-w-0 flex-1">
        <Text
          className="text-xl font-semibold tracking-tight text-ink"
          numberOfLines={1}
        >
          {title}
        </Text>
        {subtitle ? (
          <Text className="mt-0.5 font-mono text-[11px] text-muted" numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right ?? (
        <Pressable className="h-11 w-11 items-center justify-center rounded-full" hitSlop={8}>
          <Icon name="more" size={21} color="#6f675b" />
        </Pressable>
      )}
    </View>
  );
}
