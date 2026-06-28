"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import TypeBadge from "@/components/TypeBadge";
import { apiPost, ApiError } from "@/lib/api";
import type { NoteType } from "@/lib/types";

interface Source {
  id: string;
  title: string;
  type: NoteType;
}

interface Message {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  generated?: boolean;
}

interface QaResponse {
  answer: string;
  sources: Source[];
  generated: boolean;
}

const SUGGESTIONS = [
  "混合检索比单路能提升多少召回？",
  "亿级向量在 pgvector 上要注意什么？",
  "长上下文会取代 RAG 吗？",
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
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || thinking) return;

    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setThinking(true);
    setTimeout(() => scrollRef.current?.scrollTo(0, 1e9), 50);

    try {
      const resp = await apiPost<QaResponse>("/qa", { question: q, history });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: resp.answer,
          sources: resp.sources,
          generated: resp.generated,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: err instanceof ApiError ? err.message : "请求失败",
        },
      ]);
    } finally {
      setThinking(false);
      setTimeout(() => scrollRef.current?.scrollTo(0, 1e9), 50);
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
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-ink px-4 py-2.5 text-sm text-cream">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={i} className="flex flex-col gap-2">
                <div
                  className="max-w-[90%] rounded-2xl rounded-bl-sm bg-panel px-4 py-3 text-sm leading-relaxed text-ink [&_strong]:font-semibold"
                  dangerouslySetInnerHTML={{ __html: renderText(m.text) }}
                  style={{ whiteSpace: "pre-wrap" }}
                />
                {m.sources && m.sources.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pl-1">
                    <span className="font-mono text-[11px] text-muted2">
                      {m.sources.length} 条来源
                    </span>
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
              </div>
            ),
          )}

          {thinking && (
            <div className="flex">
              <div className="rounded-2xl rounded-bl-sm bg-panel px-4 py-3 text-sm text-muted2">
                思考中…
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 输入框 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="mt-4 flex gap-2"
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
  );
}
