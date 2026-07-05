// 全局 snackbar 提示。设计稿用 #snack 元素 + show class 控制，
// RN 用 Context + Provider 实现：useSnack() 返回 notify(msg) 函数。

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { Animated, Pressable, StyleSheet, Text, View } from "react-native";

interface SnackState {
  notify: (msg: string) => void;
}

const SnackContext = createContext<SnackState | null>(null);

export function useSnack(): SnackState {
  const ctx = useContext(SnackContext);
  if (!ctx) throw new Error("useSnack 必须在 SnackProvider 内使用");
  return ctx;
}

export default function SnackProvider({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState("");
  const [visible, setVisible] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;

  const notify = useCallback((text: string) => {
    setMsg(text);
    setVisible(true);
    Animated.timing(opacity, {
      toValue: 1,
      duration: 200,
      useNativeDriver: true,
    }).start();
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      Animated.timing(opacity, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }).start(() => setVisible(false));
    }, 2000);
  }, [opacity]);

  return (
    <SnackContext.Provider value={{ notify }}>
      {children}
      {visible ? (
        <View pointerEvents="none" style={styles.overlay}>
          <Animated.View
            style={[styles.snack, { opacity, transform: [{ translateY: opacity.interpolate({ inputRange: [0, 1], outputRange: [14, 0] }) }] }]}
          >
            <Text style={styles.text}>{msg}</Text>
          </Animated.View>
        </View>
      ) : null}
    </SnackContext.Provider>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: "absolute",
    bottom: 100,
    left: 0,
    right: 0,
    alignItems: "center",
    zIndex: 30,
  },
  snack: {
    backgroundColor: "#2b2722",
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  text: {
    color: "#fbf1e9",
    fontSize: 12,
  },
});
