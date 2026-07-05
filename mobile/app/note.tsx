// 笔记详情/编辑：标题 + 标签/实体 + 正文编辑器。
// 对齐设计稿 renderNote / refreshNote / triggerSave：
//   - GET /notes/{id} 拉详情
//   - 编辑标题/正文后 1.5s debounce 自动保存（PATCH /notes/{id}）
//   - 手动「保存」按钮立即保存
//   - 正文初始值 = original.join("\n\n") || summary || content

import { useLocalSearchParams, useFocusEffect } from "expo-router";
import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";

import { AppBar } from "@/components/AppBar";
import { Icon } from "@/components/Icons";
import { useSnack } from "@/contexts/SnackProvider";
import { ApiError, apiGet, apiPatch } from "@/lib/api";
import type { Note } from "@/lib/types";

export default function NoteScreen() {
  const params = useLocalSearchParams<{ id?: string }>();
  const id = params.id;
  const { notify } = useSnack();

  const [note, setNote] = useState<Note | null>(null);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 标记是否在加载中替换编辑器内容（避免触发自动保存）
  const loadingRef = useRef(true);

  const load = useCallback(async () => {
    if (!id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    loadingRef.current = true;
    try {
      const data = await apiGet<Note>(`/notes/${id}`);
      setNote(data);
      setTitle(data.title || "");
      const bodyText =
        (data.original && data.original.length > 0
          ? data.original.join("\n\n")
          : data.summary || "") || "";
      setBody(bodyText);
      setDirty(false);
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "加载笔记失败");
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, [id, notify]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const doSave = useCallback(
    async (silent = false) => {
      if (!id || loadingRef.current) return;
      setSaving(true);
      try {
        await apiPatch(`/notes/${id}`, { title, content: body });
        setDirty(false);
        if (!silent) notify("笔记已同步");
      } catch (e) {
        notify(e instanceof ApiError ? e.message : "保存失败");
      } finally {
        setSaving(false);
      }
    },
    [id, title, body, notify],
  );

  // 1.5s debounce 自动保存
  function triggerAutoSave() {
    if (loadingRef.current) return;
    setDirty(true);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      doSave(true);
    }, 1500);
  }

  // 卸载时清定时器
  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  if (!id) {
    return (
      <View className="flex-1 bg-cream">
        <AppBar title="笔记" subtitle="新建" onBack={() => router.back()} />
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-sm text-muted">
            移动端暂不支持新建笔记，请使用 Web 端创建。
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-cream">
      <AppBar
        title="笔记"
        subtitle={note?.title || "加载中…"}
        onBack={() => router.back()}
        right={
          <Pressable
            onPress={() => doSave(false)}
            className="h-11 w-11 items-center justify-center rounded-full"
            hitSlop={8}
          >
            <View className="flex-row items-center gap-1.5">
              {saving ? (
                <ActivityIndicator size="small" color="#9a4a2f" />
              ) : (
                <Icon name="check" size={18} color={dirty ? "#9a4a2f" : "#8c8273"} />
              )}
            </View>
          </Pressable>
        }
      />

      {loading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6f675b" />
        </View>
      ) : note ? (
        <KeyboardAvoidingView
          className="flex-1"
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <ScrollView
            className="flex-1"
            keyboardShouldPersistTaps="handled"
            contentContainerClassName="px-4 pb-6 pt-3"
          >
            <TextInput
              value={title}
              onChangeText={(t) => {
                setTitle(t);
                triggerAutoSave();
              }}
              placeholder="标题"
              placeholderTextColor="#8c8273"
              className="font-serif text-xl font-semibold text-ink"
            />

            {/* 标签 + 实体 */}
            <View className="mt-2 flex-row flex-wrap gap-1.5">
              {note.tags.map((t, i) => (
                <View key={`t-${i}`} className="rounded-full bg-panel px-2 py-0.5">
                  <Text className="text-[10px] text-muted">
                    {typeof t === "string" ? t : (t as { name?: string }).name || ""}
                  </Text>
                </View>
              ))}
              {note.entities.map((e, i) => (
                <View key={`e-${i}`} className="rounded-full bg-brand-soft px-2 py-0.5">
                  <Text className="text-[10px] text-accent">{e.name}</Text>
                </View>
              ))}
            </View>

            <TextInput
              value={body}
              onChangeText={(t) => {
                setBody(t);
                triggerAutoSave();
              }}
              placeholder="写下笔记内容…"
              placeholderTextColor="#8c8273"
              multiline
              textAlignVertical="top"
              className="mt-3 min-h-[300px] text-sm leading-5 text-ink"
            />
          </ScrollView>
        </KeyboardAvoidingView>
      ) : (
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-sm text-muted">笔记加载失败</Text>
        </View>
      )}
    </View>
  );
}
