"""M4 连接器同步：远端对象幂等落为笔记版本并分发变更。"""
from __future__ import annotations

import json
import uuid

from db import pool
from services import connector_crypto, distribution, lifecycle, llm
from services.connector_providers import create
from workers import ingest_worker


def run(connector_id: uuid.UUID) -> None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT provider,config,credentials,sync_cursor,space_id FROM connector_accounts "
            "WHERE id=%s AND status='active'",
            (connector_id,),
        ).fetchone()
    if row is None:
        raise ValueError("连接器不存在或已停用")
    provider_name, config, encrypted, cursor, space_id = row
    provider = create(provider_name, config or {}, connector_crypto.decrypt(encrypted))
    try:
        items, next_cursor = provider.list_changes(cursor)
        for item in items:
            _sync_item(connector_id, space_id, provider, item)
        if provider.full_snapshot:
            seen = [item.external_id for item in items]
            with pool.connection() as conn:
                missing = conn.execute(
                    "UPDATE connector_items SET status='missing',synced_at=NOW() "
                    "WHERE connector_id=%s AND status='active' AND NOT (external_id=ANY(%s)) "
                    "RETURNING note_id,external_id",
                    (connector_id, seen),
                ).fetchall()
            for note_id, external_id in missing:
                distribution.emit_change(
                    space_id, note_id, "missing", "远端内容已删除或失去访问权限",
                    {"connector_id": str(connector_id), "external_id": external_id},
                )
        with pool.connection() as conn:
            conn.execute(
                "UPDATE connector_accounts SET sync_cursor=%s,last_synced_at=NOW(),"
                "status='active',error_msg=NULL,updated_at=NOW() WHERE id=%s",
                (next_cursor, connector_id),
            )
    except Exception as exc:
        with pool.connection() as conn:
            conn.execute(
                "UPDATE connector_accounts SET status='error',error_msg=%s,updated_at=NOW() WHERE id=%s",
                (str(exc)[:1000], connector_id),
            )
        raise


def _sync_item(connector_id, space_id, provider, item) -> None:
    with pool.connection() as conn:
        current = conn.execute(
            "SELECT id,note_id,remote_version,status FROM connector_items "
            "WHERE connector_id=%s AND external_id=%s",
            (connector_id, item.external_id),
        ).fetchone()
    if item.deleted:
        if current:
            with pool.connection() as conn:
                conn.execute(
                    "UPDATE connector_items SET status='missing',synced_at=NOW() WHERE id=%s",
                    (current[0],),
                )
            distribution.emit_change(space_id, current[1], "missing", item.title)
        return
    if current and current[2] == item.version and current[3] == "active":
        return
    document = provider.fetch_content(item)
    if not document.content.strip():
        raise ValueError(f"远端内容为空: {item.external_id}")
    analysis = llm.analyze(document.content, title_hint=item.title)
    note_id = current[1] if current and current[1] else uuid.uuid4()
    with pool.connection() as conn:
        if current and current[1]:
            lifecycle.save_version(conn, note_id, "refresh")
            conn.execute(
                "UPDATE notes SET title=%s,url=%s,summary=%s,key_points=%s,content=%s,tags=%s,"
                "ingest_status='done',error_msg=NULL WHERE id=%s",
                (analysis.title, item.url, analysis.summary, analysis.key_points,
                 document.content, analysis.tags, note_id),
            )
            event_type = "restored" if current[3] == "missing" else "updated"
        else:
            conn.execute(
                """
                INSERT INTO notes(id,title,url,source,source_type,summary,key_points,content,tags,
                                  ingest_status,space_id)
                VALUES(%s,%s,%s,%s,'manual',%s,%s,%s,%s,'done',%s)
                """,
                (note_id, analysis.title, item.url, item.title, analysis.summary,
                 analysis.key_points, document.content, analysis.tags, space_id),
            )
            source_id = uuid.uuid4()
            conn.execute(
                """
                INSERT INTO source_documents(id,space_id,source_type,locator,display_name,
                                             connector_id,external_id,content_hash)
                VALUES(%s,%s,'manual',%s,%s,%s,%s,md5(%s))
                """,
                (source_id, space_id, item.url or f"connector://{connector_id}/{item.external_id}",
                 item.title, connector_id, item.external_id, document.content),
            )
            conn.execute("UPDATE notes SET source_document_id=%s WHERE id=%s", (source_id, note_id))
            event_type = "created"
        conn.execute("DELETE FROM note_entities WHERE note_id=%s", (note_id,))
        if current:
            conn.execute(
                "UPDATE connector_items SET note_id=%s,remote_version=%s,remote_modified_at=%s,"
                "status='active',metadata=%s::jsonb,error_msg=NULL,synced_at=NOW() WHERE id=%s",
                (note_id, item.version, item.modified_at,
                 json.dumps(item.metadata or {}), current[0]),
            )
        else:
            conn.execute(
                "INSERT INTO connector_items(connector_id,external_id,note_id,remote_version,"
                "remote_modified_at,status,metadata,synced_at) VALUES(%s,%s,%s,%s,%s,'active',%s::jsonb,NOW())",
                (connector_id, item.external_id, note_id, item.version, item.modified_at,
                 json.dumps(item.metadata or {})),
            )
    ingest_worker._link_entities(note_id, analysis.entities)
    lifecycle.reindex(note_id)
    distribution.emit_change(space_id, note_id, event_type, analysis.title,
                             {"connector_id": str(connector_id), "external_id": item.external_id})
