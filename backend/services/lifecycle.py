"""笔记生命周期：版本快照、编辑/恢复、重建索引与来源刷新。"""
from __future__ import annotations

import hashlib
import json
import uuid

from db import pool
from services import chunker, embedder, es, fetcher, llm

_SNAPSHOT_SQL = """
SELECT title, source, url, source_type, published_date, summary, key_points,
       content, tags, authority, raw_path
FROM notes WHERE id = %s
"""
_FIELDS = (
    "title", "source", "url", "source_type", "published_date", "summary",
    "key_points", "content", "tags", "authority", "raw_path",
)


def _snapshot(conn, note_id: uuid.UUID) -> dict:
    row = conn.execute(_SNAPSHOT_SQL, (note_id,)).fetchone()
    if row is None:
        raise ValueError("笔记不存在")
    snap = dict(zip(_FIELDS, row))
    if snap["published_date"] is not None:
        snap["published_date"] = snap["published_date"].isoformat()
    return snap


def save_version(conn, note_id: uuid.UUID, change_type: str, actor_id=None) -> int:
    """保存当前状态并递增 notes.revision，返回已保存版本号。"""
    revision = conn.execute(
        "SELECT revision FROM notes WHERE id = %s FOR UPDATE", (note_id,)
    ).fetchone()
    if revision is None:
        raise ValueError("笔记不存在")
    version_no = revision[0]
    conn.execute(
        """
        INSERT INTO note_versions (note_id, version_no, change_type, snapshot, created_by)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (note_id, version_no) DO NOTHING
        """,
        (note_id, version_no, change_type, json.dumps(_snapshot(conn, note_id), ensure_ascii=False), actor_id),
    )
    conn.execute("UPDATE notes SET revision = revision + 1 WHERE id = %s", (note_id,))
    return version_no


def enqueue_reindex(note_id: uuid.UUID, actor_id=None) -> uuid.UUID:
    job_id = uuid.uuid4()
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, job_type, note_id, payload, status, stage, title)
            SELECT %s, 'note_reindex', id,
                   jsonb_build_object('actor_id', %s::text), 'queued', 'queued', title
            FROM notes WHERE id = %s
            """,
            (job_id, actor_id, note_id),
        )
    return job_id


def reindex(note_id: uuid.UUID) -> None:
    """按当前正文重建文档/分块向量和 ES；软删除时只从 ES 移除。"""
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT title, COALESCE(summary,''), COALESCE(content,''), tags,
                   source_type, space_id, deleted_at
            FROM notes WHERE id = %s
            """,
            (note_id,),
        ).fetchone()
    if row is None:
        raise ValueError("笔记不存在")
    title, summary, content, tags, source_type, space_id, deleted_at = row
    if deleted_at is not None:
        es.delete_note(str(note_id))
        return
    chunks = chunker.split(content)
    chunk_vectors = [embedder.embed(c) for c in chunks]
    vector = embedder.embed(f"{summary}\n\n{content[:2000]}")
    with pool.connection() as conn:
        conn.execute("UPDATE notes SET embedding = %s::vector WHERE id = %s", (vector, note_id))
        conn.execute("DELETE FROM note_chunks WHERE note_id = %s", (note_id,))
        for index, (text, emb) in enumerate(zip(chunks, chunk_vectors)):
            conn.execute(
                "INSERT INTO note_chunks (id,note_id,chunk_index,content,embedding) "
                "VALUES (%s,%s,%s,%s,%s::vector)",
                (uuid.uuid4(), note_id, index, text, emb),
            )
    es.index_note(
        str(note_id), title=title, summary=summary, content=content, tags=tags or [],
        source_type=source_type, space_id=str(space_id),
    )


def restore_version(note_id: uuid.UUID, version_no: int, actor_id=None) -> None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT snapshot FROM note_versions WHERE note_id = %s AND version_no = %s",
            (note_id, version_no),
        ).fetchone()
        if row is None:
            raise ValueError("版本不存在")
        save_version(conn, note_id, "restore", actor_id)
        snap = row[0]
        conn.execute(
            """
            UPDATE notes SET title=%s, source=%s, url=%s, source_type=%s,
                published_date=%s, summary=%s, key_points=%s, content=%s, tags=%s,
                authority=%s, raw_path=%s, deleted_at=NULL, deleted_by=NULL
            WHERE id=%s
            """,
            tuple(snap.get(k) for k in _FIELDS) + (note_id,),
        )
    enqueue_reindex(note_id, actor_id)


def refresh_source(note_id: uuid.UUID, actor_id=None) -> None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT s.id, s.locator, s.content_hash
            FROM notes n JOIN source_documents s ON s.id=n.source_document_id
            WHERE n.id=%s AND n.deleted_at IS NULL AND s.source_type='url'
            """,
            (note_id,),
        ).fetchone()
    if row is None:
        raise ValueError("该笔记没有可刷新的 URL 来源")
    source_id, url, old_hash = row
    try:
        result = fetcher.fetch(url=url)
        digest = hashlib.sha256(result.content.encode("utf-8")).hexdigest()
        with pool.connection() as conn:
            if digest == old_hash:
                conn.execute(
                    "UPDATE source_documents SET status='active',last_checked_at=NOW(),"
                    "next_refresh_at=CASE refresh_policy WHEN 'daily' THEN NOW()+INTERVAL '1 day' "
                    "WHEN 'weekly' THEN NOW()+INTERVAL '7 days' ELSE NULL END,error_msg=NULL WHERE id=%s",
                    (source_id,),
                )
                return
            analysis = llm.analyze(result.content, title_hint=result.title)
            save_version(conn, note_id, "refresh", actor_id)
            conn.execute(
                "UPDATE notes SET title=%s,summary=%s,key_points=%s,content=%s,tags=%s WHERE id=%s",
                (analysis.title, analysis.summary, analysis.key_points, result.content, analysis.tags, note_id),
            )
            conn.execute("DELETE FROM generated_qa WHERE note_id=%s", (note_id,))
            conn.execute("DELETE FROM note_entities WHERE note_id=%s", (note_id,))
            conn.execute(
                "UPDATE source_documents SET content_hash=%s,status='active',last_checked_at=NOW(),"
                "next_refresh_at=CASE refresh_policy WHEN 'daily' THEN NOW()+INTERVAL '1 day' "
                "WHEN 'weekly' THEN NOW()+INTERVAL '7 days' ELSE NULL END,error_msg=NULL WHERE id=%s",
                (digest, source_id),
            )
        from workers import ingest_worker
        ingest_worker._link_entities(note_id, analysis.entities)
        reindex(note_id)
    except Exception as exc:
        with pool.connection() as conn:
            conn.execute(
                "UPDATE source_documents SET status='broken',last_checked_at=NOW(),error_msg=%s WHERE id=%s",
                (str(exc)[:1000], source_id),
            )
        raise
