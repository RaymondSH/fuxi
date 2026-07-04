"""检索 HTTP 接口。

  POST /search           关键词 / 语义 / 混合(hybrid) 检索，写入 search_history
  GET  /search/history   搜索历史

标签云 GET /tags 已迁至 routers/tags.py（与受控词表治理同组）。

关键词路走 Elasticsearch + ik 中文分词（按词切分，命中更准），ES 不可达自动回退 Postgres ILIKE；
语义路走 pgvector（chunk 级，取每篇最优块聚合）。hybrid 用 RRF 融合两路。
没有 API_KEY 时语义路拿不到查询向量，hybrid 自动降级为纯关键词。
"""
from __future__ import annotations

import html
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from db import pool
from services import embedder, es, guardrails, quota, reranker, spaces, usage
from services.auth import CurrentUser, get_current_user

router = APIRouter(tags=["search"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}
_TIME_INTERVAL = {"today": "1 day", "week": "7 days", "month": "30 days", "year": "365 days"}
_RRF_K = 60  # RRF 平滑常数


class SearchRequest(BaseModel):
    q: str
    mode: Literal["hybrid", "keyword", "semantic"] = "hybrid"
    tags: list[str] = Field(default_factory=list)
    time_filter: Literal["all", "today", "week", "month", "year"] = "all"
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class SearchResult(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    source: str = ""
    date: str | None = None
    tags: list[str] = []
    summary: str = ""
    score: float | None = None
    snippet: str = ""


class SearchResponse(BaseModel):
    query: str
    mode: str
    took_ms: int
    total: int
    results: list[SearchResult]


# ---------- 接口 ----------

@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, user: CurrentUser = Depends(get_current_user)) -> SearchResponse:
    t0 = time.perf_counter()
    q = req.q.strip()

    # 无查询词：有标签则做「按标签浏览」（不调 LLM、不计费），无标签返回空
    if not q:
        if not req.tags:
            return SearchResponse(query=q, mode=req.mode, took_ms=0, total=0, results=[])
        with pool.connection() as conn:
            sids = spaces.visible_space_ids(conn, user)
            sf, sfp = spaces.space_filter_from(sids)
            # total 用真实 COUNT(*)，不被 LIMIT 100 截断；ordered 仍限 100 防超大结果集
            extra, extra_params = _filters(req.tags, req.time_filter, sf, sfp)
            total = conn.execute(
                f"SELECT COUNT(*) FROM notes WHERE ingest_status = 'done'{extra}", extra_params
            ).fetchone()[0]
            ordered = _tag_search(conn, req.tags, req.time_filter, sf, sfp)
        page_rows = ordered[(req.page - 1) * req.size : (req.page - 1) * req.size + req.size]
        results = [_to_result(r, q) for r in page_rows]
        _save_history(q, "tag", req.tags, req.time_filter, [r.id for r in results], total, user.id)
        took = int((time.perf_counter() - t0) * 1000)
        return SearchResponse(query=q, mode="tag", took_ms=took, total=total, results=results)

    # 仅语义/混合会调用 embedding（计费），先查配额；纯关键词不计费、不检查
    if req.mode in ("hybrid", "semantic"):
        quota.check_quota(user)

    with usage.collect() as u, pool.connection() as conn:
        # M2：算一次可见空间集合，关键词路 + 语义路共用（ES 侧也用字符串形式过滤）
        sids = spaces.visible_space_ids(conn, user)
        sf, sfp = spaces.space_filter_from(sids)
        es_sids = spaces.visible_space_strs(conn, user) if sids is not None else None
        kw_rows = _keyword_search(conn, q, req.tags, req.time_filter, sf, sfp, es_sids)
        safe_q, _ = guardrails.mask_pii(q)
        vec = _try_embed(safe_q) if req.mode in ("hybrid", "semantic") else None
        sem_rows = (
            _semantic_search(conn, vec, req.tags, req.time_filter, sf, sfp)
            if vec is not None
            else []
        )

    effective_mode = req.mode
    if req.mode == "semantic":
        ordered = sem_rows or kw_rows  # 无向量时退回关键词
        if not sem_rows:
            effective_mode = "keyword"
    elif req.mode == "keyword":
        ordered = kw_rows
    else:  # hybrid
        if sem_rows:
            ordered = _rrf_fuse(kw_rows, sem_rows)
        else:
            ordered = kw_rows
            effective_mode = "keyword"

    if effective_mode == "hybrid" and len(ordered) > 1:
        safe_q, _ = guardrails.mask_pii(q)
        with pool.connection() as conn:
            ordered = reranker.rerank_rows(safe_q, ordered, conn, usage_acc=u)

    # keyword/semantic/hybrid 都是最多 100 条候选的有界排序窗口；
    # total 必须与实际可分页结果一致，不能拿 ILIKE 数量冒充语义命中总数。
    total = len(ordered)
    start = (req.page - 1) * req.size
    page_rows = ordered[start : start + req.size]
    results = [_to_result(r, q) for r in page_rows]

    quota.record_usage(user.id, "search_semantic", u)  # 纯关键词无 usage，内部不记
    _save_history(q, effective_mode, req.tags, req.time_filter, [r.id for r in results], total, user.id)

    took = int((time.perf_counter() - t0) * 1000)
    return SearchResponse(query=q, mode=effective_mode, took_ms=took, total=total, results=results)


@router.get("/search/history")
def search_history(
    scope: str = "mine",
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    all_users = user.is_admin and scope == "all"
    where = "" if all_users else "WHERE user_id = %s"
    params: list = [] if all_users else [user.id]
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, query, mode, result_count, created_at,
                   to_char(created_at, 'MM-DD HH24:MI') AS when_label
            FROM search_history
            {where}
            ORDER BY created_at DESC
            LIMIT 30
            """,
            params,
        ).fetchall()
    return {
        "items": [
            {"id": r[0], "q": r[1], "mode": r[2], "hits": r[3],
             "created_at": r[4].isoformat(), "relative": r[5]}
            for r in rows
        ]
    }


# ---------- 检索实现 ----------

# 统一选这些列，方便构造结果与片段
_COLS = "id, source_type, title, COALESCE(source,''), published_date, tags, COALESCE(summary,''), COALESCE(content,'')"


def _try_embed(q: str):
    """尝试给查询算向量；没配 API_KEY 等情况返回 None，让上层降级。"""
    try:
        return embedder.embed(q)
    except Exception:  # noqa: BLE001 — 语义路不可用时静默降级到关键词
        return None


def _filters(tags: list[str], time_filter: str, space_frag: str = "", space_params: list | None = None) -> tuple[str, list]:
    """拼附加过滤条件（空间 / 标签 / 时间），返回 SQL 片段与参数。

    space_frag（M2）是已生成好的空间过滤片段（如 " AND notes.space_id = ANY(%s::uuid[])"），
    直接拼到 WHERE 末尾；space_params 是其参数。sysadmin 传空串则不加。
    """
    clauses, params = ["deleted_at IS NULL"], []
    if space_frag:
        clauses.append(space_frag.lstrip(" AND "))
        params.extend(space_params or [])
    if tags:
        clauses.append("tags && %s::text[]")  # 标签有交集
        params.append(tags)
    interval = _TIME_INTERVAL.get(time_filter)
    if interval:
        clauses.append("created_at >= NOW() - %s::interval")
        params.append(interval)
    return ("".join(f" AND {c}" for c in clauses), params)


def _tag_search(conn, tags, time_filter, space_frag="", space_params=None) -> list[tuple]:
    """按标签浏览：无查询词时用，纯标签（+时间+空间）过滤，按时间倒序。不打分、不调 LLM。"""
    extra, extra_params = _filters(tags, time_filter, space_frag, space_params)  # extra 含空间 + tags + 时间过滤
    sql = f"""
        SELECT {_COLS}
        FROM notes
        WHERE ingest_status = 'done'{extra}
        ORDER BY created_at DESC
        LIMIT 100
    """
    return conn.execute(sql, extra_params).fetchall()


def _keyword_search(conn, q: str, tags, time_filter, space_frag="", space_params=None, es_sids=None) -> list[tuple]:
    """关键词检索：优先走 ES + ik 中文分词（按词切分，命中更准）；
    ES 不可达或无命中时回退 Postgres ILIKE（子串匹配）。

    两条路都返回 _COLS + score 的行，与语义路同构，便于 RRF 融合。
    es_sids（M2）传给 ES search 做空间硬过滤；PG 回查再补一次空间过滤（双保险）。
    """
    es_hits = es.search(q, tags=tags, limit=100, space_ids=es_sids)
    if es_hits:
        # ES 已按相关度排序；回查 PG 取 _COLS 与过滤条件，再按 ES 顺序拼回 score。
        return _keyword_search_by_ids(conn, es_hits, time_filter, space_frag, space_params)
    return _keyword_search_ilike(conn, q, tags, time_filter, space_frag, space_params)


def _keyword_search_by_ids(conn, es_hits: list[tuple[str, float]], time_filter: str, space_frag="", space_params=None) -> list[tuple]:
    """按 ES 召回的 note_id 回查 PG 取 _COLS（含时间+空间过滤），保持 ES 排序与分数。

    标签过滤已在 ES 侧完成（terms filter），这里只补时间 + 空间过滤（空间双保险）。
    """
    if not es_hits:
        return []
    ids = [h[0] for h in es_hits]
    id2score = {h[0]: h[1] for h in es_hits}
    interval = _TIME_INTERVAL.get(time_filter)
    where = "id = ANY(%s::uuid[]) AND ingest_status = 'done' AND deleted_at IS NULL"
    params: list = [ids]
    if space_frag:
        where += space_frag  # 已含前导 " AND notes.space_id = ..."
        params.extend(space_params or [])
    if interval:
        where += " AND created_at >= NOW() - %s::interval"
        params.append(interval)
    sql = f"SELECT {_COLS} FROM notes WHERE {where}"
    rows = conn.execute(sql, params).fetchall()
    # 按 ES 顺序重排，附 ES 分数
    by_id = {str(r[0]): r for r in rows}
    out: list[tuple] = []
    for nid, score in es_hits:
        r = by_id.get(nid)
        if r:
            out.append(tuple(list(r) + [score]))
    return out


def _keyword_search_ilike(conn, q: str, tags, time_filter, space_frag="", space_params=None) -> list[tuple]:
    """ILIKE 子串回退：无 ES 或 ES 无命中时使用。"""
    extra, extra_params = _filters(tags, time_filter, space_frag, space_params)
    like = f"%{q}%"
    sql = f"""
        SELECT {_COLS},
               (CASE WHEN title ILIKE %s THEN 3 ELSE 0 END)
             + (CASE WHEN summary ILIKE %s THEN 2 ELSE 0 END)
             + (CASE WHEN content ILIKE %s THEN 1 ELSE 0 END) AS kw_score
        FROM notes
        WHERE ingest_status = 'done'
          AND (title ILIKE %s OR summary ILIKE %s OR content ILIKE %s){extra}
        ORDER BY kw_score DESC, created_at DESC
        LIMIT 100
    """
    params = [like, like, like, like, like, like, *extra_params]
    return conn.execute(sql, params).fetchall()


def _semantic_search(conn, vec, tags, time_filter, space_frag="", space_params=None) -> list[tuple]:
    """chunk 级语义检索：每块算余弦相似，取每篇笔记最高分聚合回 note，按分排序。

    note_chunks 为主召回路；没有 chunk 的笔记回退 notes.embedding（见 _semantic_search_doc）。
    """
    extra, extra_params = _filters(tags, time_filter, space_frag, space_params)
    # 子查询里的空间过滤：space_frag 用的是 "notes." 别名，子查询里 notes 别名是 n，
    # 故单独构造一份 n. 版本。sysadmin（space_frag 为空）则不加。
    sub_space_frag = ""
    sub_space_params: list = []
    if space_frag:
        sub_space_frag = space_frag.replace("notes.space_id", "n.space_id")
        sub_space_params = list(space_params or [])
    # 先按 note 聚合：取每篇笔记里最相似的块分（MAX），保证一篇笔记只出一条。
    # 注意：过滤条件里的 tags/created_at 是裸列名，只在 notes 未起别名时才能解析，
    # 所以 extra 必须落到外层 WHERE；子查询里列也显式限定到 notes 避免二义。
    sql = f"""
        SELECT notes.id, notes.source_type, notes.title, COALESCE(notes.source,''),
               notes.published_date, notes.tags, COALESCE(notes.summary,''),
               COALESCE(notes.content,''), best.sim
        FROM (
            SELECT c.note_id AS id, MAX(1 - (c.embedding <=> %s::vector)) AS sim
            FROM note_chunks c
            JOIN notes n ON n.id = c.note_id
            WHERE n.ingest_status = 'done' AND n.deleted_at IS NULL
              AND c.embedding IS NOT NULL{sub_space_frag}
            GROUP BY c.note_id
            ORDER BY MAX(c.embedding <=> %s::vector)
            LIMIT 200
        ) best
        JOIN notes ON notes.id = best.id
        WHERE notes.ingest_status = 'done'{extra}
        ORDER BY best.sim DESC, notes.created_at DESC
        LIMIT 100
    """
    rows = conn.execute(sql, [vec, *sub_space_params, vec, *extra_params]).fetchall()
    if rows:
        return rows
    # 无 chunk 时回退文档级向量
    return _semantic_search_doc(conn, vec, tags, time_filter, space_frag, space_params)


def _semantic_search_doc(conn, vec, tags, time_filter, space_frag="", space_params=None) -> list[tuple]:
    """文档级语义检索（notes.embedding），chunk 表为空时的回退。"""
    extra, extra_params = _filters(tags, time_filter, space_frag, space_params)
    sql = f"""
        SELECT {_COLS}, 1 - (embedding <=> %s::vector) AS sim
        FROM notes
        WHERE ingest_status = 'done' AND embedding IS NOT NULL{extra}
        ORDER BY embedding <=> %s::vector
        LIMIT 100
    """
    return conn.execute(sql, [vec, *extra_params, vec]).fetchall()


def _rrf_fuse(kw_rows: list[tuple], sem_rows: list[tuple]) -> list[tuple]:
    """Reciprocal Rank Fusion：两路按排名打分相加，返回融合后的行。"""
    score: dict = {}
    row_by_id: dict = {}
    for rank, row in enumerate(kw_rows):
        nid = row[0]
        score[nid] = score.get(nid, 0.0) + 1.0 / (_RRF_K + rank)
        row_by_id[nid] = row
    for rank, row in enumerate(sem_rows):
        nid = row[0]
        score[nid] = score.get(nid, 0.0) + 1.0 / (_RRF_K + rank)
        row_by_id.setdefault(nid, row)
    ordered_ids = sorted(score, key=lambda x: score[x], reverse=True)
    # 把融合分塞回行末，供展示
    return [(*row_by_id[i][:8], score[i]) for i in ordered_ids]


def _to_result(row: tuple, q: str) -> SearchResult:
    nid, source_type, title, source, pub_date, tags, summary, content = row[:8]
    score = row[8] if len(row) > 8 else None
    return SearchResult(
        id=nid,
        type=_TYPE_MAP.get(source_type, "link"),
        title=title,
        source=source,
        date=pub_date.isoformat() if pub_date else None,
        tags=tags or [],
        summary=summary,
        score=round(float(score), 4) if score is not None else None,
        snippet=_snippet(content or summary, q),
    )


def _snippet(text: str, q: str, window: int = 60) -> str:
    """截取命中词周边片段，HTML 转义后只把命中词包成 <em>。"""
    if not text:
        return ""
    lower = text.lower()
    pos = lower.find(q.lower())
    if pos == -1:
        return html.escape(text[:140])
    start = max(0, pos - window)
    end = min(len(text), pos + len(q) + window)
    before = html.escape(text[start:pos])
    match = html.escape(text[pos : pos + len(q)])
    after = html.escape(text[pos + len(q) : end])
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{before}<em>{match}</em>{after}{suffix}"


def _save_history(q, mode, tags, time_filter, result_ids, total, user_id) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO search_history (query, mode, time_filter, tags, result_ids, result_count, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (q, mode if mode in ("hybrid", "keyword", "semantic", "tag") else "keyword",
             time_filter, tags, result_ids, total, user_id),
        )
