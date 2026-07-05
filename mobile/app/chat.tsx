// AI 对话页：SSE 流式问答 + 气泡渲染 + 停止生成。
// 对齐设计稿 renderChat / doChatStream：
//   - 用户气泡右对齐，AI 气泡左对齐
//   - SSE 事件序：sources（先显示来源 chip）→ token（逐字追加）→ done
//   - 流式中可点「停止」中断
//   - 历史对话存 AsyncStorage（设计稿用 sessionStorage，RN 改用 AsyncStorage）

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
import * as SecureStore from "expo-secure-store";

import { AppBar } from "@/components/AppBar";
import { Icon } from "@/components/Icons";
import { useSnack } from "@/contexts/SnackProvider";
import { ApiError } from "@/lib/api";
import { streamQa, type QaStreamSource, type QaEvents } from "@/lib/sse";
import type EventSource from "react-native-sse";

const CHAT_KEY = "fuxi_mobile_chat";

interface ChatMessage {
  role: "user" | "ai";
  text: string;
  sources?: QaStreamSource[];
}

const WELCOME: ChatMessage = {
  role: "ai",
  text:
    "你好！我是 fuxi AI 助手。我可以回答你关于知识库的问题，引用笔记中的内容来提供准确的答案。试试问我关于你的研究或笔记的内容。",
};

export default function ChatScreen() {
  const { notify } = useSnack();
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingSources, setStreamingSources] = useState<QaStreamSource[]>([]);
  const scrollRef = useRef<ScrollView>(null);
  const esRef = useRef<EventSource<"sources" | "token" | "done"> | null>(null);

  // 加载历史对话
  useEffect(() => {
    (async () => {
      try {
        const raw = await SecureStore.getItemAsync(CHAT_KEY);
        if (raw) {
          const arr = JSON.parse(raw) as ChatMessage[];
          if (Array.isArray(arr) && arr.length > 0) {
            setMessages(arr);
          }
        }
      } catch {
        /* ignore */
      }
    })();
  }, []);

  const persist = useCallback(async (msgs: ChatMessage[]) => {
    try {
      await SecureStore.setItemAsync(CHAT_KEY, JSON.stringify(msgs));
    } catch {
      /* ignore */
    }
  }, []);

  const scrollToEnd = useCallback(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
  }, []);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");

    const next: ChatMessage[] = [...messages, { role: "user", text }];
    setMessages(next);
    setStreaming(true);
    setStreamingText("");
    setStreamingSources([]);
    scrollToEnd();

    const history = next.map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      text: m.text,
    }));

    try {
      const es = await streamQa(text, history, {
        onSources: (sources) => {
          setStreamingSources(sources);
          scrollToEnd();
        },
        onToken: (chunk) => {
          setStreamingText((prev) => prev + chunk);
          scrollToEnd();
        },
        onDone: () => {
          const finalText = streamingTextRef.current;
          const finalSources = streamingSourcesRef.current;
          const completed: ChatMessage = {
            role: "ai",
            text: finalText,
            sources: finalSources,
          };
          const all = [...next, completed];
          setMessages(all);
          persist(all);
          setStreaming(false);
          setStreamingText("");
          setStreamingSources([]);
          scrollToEnd();
        },
        onError: (msg) => {
          notify(msg || "对话失败");
          setStreaming(false);
          setStreamingText("");
          setStreamingSources([]);
        },
      });
      esRef.current = es;
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "对话失败");
      setStreaming(false);
      setStreamingText("");
      setStreamingSources([]);
    }
  }

  // refs 用于 onDone 闭包内拿到最新流式文本（避免 stale closure）
  const streamingTextRef = useRef("");
  const streamingSourcesRef = useRef<QaStreamSource[]>([]);
  useEffect(() => {
    streamingTextRef.current = streamingText;
  }, [streamingText]);
  useEffect(() => {
    streamingSourcesRef.current = streamingSources;
  }, [streamingSources]);

  function stop() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    // 已生成的部分作为 AI 回复保留
    const partial = streamingTextRef.current;
    if (partial) {
      const completed: ChatMessage = {
        role: "ai",
        text: partial,
        sources: streamingSourcesRef.current,
      };
      const all = [...messages, completed];
      setMessages(all);
      persist(all);
    }
    setStreaming(false);
    setStreamingText("");
    setStreamingSources([]);
  }

  return (
    <View className="flex-1 bg-cream">
      <AppBar title="AI 对话" subtitle={`${messages.length - 1} 轮对话`} />

      <KeyboardAvoidingView
        className="flex-1"
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          ref={scrollRef}
          className="flex-1"
          contentContainerClassName="px-4 pb-4 pt-3"
        >
          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <View key={i} className="mb-3 flex-row justify-end">
                <View className="max-w-[80%] rounded-2xl bg-ink px-3.5 py-2.5">
                  <Text className="text-sm text-cream">{msg.text}</Text>
                </View>
              </View>
            ) : (
              <View key={i} className="mb-3 flex-row justify-start">
                <View className="max-w-[88%] rounded-2xl border border-line bg-white px-3.5 py-2.5">
                  {msg.sources && msg.sources.length > 0 ? (
                    <View className="mb-2 flex-row flex-wrap gap-1.5">
                      {msg.sources.map((s, j) => (
                        <View
                          key={j}
                          className="rounded-full bg-brand-soft px-2 py-0.5"
                        >
                          <Text className="text-[10px] text-accent" numberOfLines={1}>
                            {s.title || s.id}
                          </Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                  <Text className="mb-1 text-[10px] font-semibold text-muted">AI</Text>
                  <Text className="text-sm text-ink">{msg.text}</Text>
                </View>
              </View>
            ),
          )}

          {streaming ? (
            <View className="mb-3 flex-row justify-start">
              <View className="max-w-[88%] rounded-2xl border border-line bg-white px-3.5 py-2.5">
                {streamingSources.length > 0 ? (
                  <View className="mb-2 flex-row flex-wrap gap-1.5">
                    {streamingSources.map((s, j) => (
                      <View key={j} className="rounded-full bg-brand-soft px-2 py-0.5">
                        <Text className="text-[10px] text-accent" numberOfLines={1}>
                          {s.title || s.id}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
                <Text className="mb-1 text-[10px] font-semibold text-muted">AI</Text>
                {streamingText ? (
                  <Text className="text-sm text-ink">{streamingText}</Text>
                ) : (
                  <View className="flex-row items-center gap-2 py-1">
                    <ActivityIndicator size="small" color="#6f675b" />
                    <Text className="text-xs text-muted">思考中…</Text>
                  </View>
                )}
              </View>
            </View>
          ) : null}
        </ScrollView>

        {/* composer */}
        <View className="border-t border-line bg-white px-3 py-2">
          {streaming ? (
            <Pressable
              onPress={stop}
              className="flex-row items-center justify-center gap-2 rounded-xl bg-[#B23C3C] py-3"
            >
              <Icon name="close" size={16} color="#fbf1e9" />
              <Text className="text-sm font-medium text-cream">停止生成</Text>
            </Pressable>
          ) : (
            <View className="flex-row items-end gap-2">
              <TextInput
                value={input}
                onChangeText={setInput}
                placeholder="继续提问…"
                placeholderTextColor="#8c8273"
                multiline
                className="max-h-[100px] min-h-[40px] flex-1 rounded-xl border border-line bg-cream px-3 py-2 text-sm text-ink"
              />
              <Pressable
                onPress={send}
                disabled={!input.trim()}
                className="h-10 w-10 items-center justify-center rounded-xl bg-brand disabled:opacity-40"
              >
                <Icon name="send" size={18} color="#fbf1e9" />
              </Pressable>
            </View>
          )}
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}
