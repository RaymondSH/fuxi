// 登录页。复刻 frontend/app/login/page.tsx 的品牌 + 表单 + 错误提示，
// 用 React Native 组件 + NativeWind class（class 名与 Web 端一致）。

import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, Text, TextInput, View } from "react-native";

import { useAuth } from "@/contexts/AuthProvider";
import { ApiError } from "@/lib/api";

export default function LoginScreen() {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (!identifier.trim() || !password) return;
    setSubmitting(true);
    setError("");
    try {
      await login(identifier.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败");
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      className="flex-1 bg-cream"
    >
      <View className="flex-1 items-center justify-center px-6">
        {/* 品牌 */}
        <View className="mb-8 items-center gap-3">
          <View className="h-14 w-14 items-center justify-center rounded-xl bg-brand">
            <Text className="font-serif text-2xl font-semibold text-cream">复</Text>
          </View>
          <View className="items-center">
            <Text className="font-serif text-xl font-semibold text-ink">fuxi 知识库</Text>
            <Text className="mt-1 font-mono text-[10px] tracking-widest text-muted2">
              KNOWLEDGE BASE
            </Text>
          </View>
        </View>

        {/* 表单 */}
        <View className="w-full max-w-sm gap-3 rounded-2xl border border-line bg-white p-6">
          <View className="gap-1">
            <Text className="text-xs text-muted">用户名或邮箱</Text>
            <TextInput
              value={identifier}
              onChangeText={setIdentifier}
              autoCapitalize="none"
              autoComplete="username"
              autoCorrect={false}
              placeholder="用户名或邮箱"
              placeholderTextColor="#8c8273"
              className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink"
            />
          </View>
          <View className="gap-1">
            <Text className="text-xs text-muted">密码</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="current-password"
              placeholder="密码"
              placeholderTextColor="#8c8273"
              className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink"
            />
          </View>

          {error ? <Text className="text-sm text-[#B23C3C]">{error}</Text> : null}

          <Pressable
            onPress={submit}
            disabled={submitting || !identifier.trim() || !password}
            className="mt-1 items-center rounded-lg bg-ink px-5 py-2.5 disabled:opacity-40"
          >
            <Text className="text-sm font-medium text-cream">
              {submitting ? "登录中…" : "登录"}
            </Text>
          </Pressable>
        </View>

        <Text className="mt-4 text-center text-xs text-muted2">
          账号由管理员创建。如需开通，请联系管理员。
        </Text>
      </View>
    </KeyboardAvoidingView>
  );
}
