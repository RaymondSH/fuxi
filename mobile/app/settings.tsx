// 设置页：账户信息 + 同步与索引状态 + AI 偏好开关 + 其他 + 退出登录。
// 对齐设计稿 renderSettings / refreshSettings：
//   - GET /system/status 拉版本/笔记数/实体数/索引状态/db_size
//   - Switch 开关（本地态，仅 toast 提示）
//   - 退出登录：调用 useAuth().logout()

import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { AppBar } from "@/components/AppBar";
import { Icon } from "@/components/Icons";
import { Switch } from "@/components/Switch";
import { useAuth } from "@/contexts/AuthProvider";
import { useSnack } from "@/contexts/SnackProvider";
import { ApiError, apiGet } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <View className="flex-row items-center justify-between border-b border-line px-4 py-3">
      <Text className="text-sm text-ink">{label}</Text>
      {children}
    </View>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View className="mt-4">
      <Text className="mb-1.5 px-1 text-[11px] font-medium text-muted2">{label}</Text>
      <View className="overflow-hidden rounded-xl border border-line bg-white">
        {children}
      </View>
    </View>
  );
}

function Chip({ children, sync = false }: { children: React.ReactNode; sync?: boolean }) {
  return (
    <View
      className={`rounded-full px-2 py-0.5 ${sync ? "bg-brand-soft" : "bg-panel"}`}
    >
      <Text
        className={`text-[10px] font-medium ${sync ? "text-accent" : "text-muted"}`}
      >
        {children}
      </Text>
    </View>
  );
}

export default function SettingsScreen() {
  const { user, logout } = useAuth();
  const { notify } = useSnack();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [syncOn, setSyncOn] = useState(true);
  const [myKnowledgeOnly, setMyKnowledgeOnly] = useState(true);
  const [showSources, setShowSources] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<SystemStatus>("/system/status");
        setStatus(data);
      } catch (e) {
        notify(e instanceof ApiError ? e.message : "加载系统状态失败");
      }
    })();
  }, [notify]);

  const name = user?.display_name || user?.username || "";
  const role = user?.role === "admin" ? "管理员" : "成员";
  const dbMB = status?.db_size_bytes
    ? Math.round(status.db_size_bytes / 1048576)
    : null;

  return (
    <View className="flex-1 bg-cream">
      <AppBar title="设置" subtitle="fuxi 移动端" />

      <ScrollView className="flex-1" contentContainerClassName="px-4 pb-6">
        {/* 账户 */}
        <Group label="账户">
          <Row label={name}>
            <Chip sync>{role}</Chip>
          </Row>
          <Row label="邮箱">
            <Text className="text-xs text-muted2">{user?.email || "—"}</Text>
          </Row>
        </Group>

        {/* 同步与索引 */}
        <Group label="同步与索引">
          <Row label="知识库同步">
            <Switch value={syncOn} onValueChange={(v) => { setSyncOn(v); notify(v ? "已开启" : "已关闭"); }} />
          </Row>
          <Row label="笔记数量">
            <Chip sync>{status?.notes ?? "—"} 条</Chip>
          </Row>
          <Row label="实体数量">
            <Chip>{status?.entities ?? "—"}</Chip>
          </Row>
          <Row label="索引状态">
            <Text className="text-xs text-[#6e8b5e]">
              {status?.pg_version ? "正常" : "—"}
            </Text>
          </Row>
        </Group>

        {/* AI */}
        <Group label="AI">
          <Row label="仅使用我的知识">
            <Switch
              value={myKnowledgeOnly}
              onValueChange={(v) => { setMyKnowledgeOnly(v); notify(v ? "已开启" : "已关闭"); }}
            />
          </Row>
          <Row label="显示引用来源">
            <Switch
              value={showSources}
              onValueChange={(v) => { setShowSources(v); notify(v ? "已开启" : "已关闭"); }}
            />
          </Row>
        </Group>

        {/* 其他 */}
        <Group label="其他">
          <Row label="缓存">
            <Text className="text-xs text-muted2">{dbMB !== null ? `${dbMB} MB` : "—"}</Text>
          </Row>
          <Pressable
            onPress={logout}
            className="flex-row items-center justify-between border-b border-line px-4 py-3"
          >
            <Text className="text-sm text-[#B23C3C]">退出登录</Text>
            <Icon name="logOut" size={18} color="#B23C3C" />
          </Pressable>
        </Group>

        <Text className="mt-5 text-center font-mono text-[10px] text-muted2">
          fuxi v{status?.version || "0.5"}
        </Text>
      </ScrollView>
    </View>
  );
}
