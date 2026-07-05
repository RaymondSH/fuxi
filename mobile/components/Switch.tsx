// 本地 toggle 开关。设计稿用 CSS .switch + ::before/::after 实现，
// RN 用 View + Animated 模拟滑块。

import { Pressable, StyleSheet, Text, View } from "react-native";

interface SwitchProps {
  value: boolean;
  onValueChange: (v: boolean) => void;
  label?: string;
}

export function Switch({ value, onValueChange, label }: SwitchProps) {
  return (
    <Pressable
      onPress={() => onValueChange(!value)}
      className="flex-row items-center gap-2.5"
      hitSlop={8}
    >
      {label ? <Text className="flex-1 text-sm text-ink">{label}</Text> : null}
      <View style={[styles.track, value ? styles.trackOn : styles.trackOff]}>
        <View style={[styles.thumb, value ? styles.thumbOn : styles.thumbOff]} />
      </View>
    </Pressable>
  );
}

const W = 52;
const H = 44;
const THUMB = 24;

const styles = StyleSheet.create({
  track: {
    width: W,
    height: H,
    borderRadius: 22,
    paddingVertical: 10,
    paddingHorizontal: 2,
    justifyContent: "center",
  },
  trackOn: {
    backgroundColor: "#2b2722",
  },
  trackOff: {
    backgroundColor: "#e7ddd0",
  },
  thumb: {
    width: THUMB,
    height: THUMB,
    borderRadius: THUMB / 2,
    backgroundColor: "#ffffff",
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  thumbOn: {
    transform: [{ translateX: W - THUMB - 4 }],
  },
  thumbOff: {
    transform: [{ translateX: 0 }],
  },
});
