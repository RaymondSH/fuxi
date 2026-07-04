"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import TypeBadge from "@/components/TypeBadge";
import { ApiError } from "@/lib/api";
import { streamQa, type QaStyle } from "@/lib/sse";
import type { NoteType } from "@/lib/types";

interface Source {
  id: string;
  title: string;
  type: NoteType;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  generated?: boolean; // true=GLM 生成；false=缺密钥/调用失败降级
  style?: QaStyle; // 该条回答使用的风格（回显用）
  plan?: string[];
  verification?: { status: string; message: string };
}

const SUGGESTIONS = [
  "混合检索比单路能提升多少召回？",
  "亿级向量在 pgvector 上要注意什么？",
  "长上下文会取代 RAG 吗？",
];

// 角色化输出风格选项（label 展示 / value 对齐后端 QaStyle 枚举）
const STYLES: { value: QaStyle; label: string }[] = [
  { value: "default", label: "默认" },
  { value: "executive", label: "高管简报" },
  { value: "technical", label: "技术说明" },
  { value: "eli5", label: "通俗讲解" },
];

// 极简 Markdown：转义后把 **加粗** 变 <strong>
function renderText(text: string): string {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export default function QaPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [style, setStyle] = useState<QaStyle>("default");
  const [agentic, setAgentic] = useState(false);
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const messageSeq = useRef(0);

  // 在流式生成过程中持续滚动到底部（逐 token 增长时跟进）
  function scrollToBottom() {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }

  async function ask(question: string) {
    const q = question.trim();
    if (!q || thinking) return;

    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    const curStyle = style;
    const userId = `user-${++messageSeq.current}`;
    const assistantId = `assistant-${++messageSeq.current}`;
    // 先把用户消息 + 一条空的 assistant 占位（流式回答会逐字填进去）入列
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", text: q },
      { id: assistantId, role: "assistant", text: "", style: curStyle },
    ]);
    setInput("");
    setThinking(true);
    setTimeout(scrollToBottom, 50);

    try {
      await streamQa(q, history, {
        onPlan: (plan) => {
          setMessages((prev) => prev.map(
            (message) => message.id === assistantId ? { ...message, plan } : message
          ));
        },
        onSources: (sources) => {
          setMessages((prev) => prev.map(
            (message) => message.id === assistantId ? { ...message, sources } : message
          ));
          setTimeout(scrollToBottom, 50);
        },
        onToken: (text) => {
          setMessages((prev) => prev.map(
            (message) => message.id === assistantId
              ? { ...message, text: message.text + text }
              : message
          ));
          scrollToBottom();
        },
        onDone: (generated, maskedAnswer) => {
          setMessages((prev) => prev.map(
            (message) => message.id === assistantId
              ? {
                  ...message,
                  generated,
                  text: maskedAnswer ?? message.text,
                }
              : message
          ));
        },
        onVerification: (verification) => {
          setMessages((prev) => prev.map(
            (message) => message.id === assistantId
              ? { ...message, verification }
              : message
          ));
        },
      }, curStyle, agentic);
    } catch (err) {
      // 流建立前的错误（429 超额 / 401 未登录等）：替换占位为错误文案
      const msg = err instanceof ApiError ? err.message : "请求失败";
      setMessages((prev) => prev.map(
        (message) => message.id === assistantId
          ? { ...message, text: message.text || msg }
          : message
      ));
    } finally {
      setThinking(false);
      setTimeout(scrollToBottom, 50);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-8 py-8">
      <header className="mb-4">
        <h1 className="font-serif text-2xl font-semibold text-ink">问答</h1>
        <p className="mt-1 text-sm text-muted">基于知识库提问，回答附带来源。</p>
      </header>

      {/* 对话区 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 && !thinking && (
          <div className="mt-10 flex flex-col items-center gap-3">
            <p className="text-sm text-muted2">试试这些问题：</p>
            <div className="flex flex-col items-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="rounded-full border border-line bg-white px-4 py-1.5 text-sm text-muted transition-colors hover:border-brand hover:text-accent"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4">
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-ink px-4 py-2.5 text-sm text-cream">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex flex-col gap-2">
                {m.plan && (
                  <div className="font-mono text-[11px] text-muted2">
                    深度检索：{m.plan.join(" · ")}
                  </div>
                )}
                {/* 流式占位：还没收到任何 token 与来源时显示「思考中…」 */}
                {!m.text && (!m.sources || m.sources.length === 0) ? (
                  <div className="rounded-2xl rounded-bl-sm bg-panel px-4 py-3 text-sm text-muted2">
                    思考中…
                  </div>
                ) : (
                  <div
                    className="max-w-[90%] rounded-2xl rounded-bl-sm bg-panel px-4 py-3 text-sm leading-relaxed text-ink [&_strong]:font-semibold"
                    dangerouslySetInnerHTML={{ __html: renderText(m.text) }}
                    style={{ whiteSpace: "pre-wrap" }}
                  />
                )}
                {m.sources && m.sources.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pl-1">
                    <span className="font-mono text-[11px] text-muted2">
                      {m.sources.length} 条来源
                    </span>
                    {m.style && m.style !== "default" && (
                      <span className="rounded-full bg-white px-1.5 py-0.5 font-mono text-[10px] text-muted2">
                        {STYLES.find((s) => s.value === m.style)?.label ?? m.style}
                      </span>
                    )}
                    {m.sources.map((s) => (
                      <Link
                        key={s.id}
                        href={`/notes/${s.id}`}
                        className="inline-flex items-center gap-1 rounded-full border border-line bg-white px-2 py-0.5 text-xs text-muted transition-colors hover:border-brand hover:text-accent"
                      >
                        <TypeBadge type={s.type} />
                        <span className="max-w-[160px] truncate">{s.title}</span>
                      </Link>
                    ))}
                  </div>
                )}
                {m.verification && (
                  <div className={`text-xs ${m.verification.status === "supported" ? "text-green-700" : "text-amber-700"}`}>
                    引用校验：{m.verification.message}
                  </div>
                )}
              </div>
            ),
          )}
        </div>
      </div>

      {/* 风格选择 + 输入框 */}
      <div className="mt-4">
        <label className="mb-2 flex items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={agentic} onChange={(e) => setAgentic(e.target.checked)} />
          深度问答（问题拆解、重排与引用校验）
        </label>
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 font-mono text-[11px] uppercase tracking-wider text-muted2">
            风格
          </span>
          {STYLES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setStyle(s.value)}
              className={`rounded-full px-3 py-1 text-xs transition-colors ${
                style === s.value
                  ? "border border-brand bg-brand-soft text-accent"
                  : "border border-line bg-white text-muted hover:border-brand hover:text-accent"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="问一个问题…"
            className="flex-1 rounded-lg border border-line bg-white px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted2 focus:border-brand"
          />
          <button
            type="submit"
            disabled={thinking || !input.trim()}
            className="rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
          >
            发送
          </button>
        </form>
      </div>
    </div>
  );
}
