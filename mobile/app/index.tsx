// 首页：问候 + 搜索 + 快速记录 + 最近知识。
// 对齐设计稿 renderHome：按小时显示问候语、搜索框（focus 显历史、Enter 触检索）、
// 快速抓取（URL 入库）、最近笔记 5 条列表。

import { useFocusEffect } from "@react-navigation/native";
import { router } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";

import { AppBar } from "@/components/AppBar";
import { Icon } from "@/components/Icons";
import { useAuth } from "@/contexts/AuthProvider";
import { useSnack } from "@/contexts/SnackProvider";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import type { NoteSummary, SearchHistoryItem, SearchResponse } from "@/lib/types";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 9) return "早上好";
  if (h < 12) return "上午好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

function timeAgo(dateStr?: string): string {
  if (!dateStr) return "";
  const now = Date.now();
  const d = new Date(dateStr);
  const diff = Math.floor((now - d.getTime()) / 1000);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return Math.floor(diff / 60) + " 分钟前";
  if (diff < 86400) return Math.floor(diff / 3600) + " 小时前";
  if (diff < 2592000) return Math.floor(diff / 86400) + " 天前";
  return d.toLocaleDateString("zh-CN");
}

interface NotesList {
  items: NoteSummary[];
  total: number;
}

export default function HomeScreen() {
  const { user } = useAuth();
  const { notify } = useSnack();
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [history, setHistory] = useState<SearchHistoryItem[]>([]);
  const [showPanel, setShowPanel] = useState(false);
  const [results, setResults] = useState<SearchResponse | null>(null);

  const [capture, setCapture] = useState("");
  const [capturing, setCapturing] = useState(false);

  const name = user?.display_name || user?.username || "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<NotesList>("/notes?page=1&size=10");
      setNotes(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function onFocusSearch() {
    setShowPanel(true);
    setResults(null);
    if (history.length === 0) {
      try {
        const data = await apiGet<{ items: SearchHistoryItem[] }>("/search/history");
        setHistory(data.items || []);
      } catch {
        /* ignore */
      }
    }
  }

  async function doSearch() {
    const query = q.trim();
    if (!query) return;
    setSearching(true);
    setShowPanel(true);
    setResults(null);
    try {
      const res = await apiPost<SearchResponse>("/search", { q: query, mode: "hybrid" });
      setResults(res);
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "搜索失败");
      setShowPanel(false);
    } finally {
      setSearching(false);
    }
  }

  async function captureSubmit() {
    const text = capture.trim();
    if (!text) {
      notify("先写下一条想法");
      return;
    }
    if (!/^https?:\/\/\S+/.test(text)) {
      notify("暂仅支持链接保存，文字笔记请使用 Web 端");
      return;
    }
    setCapturing(true);
    try {
      await apiPost("/ingest/url", { url: text });
      notify("已添加到知识库");
      setCapture("");
      load();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "保存失败");
    } finally {
      setCapturing(false);
    }
  }

  return (
    <View className="flex-1 bg-cream">
      <AppBar
        title={`${greeting()}，${name}`}
        subtitle={`知识库 · ${total} 条笔记`}
        right={
          <Pressable
            onPress={() => router.push("/note")}
            className="h-11 w-11 items-center justify-center rounded-full"
            hitSlop={8}
          >
            <Icon name="plus" size={22} color="#2b2722" />
          </Pressable>
        }
      />

      <ScrollView
        className="flex-1"
        keyboardShouldPersistTaps="handled"
        contentContainerClassName="px-4 pb-6 pt-3"
      >
        {/* 搜索 */}
        <View className="flex-row items-center gap-2 rounded-xl border border-line bg-white px-3 py-2">
          <Icon name="search" size={18} color="#8c8273" />
          <TextInput
            value={q}
            onChangeText={setQ}
            onFocus={onFocusSearch}
            onSubmitEditing={doSearch}
            returnKeyType="search"
            placeholder="搜索笔记、网页与对话"
            placeholderTextColor="#8c8273"
            className="min-h-[36px] flex-1 text-sm text-ink"
          />
          <Pressable onPress={() => notify("语音输入已就绪")} hitSlop={8}>
            <Icon name="mic" size={18} color="#8c8273" />
          </Pressable>
        </View>

        {/* 搜索面板 */}
        {showPanel ? (
          <View className="mt-2 rounded-xl border border-line bg-white">
            {searching ? (
              <View className="items-center py-6">
                <ActivityIndicator color="#6f675b" />
                <Text className="mt-2 text-xs text-muted">正在检索「{q}」…</Text>
              </View>
            ) : results ? (
              results.results.length === 0 ? (
                <Text className="px-4 py-6 text-center text-xs text-muted">
                  没有找到结果
                </Text>
              ) : (
                <>
                  <View className="flex-row items-center justify-between border-b border-line px-4 py-2">
                    <Text className="text-sm font-semibold text-ink">
                      {results.total} 条结果
                    </Text>
                    <Text className="font-mono text-[10px] text-muted2">
                      {Math.round(results.took_ms)}ms
                    </Text>
                  </View>
                  {results.results.slice(0, 5).map((r) => (
                    <Pressable
                      key={r.id}
                      onPress={() => router.push(`/note?id=${r.id}`)}
                      className="flex-row items-center gap-3 border-b border-line px-4 py-2.5"
                    >
                      <Icon name="file" size={16} color="#8c8273" />
                      <View className="min-w-0 flex-1">
                        <Text className="text-sm text-ink" numberOfLines={1}>
                          {r.title}
                        </Text>
                        <Text className="mt-0.5 text-[11px] text-muted2" numberOfLines={1}>
                          {(r.snippet || r.summary || "").slice(0, 60)}
                        </Text>
                      </View>
                      {r.score ? (
                        <Text className="font-mono text-[10px] text-muted">
                          {Math.round(r.score * 100)}%
                        </Text>
                      ) : null}
                    </Pressable>
                  ))}
                  {results.total > 5 ? (
                    <Text className="px-4 py-2 text-center text-[11px] text-muted2">
                      还有 {results.total - 5} 条结果
                    </Text>
                  ) : null}
                </>
              )
            ) : history.length === 0 ? (
              <Text className="px-4 py-6 text-center text-xs text-muted">
                最近没有搜索记录
              </Text>
            ) : (
              history.slice(0, 5).map((item) => (
                <Pressable
                  key={item.id}
                  onPress={() => {
                    setQ(item.q);
                    doSearch();
                  }}
                  className="flex-row items-center gap-3 border-b border-line px-4 py-2.5"
                >
                  <Icon name="clock" size={16} color="#8c8273" />
                  <View className="min-w-0 flex-1">
                    <Text className="text-sm text-ink" numberOfLines={1}>
                      {item.q}
                    </Text>
                    <Text className="mt-0.5 text-[11px] text-muted2">
                      {item.hits} 条结果 · {timeAgo(item.created_at)}
                    </Text>
                  </View>
                </Pressable>
              ))
            )}
          </View>
        ) : null}

        {/* 快速记录 */}
        <View className="mt-5">
          <View className="mb-2 flex-row items-baseline justify-between">
            <Text className="font-serif text-base font-semibold text-ink">快速记录</Text>
            <Text className="text-[11px] text-muted2">自动归档</Text>
          </View>
          <View className="rounded-xl border border-line bg-white p-3">
            <TextInput
              value={capture}
              onChangeText={setCapture}
              placeholder="记下一条想法，或粘贴链接…"
              placeholderTextColor="#8c8273"
              multiline
              className="min-h-[60px] text-sm text-ink"
            />
            <View className="mt-2 flex-row items-center justify-between">
              <View className="flex-row gap-2">
                <Pressable onPress={() => notify("选择附件")} hitSlop={8}>
                  <Icon name="plus" size={18} color="#8c8273" />
                </Pressable>
                <Pressable onPress={() => notify("开始语音记录")} hitSlop={8}>
                  <Icon name="mic" size={18} color="#8c8273" />
                </Pressable>
              </View>
              <Pressable
                onPress={captureSubmit}
                disabled={capturing}
                className="rounded-lg bg-brand px-4 py-1.5 disabled:opacity-40"
              >
                <Text className="text-xs font-medium text-cream">
                  {capturing ? "保存中…" : "保存"}
                </Text>
              </Pressable>
            </View>
          </View>
        </View>

        {/* 最近知识 */}
        <View className="mt-5">
          <View className="mb-2 flex-row items-baseline justify-between">
            <Text className="font-serif text-base font-semibold text-ink">最近知识</Text>
            <Pressable onPress={() => router.push("/note")}>
              <Text className="text-[11px] text-accent">查看全部</Text>
            </Pressable>
          </View>
          <View className="rounded-xl border border-line bg-white">
            {loading ? (
              <View className="items-center py-8">
                <ActivityIndicator color="#6f675b" />
              </View>
            ) : notes.length === 0 ? (
              <Text className="px-4 py-8 text-center text-sm text-muted">
                还没有知识，开始记录吧
              </Text>
            ) : (
              notes.slice(0, 5).map((note, i) => (
                <Pressable
                  key={note.id}
                  onPress={() => router.push(`/note?id=${note.id}`)}
                  className={`flex-row items-center gap-3 px-4 py-3 ${
                    i > 0 ? "border-t border-line" : ""
                  }`}
                >
                  <Icon name="file" size={18} color="#8c8273" />
                  <View className="min-w-0 flex-1">
                    <Text className="text-sm text-ink" numberOfLines={1}>
                      {note.title || "无标题"}
                    </Text>
                    <Text className="mt-0.5 text-[11px] text-muted2">
                      {timeAgo(note.date)}
                    </Text>
                  </View>
                  <View className="rounded bg-brand-soft px-2 py-0.5">
                    <Text className="text-[10px] font-medium text-accent">已同步</Text>
                  </View>
                </Pressable>
              ))
            )}
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
