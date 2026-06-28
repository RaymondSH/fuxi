"""笔记 HTTP 接口。

  GET    /notes/{id}    单篇详情（含实体、要点、正文分段）
  DELETE /notes/{id}    删除

正文 original 由 notes.content 按空行切成段落数组返回，对齐前端渲染。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import pool
from services import es
from services.auth import require_admin

router = APIRouter(prefix="/notes", tags=["notes"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}
# 实体类别收敛到前端的三类着色
_CAT_MAP = {"concept": "concept", "product": "product", "company": "company"}


class EntityRef(BaseModel):
    id: uuid.UUID
    name: str
    cat: str


class NoteDetail(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    source: str = ""
    url: str | None = None
    date: str | None = None
    tags: list[str] = []
    entities: list[EntityRef] = []
    summary: str = ""
    keypoints: list[str] = []
    original: list[str] = []
    related_note_ids: list[uuid.UUID] = []


@router.get("/{note_id}", response_model=NoteDetail)
def get_note(note_id: uuid.UUID) -> NoteDetail:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id, source_type, title, COALESCE(source,''), url, published_date,
                   tags, COALESCE(summary,''), key_points, COALESCE(content,''), related_note_ids
            FROM notes WHERE id = %s
            """,
            (note_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="笔记不存在")

        entity_rows = conn.execute(
            """
            SELECT e.id, e.name, e.type
            FROM note_entities ne JOIN entities e ON e.id = ne.entity_id
            WHERE ne.note_id = %s
            ORDER BY ne.mention_count DESC, e.name
            """,
            (note_id,),
        ).fetchall()

    (nid, source_type, title, source, url, pub_date,
     tags, summary, key_points, content, related) = row

    return NoteDetail(
        id=nid,
        type=_TYPE_MAP.get(source_type, "link"),
        title=title,
        source=source,
        url=url,
        date=pub_date.isoformat() if pub_date else None,
        tags=tags or [],
        entities=[
            EntityRef(id=e[0], name=e[1], cat=_CAT_MAP.get(e[2], "concept"))
            for e in entity_rows
        ],
        summary=summary,
        keypoints=key_points or [],
        original=[p.strip() for p in content.split("\n\n") if p.strip()],
        related_note_ids=related or [],
    )


@router.delete("/{note_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_note(note_id: uuid.UUID) -> None:
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = %s", (note_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="笔记不存在")
    # 同步删除 ES 索引（note_chunks 由 FK ON DELETE CASCADE 自动清理）
    es.delete_note(str(note_id))
