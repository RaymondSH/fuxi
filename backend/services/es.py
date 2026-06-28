"""Elasticsearch 客户端（ik 中文分词）。

关键词检索从 Postgres ILIKE 迁到 ES + ik：中文按词切分而非按字，
命中更准（如「自然语言处理」能整词匹配，而 ILIKE 只能子串匹配）。

设计要点：
- 单例 httpx 客户端（ES 是纯 HTTP/JSON，无需重客户端依赖）。
- 索引 notes_v1：title/summary/content 用 ik_max_word（索引最细粒度）+ ik_smart（查询智能切分）；
  tags 存 keyword 数组方便精确过滤；note_id 存 keyword 供回查 PG。
- 检索只返回 note_id + score，由 search 路由拿 note_id 回 PG 取 _COLS，
  与语义路结果同构，便于 RRF 融合。
- ES 不可达时 search 返回空列表，调用方自动回退 ILIKE，不抛异常打断请求。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

_INDEX = "notes_v1"

# 索引映射：title/summary/content 走 ik 中文分词；tags 用 keyword 精确匹配。
# 索引期 ik_max_word（最细，召回高），查询期 ik_smart（粗粒度，精度高）。
_MAPPING = {
    "properties": {
        "note_id": {"type": "keyword"},
        "title": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
        "summary": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
        "content": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
        "tags": {"type": "keyword"},
        "source_type": {"type": "keyword"},
    }
}

# 单例 httpx 客户端（长连接复用）
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            base_url=settings.es_url,
            timeout=httpx.Timeout(settings.es_timeout, connect=3.0),
            headers={"Content-Type": "application/json"},
        )
    return _client


def _is_enabled() -> bool:
    """ES 未配置或显式关闭时返回 False，调用方走 ILIKE 回退。"""
    return bool(settings.es_url)


def ensure_index() -> None:
    """启动时确保索引存在（幂等）。ES 不可达时静默跳过，等回退即可。"""
    if not _is_enabled():
        return
    try:
        c = _get_client()
        resp = c.head(f"/{_INDEX}")
        if resp.status_code == 404:
            body = {"mappings": _MAPPING, "settings": {"number_of_shards": 1, "number_of_replicas": 0}}
            r = c.put(f"/{_INDEX}", content=json.dumps(body))
            r.raise_for_status()
            log.info("es: created index %s", _INDEX)
    except Exception as exc:  # noqa: BLE001 — 启动期 ES 未就绪不应致命
        log.warning("es: ensure_index 失败，关键词检索将回退 ILIKE：%s", exc)


def index_note(
    note_id: str,
    title: str,
    summary: str,
    content: str,
    tags: list[str],
    source_type: str = "",
) -> None:
    """把一篇笔记索引进 ES（用 note_id 做 _id，重复索引即覆盖）。ES 不可达时静默丢弃。"""
    if not _is_enabled():
        return
    doc = {
        "note_id": note_id,
        "title": title,
        "summary": summary or "",
        "content": content or "",
        "tags": tags or [],
        "source_type": source_type,
    }
    try:
        _get_client().put(f"/{_INDEX}/_doc/{note_id}", content=json.dumps(doc))
    except Exception as exc:  # noqa: BLE001 — 索引失败不影响 PG 入库主流程
        log.warning("es: index_note %s 失败：%s", note_id, exc)


def delete_note(note_id: str) -> None:
    """从 ES 删除一篇笔记的索引（删笔记时调用，404 视为已删）。"""
    if not _is_enabled():
        return
    try:
        _get_client().delete(f"/{_INDEX}/_doc/{note_id}")
    except Exception as exc:  # noqa: BLE001 — 删除失败不影响 PG 删除主流程
        log.warning("es: delete_note %s 失败：%s", note_id, exc)


def search(q: str, tags: list[str] | None = None, limit: int = 100) -> list[tuple[str, float]]:
    """关键词检索：返回 [(note_id, score), ...]，按相关度降序。

    ES 不可达 / 未配置时返回空列表，调用方据此回退 ILIKE。
    """
    if not _is_enabled() or not q.strip():
        return []
    # multi_match 跨 title/summary/content；title 权重最高（^3），summary 次之（^2）。
    body: dict[str, Any] = {
        "size": limit,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": ["title^3", "summary^2", "content"],
                            "type": "best_fields",
                            "operator": "or",
                        }
                    }
                ],
                "filter": [],
            }
        },
    }
    if tags:
        body["query"]["bool"]["filter"].append({"terms": {"tags": tags}})
    try:
        resp = _get_client().post(f"/{_INDEX}/_search", content=json.dumps(body))
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        out: list[tuple[str, float]] = []
        for h in hits:
            note_id = h.get("_source", {}).get("note_id") or h.get("_id")
            if note_id:
                out.append((str(note_id), float(h.get("_score", 0.0))))
        return out
    except Exception as exc:  # noqa: BLE001 — 检索期 ES 不可达走回退
        log.warning("es: search 失败，回退 ILIKE：%s", exc)
        return []
