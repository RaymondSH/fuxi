"""Q&A 生成 Worker：针对一篇笔记自动生成问答对并回灌检索库。

  读笔记(db) → LLM 生成问答对(glm.generate_qa) → 问题向量化(embedder) → 写 generated_qa

镜像 ingest_worker 的两段式入口：
  enqueue_qa_gen   建 qa_gen job，返回 note_id；处理交给 run()
  run              后台跑生成流程，供独立 job_runner 调用

回灌：qa._retrieve 检索时取 generated_qa 余弦 top-2 拼进 context，
让模型能复用历史沉淀的问答（同义问题不必每次重新推一遍）。
"""
from __future__ import annotations

import json
import uuid

from db import pool
from services import embedder, llm, quota, usage
from services.logging import get_logger

log = get_logger("qa_gen")

# 每篇笔记生成问答对的上限（避免内容过少时硬凑，由 LLM 按内容自然决定 3-5 条）


# ---------- 两段式入口 ----------

def enqueue_qa_gen(
    note_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """建一条 qa_gen job，返回 note_id；处理交给 run()。"""
    with pool.connection() as conn:
        # 同一笔记重跑时先清掉旧的 queued/running job，避免卡片串台
        conn.execute(
            "DELETE FROM jobs WHERE job_type = 'qa_gen' AND note_id = %s "
            "AND status IN ('queued', 'running')",
            (note_id,),
        )
        conn.execute(
            "INSERT INTO jobs (job_type, note_id, payload, status, stage, progress) "
            "VALUES ('qa_gen', %s, %s::jsonb, 'queued', 'queued', 0)",
            (note_id, json.dumps({
                "actor_id": str(actor_id) if actor_id else None,
            })),
        )
    return note_id


def run(note_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> None:
    """后台执行生成流程。供独立 job_runner 调用。

    actor_id 是触发生成的用户；本次生成消耗的 GLM token 会记进该用户的 token_usage。
    """
    _process(note_id, actor_id=actor_id)


# ---------- 主流程 ----------

def _process(note_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> None:
    log.info("qa_gen start", extra={"event": "qa_gen_start", "note_id": str(note_id)})
    try:
        _update_job(note_id, status="running", stage="fetch", progress=10)

        # 用量采集包住 LLM 生成 + 问题向量化，按 actor_id 落 token_usage。
        with usage.collect() as u:
            note = _fetch_note(note_id)
            if not note:
                raise ValueError("笔记不存在")
            title, summary, content = note
            if not (content or "").strip():
                raise ValueError("笔记正文为空，无法生成问答")

            _update_job(note_id, stage="refine", progress=40)
            result = llm.generate_qa(content, title_hint=title or summary or "")
            if not result.items:
                raise ValueError("LLM 未生成任何问答对")

            _update_job(note_id, stage="embedding", progress=75)
            # 每条问答的问题向量化，回灌检索时按余弦相似召回
            qa_with_vec = []
            for item in result.items:
                vec = embedder.embed(item.question)
                qa_with_vec.append((item.question, item.answer, vec))

        # 写操作：把用量记到触发者账上（脚本/迁移无 actor_id 不记账）
        if actor_id is not None:
            quota.record_usage(actor_id, "qa_gen", u)

        _update_job(note_id, stage="store", progress=90)
        _save(note_id, qa_with_vec)

        _update_job(note_id, status="done", stage="done", progress=100)
        log.info("qa_gen done", extra={"event": "qa_gen_done", "note_id": str(note_id),
                                       "count": len(qa_with_vec)})
    except Exception as exc:  # noqa: BLE001 — 生成失败记到 job，不抛断请求
        _update_job(note_id, status="failed", error=str(exc))
        log.exception("qa_gen failed", extra={"event": "qa_gen_failed", "note_id": str(note_id)})


# ---------- 读写 ----------

def _fetch_note(note_id: uuid.UUID):
    """取笔记的标题/摘要/正文（生成问答的原料）。"""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT title, COALESCE(summary,''), COALESCE(content,'') "
            "FROM notes WHERE id = %s AND deleted_at IS NULL",
            (note_id,),
        ).fetchone()
    return row


def _save(note_id: uuid.UUID, qa_with_vec: list[tuple[str, str, list[float]]]) -> None:
    """写 generated_qa：先删该笔记的旧问答（只留最新一批），再逐条插入。"""
    with pool.connection() as conn:
        conn.execute("DELETE FROM generated_qa WHERE note_id = %s", (note_id,))
        if not qa_with_vec:
            return
        for question, answer, vec in qa_with_vec:
            conn.execute(
                "INSERT INTO generated_qa (note_id, question, answer, embedding) "
                "VALUES (%s, %s, %s, %s::vector)",
                (note_id, question, answer, vec),
            )


# ---------- jobs 读写 ----------

def _update_job(
    note_id,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    error: str | None = None,
) -> None:
    """按需更新该笔记的 qa_gen job；用 note_id + job_type 定位。"""
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
    vals.append(note_id)
    with pool.connection() as conn:
        conn.execute(
            f"UPDATE jobs SET {', '.join(sets)} "
            "WHERE job_type = 'qa_gen' AND note_id = %s "
            "AND status IN ('queued', 'running')",
            vals,
        )
