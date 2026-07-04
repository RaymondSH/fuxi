// SSE 流式请求：浏览器原生 EventSource 只支持 GET，无法带 body / 自定义头，
// 故问答的 POST /qa/stream 用 fetch + ReadableStream 手动解析 SSE 事件流。
//
// SSE 帧格式：以空行分隔的「事件块」，每块由若干行 `event:` / `data:` 组成。
// 后端 /qa/stream 的事件序：sources → token(多次) → done。
// 文档约定见 docs/api-contract.md 与 backend/routers/qa.py。

import { ApiError, refreshAccess } from "@/lib/api";
import type { NoteType } from "@/lib/types";

const BASE = "/api";

export type QaStyle = "default" | "executive" | "technical" | "eli5";

export interface QaStreamSource {
  id: string;
  title: string;
  type: NoteType;
}

export interface QaStreamHandlers {
  onPlan?: (queries: string[]) => void;
  /** 检索到的来源（在回答前一次性给出）。 */
  onSources: (sources: QaStreamSource[]) => void;
  /** 逐块生成的回答文本，前端逐字拼到当前消息末尾。 */
  onToken: (text: string) => void;
  /** 流结束；generated=false 表示缺密钥/调用失败的降级。 */
  onDone: (generated: boolean, maskedAnswer?: string) => void;
  onVerification?: (result: { status: string; message: string }) => void;
}

// 一次问答流：POST /qa/stream，按 SSE 事件回调驱动前端渲染。
// 抛 ApiError 表示请求未建立（如 429 超额、401 未登录）；流建立后的错误走 onDone(false)。
export async function streamQa(
  question: string,
  history: { role: string; text: string }[],
  handlers: QaStreamHandlers,
  style: QaStyle = "default",
  agentic = false,
): Promise<void> {
  const open = () => fetch(`${BASE}${agentic ? "/qa/agentic/stream" : "/qa/stream"}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ question, history, style }),
    });
  let res = await open();
  if (res.status === 401) {
    await refreshAccess();
    res = await open();
  }

  if (!res.ok) {
    // 超额(429)/未登录(401) 等在开流前返回普通错误体，沿用 api 的错误解析
    let code = "http_error";
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      } else if (typeof body?.detail === "string") {
        message = body.detail;
      }
    } catch {
      /* 非 JSON 错误体，沿用状态码 */
    }
    if (res.status === 429) code = "rate_limited";
    throw new ApiError(code, message, res.status);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("浏览器不支持流式响应");

  const decoder = new TextDecoder();
  let buffer = ""; // 跨 chunk 的不完整事件块
  let completed = false;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 允许 CRLF / LF / CR 三种换行；逐块取出完整事件，剩余留在 buffer。
    // 不能预先替换 chunk 末尾的 \r，否则 CRLF 恰好跨 chunk 时会被误判成空行。
    let boundary: RegExpExecArray | null;
    while ((boundary = /\r\n\r\n|\n\n|\r\r/.exec(buffer)) !== null) {
      const raw = buffer.slice(0, boundary.index);
      buffer = buffer.slice(boundary.index + boundary[0].length);
      const evt = parseEvent(raw);
      if (!evt) continue;
      dispatch(evt.event, evt.data, handlers);
      if (evt.event === "done") completed = true;
    }
  }
  if (!completed) throw new Error("问答流意外中断");
}

interface SseEvent {
  event: string;
  data: string;
}

// 解析一个事件块：行形如 `event: xxx` / `data: yyy`，data 可跨多行（用 \n 连接）。
function parseEvent(raw: string): SseEvent | null {
  let event = "message";
  const dataParts: string[] = [];
  for (const line of raw.split(/\r\n|\n|\r/)) {
    if (!line || line.startsWith(":")) continue; // 空行或注释行
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    // 冒号后若紧跟空格则跳过它（SSE 规范）
    let val = idx === -1 ? "" : line.slice(idx + 1);
    if (val.startsWith(" ")) val = val.slice(1);
    if (field === "event") event = val;
    else if (field === "data") dataParts.push(val);
  }
  if (event === "message" && dataParts.length === 0) return null;
  return { event, data: dataParts.join("\n") };
}

function dispatch(event: string, data: string, h: QaStreamHandlers): void {
  try {
    if (event === "sources") {
      const arr = JSON.parse(data || "[]");
      h.onSources(arr);
    } else if (event === "plan") {
      const obj = JSON.parse(data || "{}");
      h.onPlan?.(obj.queries || []);
    } else if (event === "token") {
      const obj = JSON.parse(data || "{}");
      if (obj.text) h.onToken(obj.text);
    } else if (event === "done") {
      const obj = JSON.parse(data || "{}");
      h.onDone(
        Boolean(obj.generated),
        typeof obj.masked_answer === "string" ? obj.masked_answer : undefined,
      );
    } else if (event === "verification") {
      h.onVerification?.(JSON.parse(data || "{}"));
    }
  } catch {
    /* 单个事件解析失败不影响后续流 */
  }
}
