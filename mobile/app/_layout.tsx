// 根布局：包 NativeWind + SafeArea + AuthProvider。
// expo-router 的 Stack 承载页面；AuthProvider 内部完成登录守卫（见 contexts/AuthProvider.tsx）。

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaView } from "react-native-safe-area-context";

import AuthProvider from "@/contexts/AuthProvider";

export default function RootLayout() {
  return (
    <AuthProvider>
      <SafeAreaView className="flex-1 bg-cream" edges={["top"]}>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="login" />
        </Stack>
      </SafeAreaView>
    </AuthProvider>
  );
}
