"""M4 变更事件与站内通知分发。"""
from __future__ import annotations

import json
import uuid

from db import pool


def emit_change(space_id, note_id, event_type: str, title: str, detail: dict | None = None) -> uuid.UUID:
    event_id = uuid.uuid4()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO change_events(id,space_id,note_id,event_type,title,detail) "
            "VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
            (event_id, space_id, note_id, event_type, title,
             json.dumps(detail or {}, ensure_ascii=False)),
        )
        tags = []
        if note_id:
            row = conn.execute("SELECT tags FROM notes WHERE id=%s", (note_id,)).fetchone()
            tags = row[0] if row else []
        rows = conn.execute(
            """
            SELECT DISTINCT s.user_id FROM subscriptions s
            JOIN users u ON u.id=s.user_id
            LEFT JOIN space_members sm ON sm.space_id=s.space_id AND sm.user_id=s.user_id
            WHERE s.space_id=%s AND (
                s.scope_type='space'
                OR (s.scope_type='note' AND s.scope_value=%s)
                OR (s.scope_type='tag' AND s.scope_value=ANY(%s::text[]))
            ) AND (u.role='admin' OR sm.user_id IS NOT NULL)
            """,
            (space_id, str(note_id) if note_id else "", tags),
        ).fetchall()
        for (user_id,) in rows:
            conn.execute(
                """
                INSERT INTO notifications(user_id,space_id,change_event_id,title,body,link)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,change_event_id) DO NOTHING
                """,
                (user_id, space_id, event_id, title,
                 {"created": "新增", "updated": "更新", "missing": "失效", "restored": "恢复"}.get(event_type, "变更"),
                 f"/notes/{note_id}" if note_id else None),
            )
    return event_id
