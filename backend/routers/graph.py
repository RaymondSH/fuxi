"""知识图谱 HTTP 接口。

  GET /graph?filter=all          实体节点 + 共现边（坐标由前端力导向布局算）
  GET /graph/entities/{id}       实体详情 + 相关笔记

节点提及数走 entity_note_counts 视图，边走 entity_cooccurrence 视图（见 sql/03_graph.sql）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import pool

router = APIRouter(prefix="/graph", tags=["graph"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}
_CATS = {"concept", "product", "company"}


def _cat(t: str) -> str:
    return t if t in _CATS else "concept"


class GraphNode(BaseModel):
    id: uuid.UUID
    name: str
    cat: str
    count: int


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[list[uuid.UUID]]


@router.get("", response_model=GraphResponse)
def get_graph(filter: str = "all") -> GraphResponse:
    """filter: all | concept | product | company。"""
    with pool.connection() as conn:
        if filter in _CATS:
            node_rows = conn.execute(
                """
                SELECT e.id, e.name, e.type, COALESCE(c.note_count, 0)
                FROM entities e
                LEFT JOIN entity_note_counts c ON c.entity_id = e.id
                WHERE e.type = %s
                ORDER BY COALESCE(c.note_count, 0) DESC
                """,
                (filter,),
            ).fetchall()
        else:
            node_rows = conn.execute(
                """
                SELECT e.id, e.name, e.type, COALESCE(c.note_count, 0)
                FROM entities e
                LEFT JOIN entity_note_counts c ON c.entity_id = e.id
                ORDER BY COALESCE(c.note_count, 0) DESC
                """
            ).fetchall()
        edge_rows = conn.execute(
            "SELECT from_id, to_id FROM entity_cooccurrence"
        ).fetchall()

    node_ids = {r[0] for r in node_rows}
    nodes = [GraphNode(id=r[0], name=r[1], cat=_cat(r[2]), count=r[3]) for r in node_rows]
    # 过滤后只保留两端都在节点集里的边
    edges = [[a, b] for a, b in edge_rows if a in node_ids and b in node_ids]
    return GraphResponse(nodes=nodes, edges=edges)


class EntityDetail(BaseModel):
    id: uuid.UUID
    name: str
    cat: str
    count: int
    aliases: list[str] = []
    notes: list[dict]


@router.get("/entities/{entity_id}", response_model=EntityDetail)
def get_entity(entity_id: uuid.UUID) -> EntityDetail:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT e.id, e.name, e.type, e.aliases, COALESCE(c.note_count, 0)
            FROM entities e
            LEFT JOIN entity_note_counts c ON c.entity_id = e.id
            WHERE e.id = %s
            """,
            (entity_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="实体不存在")

        note_rows = conn.execute(
            """
            SELECT n.id, n.title, n.source_type, n.published_date
            FROM note_entities ne JOIN notes n ON n.id = ne.note_id
            WHERE ne.entity_id = %s
            ORDER BY n.published_date DESC NULLS LAST, n.created_at DESC
            """,
            (entity_id,),
        ).fetchall()

    return EntityDetail(
        id=row[0],
        name=row[1],
        cat=_cat(row[2]),
        count=row[4],
        aliases=row[3] or [],
        notes=[
            {
                "id": str(n[0]),
                "title": n[1],
                "type": _TYPE_MAP.get(n[2], "link"),
                "date": n[3].isoformat() if n[3] else None,
            }
            for n in note_rows
        ],
    )
