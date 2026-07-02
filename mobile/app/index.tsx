// 首页占位：登录后展示用户名 + 角色角标 + 登出按钮。
// 仅用于验证 token 持久化与鉴权链路通；检索/问答/图谱等页面后续阶段接入。

import { Pressable, Text, View } from "react-native";

import { useAuth } from "@/contexts/AuthProvider";

export default function HomeScreen() {
  const { user, loading, logout } = useAuth();

  if (loading || !user) {
    return <View className="flex-1 items-center justify-center bg-cream" />;
  }

  const name = user.display_name || user.username || user.email;

  return (
    <View className="flex-1 bg-cream px-6">
      <View className="mt-10 items-center">
        <View className="h-14 w-14 items-center justify-center rounded-xl bg-brand">
          <Text className="font-serif text-2xl font-semibold text-cream">复</Text>
        </View>
      </View>

      <View className="mt-8 gap-2">
        <Text className="text-center font-serif text-2xl font-semibold text-ink">
          欢迎，{name}
        </Text>
        <View className="flex-row items-center justify-center gap-2">
          <Text className="text-xs text-muted2">{user.email}</Text>
          <View className="rounded bg-brand-soft px-2 py-0.5">
            <Text className="text-[10px] font-medium text-accent">
              {user.role === "admin" ? "管理员" : "成员"}
            </Text>
          </View>
        </View>
      </View>

      <Text className="mt-6 text-center text-xs text-muted2">
        fuxi 移动端 · 登录链路已通
      </Text>

      <View className="mt-auto mb-8">
        <Pressable
          onPress={logout}
          className="items-center rounded-lg border border-line bg-white px-5 py-3"
        >
          <Text className="text-sm font-medium text-ink">退出登录</Text>
        </Pressable>
      </View>
    </View>
  );
}
