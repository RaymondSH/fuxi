"""智谱文本重排；失败时返回原 RRF 顺序。"""
from __future__ import annotations

import httpx

from config import settings
from services.logging import get_logger

log = get_logger("reranker")


def rerank_rows(query: str, rows: list[tuple], conn, usage_acc=None, top_n: int = 20) -> list[tuple]:
    if not settings.rerank_enabled or not settings.ai_api_key or len(rows) < 2:
        return rows
    candidates = rows[:top_n]
    documents = [f"{r[2]}\n{r[6]}\n{r[7][:3000]}"[:4096] for r in candidates]
    try:
        response = httpx.post(
            settings.ai_base_url.rstrip("/") + "/rerank",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            json={
                "model": settings.rerank_model, "query": query[:4096],
                "documents": documents, "top_n": len(documents),
                "return_documents": False,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        if usage_acc is not None:
            u = data.get("usage") or {}
            usage_acc.add(prompt=u.get("prompt_tokens", 0), total=u.get("total_tokens", 0))
        ids = [r[0] for r in candidates]
        auth_rows = conn.execute(
            "SELECT id,COALESCE(authority,0.5) FROM notes WHERE id=ANY(%s)", (ids,)
        ).fetchall()
        authority = {r[0]: float(r[1]) for r in auth_rows}
        ranked: list[tuple] = []
        used: set[int] = set()
        for item in data.get("results", []):
            index = int(item["index"])
            if index >= len(candidates):
                continue
            used.add(index)
            row = candidates[index]
            score = 0.9 * float(item.get("relevance_score", 0)) + 0.1 * authority.get(row[0], 0.5)
            ranked.append((*row[:8], score))
        ranked.extend(candidates[i] for i in range(len(candidates)) if i not in used)
        return ranked + rows[top_n:]
    except Exception as exc:
        log.warning("rerank failed, keep RRF order: %s", exc)
        return rows

