"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import TypeBadge from "@/components/TypeBadge";
import { canAct, useSpaces } from "@/components/SpacesProvider";
import { apiGet, apiPost, apiUpload, ApiError } from "@/lib/api";
import type { IngestJob, IngestStage } from "@/lib/types";

const STAGE_LABEL: Record<IngestStage, string> = {
  queued: "排队",
  fetch: "抓取",
  extract: "解析",
  refine: "提炼",
  chunk: "分块",
  embedding: "向量化",
  store: "写库",
  done: "完成",
};

const STATUS_META: Record<
  IngestJob["status"],
  { label: string; color: string }
> = {
  pending: { label: "等待", color: "#8C8273" },
  processing: { label: "处理中", color: "#9A4A2F" },
  done: { label: "完成", color: "#4E7A4E" },
  failed: { label: "失败", color: "#B23C3C" },
};

export default function IngestPage() {
  const { spaces, activeSpace } = useSpaces();
  const targetSpace = activeSpace && canAct(activeSpace.my_role, "editor")
    ? activeSpace
    : spaces.find((s) => canAct(s.my_role, "editor")) || null;
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadJobs = useCallback(async () => {
    try {
      const data = await apiGet<{ items: IngestJob[] }>("/ingest/jobs");
      setJobs(data.items);
    } catch {
      /* 轮询失败静默，下次再试 */
    }
  }, []);

  // 进入页面拉一次，之后每 1.5s 轮询进度
  useEffect(() => {
    loadJobs();
    const t = setInterval(loadJobs, 1500);
    return () => clearInterval(t);
  }, [loadJobs]);

  async function submitUrl(e: React.FormEvent) {
    e.preventDefault();
    const v = url.trim();
    if (!v) return;
    setSubmitting(true);
    setError("");
    try {
      if (!targetSpace) throw new ApiError("forbidden", "没有可入库的空间", 403);
      await apiPost("/ingest/url", { url: v, space_id: targetSpace.id });
      setUrl("");
      loadJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitFile(file: File) {
    setSubmitting(true);
    setError("");
    try {
      if (!targetSpace) throw new ApiError("forbidden", "没有可入库的空间", 403);
      // 后端 /ingest/file 不读 JSON body（multipart），space_id 通过查询参数传
      await apiUpload(`/ingest/file?space_id=${targetSpace.id}`, file);
      loadJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setSubmitting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <header className="mb-8">
        <h1 className="font-serif text-2xl font-semibold text-ink">入库</h1>
        <p className="mt-1 text-sm text-muted">
          粘贴链接或上传文件，自动抓取、提炼摘要与要点、写入知识库。
        </p>
        {targetSpace && (
          <p className="mt-1 font-mono text-xs text-muted2">
            目标空间：{targetSpace.name}
          </p>
        )}
      </header>

      {/* 链接入库 */}
      <form onSubmit={submitUrl} className="flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="粘贴链接 https://…（网页 / 公众号）"
          className="flex-1 rounded-lg border border-line bg-white px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted2 focus:border-brand"
        />
        <button
          type="submit"
          disabled={submitting || !url.trim()}
          className="rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
        >
          入库
        </button>
      </form>

      {/* 文件入库 */}
      <div className="mt-3">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={submitting}
          className="rounded-lg border border-dashed border-line bg-panel px-4 py-2 text-sm text-muted transition-colors hover:border-brand hover:text-accent disabled:opacity-40"
        >
          ＋ 上传文件（PDF / Word / Excel / 图片）
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) submitFile(f);
          }}
        />
      </div>

      {error && <p className="mt-3 text-sm text-[#B23C3C]">{error}</p>}

      {/* 入库队列 */}
      <section className="mt-10">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted2">
          入库队列
        </h2>
        {jobs.length === 0 ? (
          <p className="rounded-lg border border-line bg-panel px-4 py-8 text-center text-sm text-muted2">
            还没有入库任务
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {jobs.map((job) => {
              const st = STATUS_META[job.status];
              return (
                <li
                  key={job.id}
                  className="rounded-lg border border-line bg-white px-4 py-3"
                >
                  <div className="flex items-center gap-2">
                    <TypeBadge type={job.type} />
                    <span className="flex-1 truncate text-sm font-medium text-ink">
                      {job.title}
                    </span>
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: st.color }}
                    >
                      {st.label}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-3 pl-1 text-xs text-muted2">
                    <span className="truncate">{job.sub}</span>
                  </div>
                  {/* 进度条 */}
                  <div className="mt-2 flex items-center gap-3">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${job.progress}%`,
                          background:
                            job.status === "failed" ? "#B23C3C" : "#B25B3C",
                        }}
                      />
                    </div>
                    <span className="w-16 shrink-0 text-right font-mono text-[11px] text-muted">
                      {job.status === "failed"
                        ? "失败"
                        : STAGE_LABEL[job.stage]}
                    </span>
                  </div>
                  {job.error_msg && (
                    <p className="mt-1.5 text-xs text-[#B23C3C]">
                      {job.error_msg}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
