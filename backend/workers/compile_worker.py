"""主题页编译 Worker：把多篇笔记综合成一篇结构化 Wiki 主题页。

  取来源笔记(db) → LLM 综合(llm.compile_wiki) → 写 wiki_pages(sections/conflict/summary)

镜像 ingest_worker 的两段式入口：
  enqueue_compile   建 wiki_pages 占位行 + 一条 compile job，返回 slug
  run               后台跑编译流程，供独立 job_runner 调用

wiki_pages 行在编译期间 compiled_at 为空（前端可据此显示「编译中」），编译完写回。
"""
from __future__ import annotations

import json
import re
import uuid

from db import pool
from services import embedder, llm, quota, usage
from services.logging import get_logger

log = get_logger("compile")

# 主题页编译流水线阶段（复用 jobs.stage，但编译走自己的进度语义）
# fetch=取来源 / compile=LLM 综合 / embedding=主题页向量 / done=完成


def _default_space_id() -> uuid.UUID:
    """取 default 空间 id（脚本/迁移编译无显式 space 时落 default）。"""
    with pool.connection() as conn:
        row = conn.execute("SELECT id FROM spaces WHERE is_default").fetchone()
    if not row:
        raise RuntimeError("default 空间不存在，请先跑 sql/18_spaces.sql")
    return row[0]


def compile_sync(slug: str, title: str, source_note_ids: list[uuid.UUID], space_id: uuid.UUID | None = None) -> str:
    """同步跑完（脚本 / 迁移用），返回 slug。"""
    enqueue_compile(slug, title, source_note_ids, space_id=space_id)
    run(slug)
    return slug


def enqueue_compile(
    slug: str,
    title: str,
    source_note_ids: list[uuid.UUID],
    space_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> str:
    """建/更新 wiki_pages 占位行 + 一条 compile job，返回 slug。处理交给 run()。

    space_id 指定主题页归属空间（默认 default 空间，供脚本/迁移用）。
    """
    sid = space_id or _default_space_id()
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO wiki_pages (slug, title, source_note_ids, space_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE
                SET title = EXCLUDED.title,
                    source_note_ids = EXCLUDED.source_note_ids,
                    space_id = EXCLUDED.space_id,
                    sections = NULL,
                    conflict = NULL,
                    compiled_at = NULL
            """,
            (slug, title, source_note_ids, sid),
        )
        # 同一 slug 重编译时先清掉旧 job，避免卡片串台
        conn.execute(
            "DELETE FROM jobs WHERE job_type = 'compile' AND payload->>'slug' = %s AND status IN ('queued','running')",
            (slug,),
        )
        conn.execute(
            "INSERT INTO jobs (job_type, payload, status, progress) "
            "VALUES ('compile', %s, 'queued', 0)",
            (json.dumps({
                "slug": slug,
                "title": title,
                "actor_id": str(actor_id) if actor_id else None,
            }),),
        )
    return slug


def run(slug: str, *, actor_id: uuid.UUID | None = None) -> None:
    """后台执行编译流程。供独立 job_runner 调用。

    actor_id 是触发编译的用户；本次编译消耗的 GLM token 会记进该用户的 token_usage。
    脚本/迁移调用不传，则不记账。
    """
    _process(slug, actor_id=actor_id)


# ---------- 主流程 ----------

def _process(slug: str, *, actor_id: uuid.UUID | None = None) -> None:
    try:
        _update_job(slug, status="running", stage="fetch", progress=10)

        sources = _fetch_sources(slug)
        if not sources:
            raise ValueError("没有可用的来源笔记")
        _update_job(slug, stage="compile", progress=40)

        topic = _job_title(slug) or slug
        # 用量采集包住 LLM 综合 + 主题页向量化，按 actor_id 落 token_usage。
        with usage.collect() as u:
            result = llm.compile_wiki(sources, topic)
            _update_job(slug, stage="embedding", progress=80)

            # 主题页向量用概览摘要 + 各章节标题，便于主题页本身的语义检索
            section_titles = "；".join(s.heading for s in result.sections)
            vector_text = f"{result.summary}\n\n{section_titles}"[:2000]
            vector = embedder.embed(vector_text)

        # 写操作：把本次 GLM 用量记到触发者账上（看板可见 + 计额度）。
        # 脚本/迁移调用无 actor_id，不记账（token_usage.user_id 有 FK 约束，None 写不进）。
        if actor_id is not None:
            quota.record_usage(actor_id, "compile", u)

        _save(slug, result, vector)
        _update_job(slug, status="done", stage="done", progress=100)
    except Exception as exc:  # noqa: BLE001 — 编译失败记到 job，不抛断请求
        log.exception("wiki compile failed: slug=%s", slug)
        _update_job(slug, status="failed", error=str(exc))


def _fetch_sources(slug: str) -> list[dict]:
    """取该主题页来源笔记的 id/标题/摘要/正文（按 source_note_ids 顺序）。

    纵深防御：只取与主题页同空间的笔记。即便 source_note_ids 被串改进异空间 id，
    这里也不会读出来（API 层已校验同空间，这里是兜底）。
    """
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT source_note_ids, space_id FROM wiki_pages WHERE slug = %s", (slug,)
        ).fetchone()
        if not row or not row[0]:
            return []
        ids, space_id = row[0], row[1]
        rows = conn.execute(
            """
            SELECT id, title, COALESCE(summary,''), COALESCE(content,'')
            FROM notes WHERE id = ANY(%s) AND ingest_status = 'done' AND deleted_at IS NULL
              AND (%s IS NULL OR space_id = %s)
            """,
            (ids, space_id, space_id),
        ).fetchall()
    # 保持 source_note_ids 原始顺序
    by_id = {str(r[0]): r for r in rows}
    ordered = []
    for nid in ids:
        r = by_id.get(str(nid))
        if r:
            ordered.append({"id": str(r[0]), "title": r[1], "summary": r[2], "content": r[3]})
    return ordered


def _job_title(slug: str) -> str | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT title FROM wiki_pages WHERE slug = %s", (slug,)
        ).fetchone()
    return row[0] if row else None


def _save(slug: str, result, vector: list[float]) -> None:
    """把编译结果写回 wiki_pages：sections/conflict/summary/content/embedding/compiled_at。"""
    # content：纯文本 fallback（章节标题 + 段落正文拼成 Markdown）
    md_parts = []
    for sec in result.sections:
        md_parts.append(f"## {sec.heading}")
        for p in sec.paragraphs:
            md_parts.append(p.text)
    content_md = "\n\n".join(md_parts)

    sections_json = json.dumps(
        [s.model_dump() for s in result.sections], ensure_ascii=False
    )
    conflict_json = (
        json.dumps(result.conflict.model_dump(), ensure_ascii=False)
        if result.conflict
        else None
    )
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE wiki_pages SET
                sections   = %s::jsonb,
                conflict   = %s::jsonb,
                summary    = %s,
                content    = %s,
                embedding  = %s::vector,
                compiled_at = NOW()
            WHERE slug = %s
            """,
            (sections_json, conflict_json, result.summary, content_md, vector, slug),
        )


# ---------- jobs 读写 ----------

def _update_job(
    slug: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    error: str | None = None,
) -> None:
    """按需更新该 slug 的 compile job；用 payload->>'slug' 定位。"""
    sets: list[str] = []
    vals: list[object] = []
    for col, val in (
        ("status", status),
        ("stage", stage),
        ("progress", progress),
        ("error_msg", error),
    ):
        if val is not None:
            sets.append(f"{col} = %s")
            vals.append(val)
    if status == "running":
        sets.append("started_at = COALESCE(started_at, NOW())")
    if status in ("done", "failed"):
        sets.append("finished_at = NOW()")
    if not sets:
        return
    vals.append(slug)
    with pool.connection() as conn:
        conn.execute(
            f"UPDATE jobs SET {', '.join(sets)} "
            "WHERE job_type = 'compile' AND payload->>'slug' = %s "
            "AND status IN ('queued', 'running')",
            vals,
        )


def _slugify(text: str) -> str:
    """中文标题 → URL slug：保留中文/英文/数字，其余转连字符。"""
    text = text.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text, flags=re.UNICODE)
    return text.strip("-") or "topic"
