// SSE 流式问答封装。移植自 frontend/lib/sse.ts，适配 react-native-sse。
//
// react-native-sse 的 EventSource 支持 POST + 自定义 headers + Bearer token，
// 解决了 RN fetch 不支持 ReadableStream body 读取的问题。
//
// 后端 /qa/stream 事件序：sources → token(多次) → done。

import EventSource from "react-native-sse";

import { BASE, getAccessToken } from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { NoteType } from "@/lib/types";

export type QaStyle = "default" | "executive" | "technical" | "eli5";

export interface QaStreamSource {
  id: string;
  title: string;
  type: NoteType;
}

export interface QaStreamHandlers {
  onSources: (sources: QaStreamSource[]) => void;
  onToken: (text: string) => void;
  onDone: (generated: boolean, maskedAnswer?: string) => void;
  onError?: (message: string) => void;
}

const CHAT_STORAGE = "fuxi_mobile_chat";

export function chatStorageKey(): string {
  return CHAT_STORAGE;
}

// 一次问答流：POST /qa/stream，按 SSE 事件回调驱动前端渲染。
// 抛 ApiError 表示请求未建立（如 429 超额、401 未登录）。
// 自定义 SSE 事件名：sources / token / done（与后端 /qa/stream 协议对齐）
export type QaEvents = "sources" | "token" | "done";

export async function streamQa(
  question: string,
  history: { role: string; text: string }[],
  handlers: QaStreamHandlers,
  style: QaStyle = "default",
): Promise<EventSource<QaEvents> | null> {
  const token = getAccessToken();
  if (!token) throw new ApiError("unauthorized", "未登录", 401);

  const body = JSON.stringify({ question, history, style });

  const es = new EventSource<QaEvents>(`${BASE}/qa/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body,
    pollingInterval: 0, // 不自动重连，流式问答是一次性的
  });

  let completed = false;

  es.addEventListener("sources", (e) => {
    try {
      const arr = JSON.parse(e.data || "[]");
      handlers.onSources(arr);
    } catch {
      /* 单事件解析失败不影响后续 */
    }
  });

  es.addEventListener("token", (e) => {
    try {
      const obj = JSON.parse(e.data || "{}");
      if (obj.text) handlers.onToken(obj.text);
    } catch {
      /* ignore */
    }
  });

  es.addEventListener("done", (e) => {
    completed = true;
    try {
      const obj = JSON.parse(e.data || "{}");
      handlers.onDone(
        Boolean(obj.generated),
        typeof obj.masked_answer === "string" ? obj.masked_answer : undefined,
      );
    } catch {
      handlers.onDone(false);
    }
    es.close();
  });

  es.addEventListener("error", (e) => {
    if (completed) return; // done 后的 error 忽略
    // react-native-sse 在网络错误时返回 event；消息可能为 undefined
    const msg = (e as { message?: string }).message || "问答流意外中断";
    handlers.onError?.(msg);
    es.close();
  });

  return es;
}
