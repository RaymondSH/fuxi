// 根布局：NativeWind + SafeArea + AuthProvider + SnackProvider。
// expo-router 的 Stack 承载页面；AuthProvider 完成登录守卫。
//
// 5 个底部 tab 路由：index(首页) / chat / note / graph / settings。
// 这些路由显示持久底部 nav；login 与未匹配路由不显示。

import { router, Stack, usePathname } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { BottomNav } from "@/components/BottomNav";
import AuthProvider, { useAuth } from "@/contexts/AuthProvider";
import SnackProvider from "@/contexts/SnackProvider";

const TAB_ROUTES = ["index", "chat", "note", "graph", "settings"];

// 登录守卫完成前显示空白屏，避免页面闪现。
function Guard({ children }: { children: React.ReactNode }) {
  const { loading } = useAuth();
  if (loading) {
    return (
      <SafeAreaView className="flex-1 bg-cream" edges={["top"]}>
        <StatusBar style="dark" />
      </SafeAreaView>
    );
  }
  return <>{children}</>;
}

function Shell() {
  const pathname = usePathname();
  const seg = pathname.replace(/^\//, "").split("/")[0];
  const current = TAB_ROUTES.includes(seg) ? seg : "index";
  const showNav = TAB_ROUTES.includes(seg);

  return (
    <SafeAreaView className="flex-1 bg-cream" edges={["top"]}>
      <StatusBar style="dark" />
      <View className="flex-1">
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="login" />
          <Stack.Screen name="chat" />
          <Stack.Screen name="note" />
          <Stack.Screen name="graph" />
          <Stack.Screen name="settings" />
        </Stack>
        {showNav ? (
          <BottomNav current={current} onNavigate={(id) => router.replace(`/${id}`)} />
        ) : null}
      </View>
    </SafeAreaView>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <Guard>
        <SnackProvider>
          <Shell />
        </SnackProvider>
      </Guard>
    </AuthProvider>
  );
}
