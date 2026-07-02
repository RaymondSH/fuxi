"""入库 Worker：把一个来源跑完整条入库链路。

  抓取(fetcher) → 提炼摘要/要点/标签/实体(glm) → 向量化(embedder) → 写库(notes/entities)

每条入库同时维护两份状态：
  notes.ingest_status  —  总状态（pending/processing/done/failed）
  jobs 表              —  细粒度 stage + progress，驱动前端「入库队列」进度卡片

对外入口：
  ingest_url / ingest_file        同步跑完（脚本 / 迁移用）
  enqueue_* + run                 拆成「建占位行 + 后台处理」，给 HTTP 接口用
"""
from __future__ import annotations

import hashlib
import json
import uuid
from urllib.parse import urlparse

from db import pool
from services import chunker, embedder, es, fetcher, llm, quota, storage, usage
from services.logging import get_logger

log = get_logger("ingest")

# 文件扩展名 → notes.source_type（入队时就定下来，前端角标立刻正确）
_EXT_SOURCE_TYPE = {
    "pdf": "pdf",
    "docx": "docx",
    "xlsx": "xlsx",
    "xls": "xlsx",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "webp": "image",
}

# source_type → 原始文件扩展名（落对象存储时用）
_SOURCE_EXT = {"pdf": "pdf", "docx": "docx", "xlsx": "xlsx", "image": "png"}


# ---------- 同步入口（脚本 / 迁移） ----------

def ingest_url(url: str, *, space_id=None, created_by=None) -> uuid.UUID:
    note_id = enqueue_url(url, space_id=space_id, created_by=created_by)
    run(note_id, url=url, space_id=space_id, actor_id=created_by)
    return note_id


def ingest_file(data: bytes, filename: str, *, space_id=None, created_by=None) -> uuid.UUID:
    note_id = enqueue_file(
        filename, len(data), data=data, space_id=space_id, created_by=created_by
    )
    run(note_id, data=data, filename=filename, space_id=space_id, actor_id=created_by)
    return note_id


# ---------- 拆两步，给 HTTP 接口用 ----------

def enqueue_url(url: str, *, space_id=None, created_by=None) -> uuid.UUID:
    """建一条 pending 笔记 + 一条 ingest job，返回 note_id；处理交给 run()。

    space_id/created_by（M2）：归属空间 + 入库者。脚本/迁移不传则留 NULL。
    """
    note_id = _create_pending(url=url, source_type="url", space_id=space_id, created_by=created_by)
    _create_job(
        note_id,
        title=url,
        sub=urlparse(url).netloc or url,
        payload={
            "kind": "url",
            "url": url,
            "actor_id": str(created_by) if created_by else None,
            "space_id": str(space_id) if space_id else None,
        },
    )
    return note_id


def enqueue_file(
    filename: str,
    size_bytes: int = 0,
    *,
    data: bytes,
    space_id=None,
    created_by=None,
) -> uuid.UUID:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    source_type = _EXT_SOURCE_TYPE.get(ext, "manual")
    note_id = _create_pending(url=f"file://{filename}", source_type=source_type, space_id=space_id, created_by=created_by)
    # 在返回 202 前先持久化上传内容；worker 重启后可从对象存储恢复任务。
    staged_key = f"{note_id}/raw.{ext or 'bin'}"
    storage.get_store().put(staged_key, data)
    _create_job(
        note_id,
        title=filename,
        sub=_human_size(size_bytes),
        payload={
            "kind": "file",
            "filename": filename,
            "staged_key": staged_key,
            "actor_id": str(created_by) if created_by else None,
            "space_id": str(space_id) if space_id else None,
        },
    )
    return note_id


def run(note_id: uuid.UUID, *, actor_id: uuid.UUID | None = None, space_id=None, **fetch_kwargs) -> None:
    """后台执行：抓取 → 提炼 → 向量化 → 写库。供独立 job_runner 调用。

    actor_id 是触发入库的用户；HTTP 接口传入后，本次入库消耗的 GLM token 会
    记进该用户的 token_usage（用量看板可见、并计入其每日额度）。脚本/迁移
    调用不传，则不记账。

    space_id 用于 ES 索引写入（notes 表的 space_id 在 enqueue_* 时已写入）；
    若 enqueue 未传（脚本场景）则从库里读已存的 space_id。
    """
    _process(note_id, actor_id=actor_id, space_id=space_id, **fetch_kwargs)


# ---------- 主流程 ----------

def _process(note_id: uuid.UUID, *, actor_id: uuid.UUID | None = None, space_id=None, **fetch_kwargs) -> None:
    log.info("ingest start", extra={"event": "ingest_start", "note_id": str(note_id), "actor_id": str(actor_id) if actor_id else None})
    try:
        _mark_status(note_id, "processing")
        _update_job(note_id, status="running", stage="fetch", progress=10)

        # 用量采集包住所有 LLM 调用（analyze / embed / 图片入库的 describe_image）。
        # ContextVar 在本线程内有效：fetch→analyze→embed 都在此线程跑，
        # provider 调用后 record_call 累加到 u；结束按 actor_id 落 token_usage。
        with usage.collect() as u:
            result = fetcher.fetch(**fetch_kwargs)
            if not result.content.strip():
                raise ValueError("抓取到的正文为空")
            # 抓到真实标题后回填到 job 卡片
            _update_job(note_id, title=result.title, stage="extract", progress=35)

            # 原始文件落对象存储（URL 来源无 raw_bytes，跳过）
            raw_path = _store_raw(note_id, result)

            _update_job(note_id, stage="refine", progress=55)
            analysis = llm.analyze(result.content, title_hint=result.title)

            # 长文档切块：逐块向量化写入 note_chunks（语义检索主召回路）
            _update_job(note_id, stage="chunk", progress=60)
            chunks = chunker.split(result.content)
            chunk_embeddings = [embedder.embed(c) for c in chunks]

            _update_job(note_id, stage="embedding", progress=75)
            # 文档级向量用「摘要 + 正文前段」，作概览/降级；chunk 级是主召回
            vector = embedder.embed(f"{analysis.summary}\n\n{result.content[:2000]}")

        # 入库是 admin 写操作：把本次 GLM 用量记到触发者账上（看板可见 + 计额度）。
        # 脚本/迁移调用无 actor_id，不记账（token_usage.user_id 有 FK 约束，None 写不进）。
        if actor_id is not None:
            quota.record_usage(actor_id, "ingest", u)

        _update_job(note_id, stage="store", progress=90)
        _save(note_id, result, analysis, vector, raw_path, space_id=space_id)
        _save_chunks(note_id, chunks, chunk_embeddings)
        _link_entities(note_id, analysis.entities)

        _mark_status(note_id, "done")
        _update_job(note_id, status="done", stage="done", progress=100)
        log.info("ingest done", extra={"event": "ingest_done", "note_id": str(note_id)})
    except Exception as exc:  # noqa: BLE001 — 入库失败要落库，不能吞
        _fail(note_id, str(exc))
        _update_job(note_id, status="failed", error=str(exc))
        log.exception("ingest failed", extra={"event": "ingest_failed", "note_id": str(note_id)})
        raise


# ---------- notes 读写 ----------

def _create_pending(*, url: str, source_type: str, space_id=None, created_by=None) -> uuid.UUID:
    note_id = uuid.uuid4()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO notes (id, title, url, source_type, ingest_status, space_id, created_by) "
            "VALUES (%s, %s, %s, %s, 'pending', %s, %s)",
            (note_id, "（抓取中…）", url, source_type, space_id, created_by),
        )
        source_row = conn.execute(
            """
            INSERT INTO source_documents(space_id,source_type,locator,display_name)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(space_id,locator) DO UPDATE SET updated_at=NOW()
            RETURNING id
            """,
            (space_id, source_type, url or f"note://{note_id}", url),
        ).fetchone()
        conn.execute(
            "UPDATE notes SET source_document_id=%s WHERE id=%s", (source_row[0], note_id)
        )
    return note_id


def _store_raw(note_id, result) -> str | None:
    """把原始文件字节落对象存储，返回写回 notes.raw_path 的路径；无 raw_bytes 返回 None。"""
    if not result.raw_bytes:
        return None
    ext = _SOURCE_EXT.get(result.source_type, "bin")
    key = f"{note_id}/raw.{ext}"
    return storage.get_store().put(key, result.raw_bytes)


def _save(note_id, result, analysis, vector, raw_path: str | None = None, *, space_id=None) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE notes SET
                title       = %s,
                source_type = %s,
                summary     = %s,
                key_points  = %s,
                content     = %s,
                tags        = %s,
                embedding   = %s::vector,
                raw_path    = %s
            WHERE id = %s
            """,
            (
                analysis.title or result.title,
                result.source_type,
                analysis.summary,
                analysis.key_points,
                result.content,
                analysis.tags,
                vector,
                raw_path,
                note_id,
            ),
        )
        # space_id 未传（脚本场景）时从已写好的笔记里读，保证 ES 索引带上空间
        if space_id is None:
            row = conn.execute("SELECT space_id FROM notes WHERE id = %s", (note_id,)).fetchone()
            space_id = row[0] if row else None
        conn.execute(
            """
            UPDATE source_documents SET display_name=%s,content_hash=%s,status='active',
                error_msg=NULL,updated_at=NOW()
            WHERE id=(SELECT source_document_id FROM notes WHERE id=%s)
            """,
            (result.title, hashlib.sha256(result.content.encode("utf-8")).hexdigest(), note_id),
        )
    # 同步索引到 ES（ik 中文分词），关键词检索从这里召回；ES 不可达时静默跳过
    es.index_note(
        str(note_id),
        title=analysis.title or result.title,
        summary=analysis.summary,
        content=result.content,
        tags=analysis.tags or [],
        source_type=result.source_type,
        space_id=str(space_id) if space_id else "",
    )


def _save_chunks(note_id, chunks: list[str], embeddings: list[list[float]]) -> None:
    """把切块逐条写入 note_chunks（先清旧块，重跑入库时覆盖）。"""
    with pool.connection() as conn:
        conn.execute("DELETE FROM note_chunks WHERE note_id = %s", (note_id,))
        if not chunks:
            return
        # psycopg3 的 executemany 在 Cursor 上而非 Connection 上，
        # 这里逐行 execute 更贴合本文件 _save 的写法；每篇笔记块数不多，性能足够。
        insert_sql = """
            INSERT INTO note_chunks (id, note_id, chunk_index, content, embedding)
            VALUES (%s, %s, %s, %s, %s::vector)
        """
        for idx, (text, vec) in enumerate(zip(chunks, embeddings)):
            conn.execute(insert_sql, (uuid.uuid4(), note_id, idx, text, vec))


def _link_entities(note_id, entities) -> None:
    """每个实体 upsert 进 entities，再把 note↔entity 关联写进 note_entities。"""
    if not entities:
        return
    with pool.connection() as conn:
        for ent in entities:
            row = conn.execute(
                """
                INSERT INTO entities (name, type, aliases)
                VALUES (%s, %s, %s)
                ON CONFLICT (name, type) DO UPDATE
                    SET aliases = (
                        SELECT ARRAY(SELECT DISTINCT unnest(entities.aliases || EXCLUDED.aliases))
                    )
                RETURNING id
                """,
                (ent.name, ent.type, ent.aliases),
            ).fetchone()
            entity_id = row[0]
            conn.execute(
                """
                INSERT INTO note_entities (note_id, entity_id, mention_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (note_id, entity_id)
                    DO UPDATE SET mention_count = note_entities.mention_count + 1
                """,
                (note_id, entity_id),
            )


def _mark_status(note_id, status: str) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE notes SET ingest_status = %s WHERE id = %s", (status, note_id))


def _fail(note_id, msg: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE notes SET ingest_status = 'failed', error_msg = %s WHERE id = %s",
            (msg, note_id),
        )


# ---------- jobs 读写（驱动入库队列卡片） ----------

def _create_job(note_id, *, title: str, sub: str, payload: dict) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO jobs (job_type, note_id, payload, title, sub, status, stage, progress) "
            "VALUES ('ingest', %s, %s::jsonb, %s, %s, 'queued', 'queued', 0)",
            (note_id, json.dumps(payload), title, sub),
        )


def _update_job(
    note_id,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    title: str | None = None,
    sub: str | None = None,
    error: str | None = None,
) -> None:
    """按需更新 jobs 行；列名是代码里的字面量，值全部参数化。"""
    sets: list[str] = []
    vals: list[object] = []
    for col, val in (
        ("status", status),
        ("stage", stage),
        ("progress", progress),
        ("title", title),
        ("sub", sub),
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
            "WHERE note_id = %s AND job_type = 'ingest' "
            "AND status IN ('queued', 'running')",
            vals,
        )


def _human_size(n: int) -> str:
    if not n:
        return ""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"
