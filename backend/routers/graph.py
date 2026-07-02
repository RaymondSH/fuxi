"""知识图谱 HTTP 接口。

  GET /graph?filter=all          实体节点 + 共现边（坐标由前端力导向布局算）
  GET /graph/entities/{id}       实体详情 + 相关笔记

M2 起不再用全局视图 entity_note_counts / entity_cooccurrence —— 它们无法接收运行期空间过滤，
会跨空间泄露实体共现与提及数。改为应用层 JOIN note_entities → notes + space 过滤，每请求现算。
（视图定义保留在 sql/03_graph.sql，仅供历史 mcp_server 兼容；新代码勿用。）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import pool
from services import spaces
from services.auth import CurrentUser, get_current_user

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


# 实体提及数 + 共现边：JOIN note_entities → notes 注入空间过滤。
# 子查询里 notes 起别名 ne_space，故空间片段按 alias="ne_space" 生成。
@router.get("", response_model=GraphResponse)
def get_graph(filter: str = "all", user: CurrentUser = Depends(get_current_user)) -> GraphResponse:
    """filter: all | concept | product | company。

    节点提及数与共现边都限定在用户可见空间内现算（sysadmin 全可见）。
    """
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        # 聚合子查询里 notes 起别名 ne_space，故按该别名生成空间片段。
        ne_sf, ne_sfp = spaces.space_filter_from(sids, alias="ne_space")

        if filter in _CATS:
            node_rows = conn.execute(
                f"""
                SELECT e.id, e.name, e.type, COALESCE(cnt.note_count, 0)
                FROM entities e
                LEFT JOIN (
                    SELECT ne.entity_id, COUNT(*)::int AS note_count
                    FROM note_entities ne
                    JOIN notes ne_space ON ne_space.id = ne.note_id
                    WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                    GROUP BY ne.entity_id
                ) cnt ON cnt.entity_id = e.id
                WHERE e.type = %s AND cnt.note_count IS NOT NULL
                ORDER BY COALESCE(cnt.note_count, 0) DESC
                """,
                [*ne_sfp, filter],
            ).fetchall()
        else:
            node_rows = conn.execute(
                f"""
                SELECT e.id, e.name, e.type, COALESCE(cnt.note_count, 0)
                FROM entities e
                LEFT JOIN (
                    SELECT ne.entity_id, COUNT(*)::int AS note_count
                    FROM note_entities ne
                    JOIN notes ne_space ON ne_space.id = ne.note_id
                    WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                    GROUP BY ne.entity_id
                ) cnt ON cnt.entity_id = e.id
                WHERE cnt.note_count IS NOT NULL
                ORDER BY COALESCE(cnt.note_count, 0) DESC
                """,
                ne_sfp,
            ).fetchall()

        edge_rows = conn.execute(
            f"""
            SELECT a.entity_id AS from_id, b.entity_id AS to_id
            FROM note_entities a
            JOIN note_entities b
              ON a.note_id = b.note_id AND a.entity_id < b.entity_id
            JOIN notes ne_space ON ne_space.id = a.note_id
            WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
            GROUP BY a.entity_id, b.entity_id
            """,
            ne_sfp,
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
def get_entity(entity_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> EntityDetail:
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        # 子查询里 notes 起别名 ne_space；相关笔记查询里 notes 起别名 n。
        # 各自按别名生成空间片段，避免 "notes.space_id" 对不上的二义错误。
        ne_sf, ne_sfp = spaces.space_filter_from(sids, alias="ne_space")
        n_sf, n_sfp = spaces.space_filter_from(sids, alias="n")

        row = conn.execute(
            f"""
            SELECT e.id, e.name, e.type, e.aliases, COALESCE(cnt.note_count, 0)
            FROM entities e
            LEFT JOIN (
                SELECT ne.entity_id, COUNT(*)::int AS note_count
                FROM note_entities ne
                JOIN notes ne_space ON ne_space.id = ne.note_id
                WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                GROUP BY ne.entity_id
            ) cnt ON cnt.entity_id = e.id
            WHERE e.id = %s AND cnt.note_count IS NOT NULL
            """,
            [*ne_sfp, entity_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="实体不存在")

        # 相关笔记同样限定可见空间（这里 notes 别名是 n）。
        note_rows = conn.execute(
            f"""
            SELECT n.id, n.title, n.source_type, n.published_date
            FROM note_entities ne JOIN notes n ON n.id = ne.note_id
            WHERE ne.entity_id = %s AND n.ingest_status = 'done' AND n.deleted_at IS NULL{n_sf}
            ORDER BY n.published_date DESC NULLS LAST, n.created_at DESC
            """,
            [entity_id, *n_sfp],
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
