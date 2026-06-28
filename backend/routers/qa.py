"""问答（RAG）HTTP 接口。

  POST /qa            基于知识库检索 + LLM 生成带来源的回答
  GET  /qa/history    问答历史

骨架策略：检索部分（找相关来源）无密钥也能跑；生成部分缺 API_KEY 时
降级——返回检索到的来源 + 一句提示，而不是报错。
"""
from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from db import pool
from routers import search as search_mod
from services import llm, quota, usage
from services.auth import CurrentUser, get_current_user

router = APIRouter(tags=["qa"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}
_TOP_K = 5


class QaTurn(BaseModel):
    role: str
    text: str


class QaRequest(BaseModel):
    question: str
    history: list[QaTurn] = []


class Source(BaseModel):
    id: uuid.UUID
    title: str
    type: str


class QaResponse(BaseModel):
    answer: str
    sources: list[Source]
    generated: bool  # True=GLM 生成；False=缺密钥降级


@router.post("/qa", response_model=QaResponse)
def qa(req: QaRequest, user: CurrentUser = Depends(get_current_user)) -> QaResponse:
    question = req.question.strip()
    if not question:
        return QaResponse(answer="请输入问题。", sources=[], generated=False)

    quota.check_quota(user)  # 超当日额度直接 429

    with usage.collect() as u:  # 检索（embedding）+ 生成的 token 都计入
        rows = _retrieve(question)
        sources = [
            Source(id=r[0], title=r[2], type=_TYPE_MAP.get(r[1], "link")) for r in rows
        ]
        context = _build_context(rows)
        try:
            text = llm.answer(
                question, context, [t.model_dump() for t in req.history]
            )
            generated = True
        except Exception:  # noqa: BLE001 — 缺密钥/调用失败时降级，不报错
            generated = False
            if sources:
                text = "（未配置 API_KEY，暂不能生成回答。以下是检索到的相关来源，供参考。）"
            else:
                text = "（未配置 API_KEY，且没有检索到相关来源。）"

    quota.record_usage(user.id, "qa", u)
    _save_history(question, text, [s.id for s in sources], user.id)
    return QaResponse(answer=text, sources=sources, generated=generated)


@router.post("/qa/stream")
async def qa_stream(req: QaRequest, user: CurrentUser = Depends(get_current_user)):
    """流式问答（SSE）。

    事件流：
      event: sources   data: [{id,title,type}, ...]   检索到的来源（先于回答）
      event: token     data: <生成的一小段文本>        逐块推送，前端逐字渲染
      event: done       data: {"generated": true}     结束（含是否真生成）
    缺 API_KEY 时只发 sources + done(generated=false)，与非流式降级行为一致。
    """
    question = req.question.strip()
    if question:
        quota.check_quota(user)  # 超额在开流前抛 429，前端按普通错误处理

    async def event_gen():
        if not question:
            yield {"event": "done", "data": '{"generated": false, "error": "空问题"}'}
            return

        with usage.collect() as u:
            rows = _retrieve(question)
            sources = [
                {"id": str(r[0]), "title": r[2], "type": _TYPE_MAP.get(r[1], "link")}
                for r in rows
            ]
            yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}

            context = _build_context(rows)
            full_answer: list[str] = []
            generated = True
            try:
                async for chunk in llm.answer_stream(
                    question, context, [t.model_dump() for t in req.history]
                ):
                    full_answer.append(chunk)
                    yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}
            except Exception:  # noqa: BLE001 — 缺密钥/调用失败时降级，不报错
                generated = False
                if sources:
                    full_answer.append(
                        "（未配置 API_KEY，暂不能生成回答。以下是检索到的相关来源，供参考。）"
                    )
                else:
                    full_answer.append("（未配置 API_KEY，且没有检索到相关来源。）")

        quota.record_usage(user.id, "qa_stream", u)
        answer_text = "".join(full_answer)
        _save_history(question, answer_text, [uuid.UUID(s["id"]) for s in sources], user.id)
        yield {
            "event": "done",
            "data": json.dumps({"generated": generated}, ensure_ascii=False),
        }

    return EventSourceResponse(event_gen())


@router.get("/qa/history")
def qa_history(
    scope: str = "mine",
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    # 默认只看自己；管理员传 scope=all 看全部
    all_users = user.is_admin and scope == "all"
    where = "" if all_users else "WHERE user_id = %s"
    params: list = [] if all_users else [user.id]
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, question, answer, array_length(source_ids, 1), created_at,
                   to_char(created_at, 'MM-DD HH24:MI') AS when_label
            FROM qa_history
            {where}
            ORDER BY created_at DESC
            LIMIT 30
            """,
            params,
        ).fetchall()
    return {
        "items": [
            {
                "id": r[0],
                "question": r[1],
                "answer_preview": (r[2] or "")[:80],
                "source_count": r[3] or 0,
                "created_at": r[4].isoformat(),
                "relative": r[5],
            }
            for r in rows
        ]
    }


# ---------- 检索 ----------

def _retrieve(question: str) -> list[tuple]:
    """有 API_KEY 走语义检索；否则按问题里的词做关键词召回。"""
    with pool.connection() as conn:
        vec = search_mod._try_embed(question)
        if vec is not None:
            return search_mod._semantic_search(conn, vec, [], "all")[:_TOP_K]
        return _token_search(conn, question)


def _terms(question: str) -> list[str]:
    """从问题里抽召回词：英文/数字整词 + 中文 2-gram（中文无空格，整句匹配不到）。"""
    terms: set[str] = set()
    for t in re.findall(r"[A-Za-z0-9]{2,}", question):
        terms.add(t)
    for run in re.findall(r"[一-鿿]+", question):
        if len(run) >= 2:
            for i in range(len(run) - 1):
                terms.add(run[i : i + 2])
        else:
            terms.add(run)
    return list(terms)[:20]  # 限量，避免 SQL 过长


def _token_search(conn, question: str) -> list[tuple]:
    """召回命中召回词最多的笔记（无密钥时的兜底检索）。"""
    tokens = _terms(question) or [question]
    # 每个 token 一个 ILIKE，命中数作为分数
    score_terms = " + ".join(
        ["(CASE WHEN title || ' ' || COALESCE(summary,'') || ' ' || COALESCE(content,'') ILIKE %s THEN 1 ELSE 0 END)"]
        * len(tokens)
    )
    where_terms = " OR ".join(
        ["title || ' ' || COALESCE(summary,'') || ' ' || COALESCE(content,'') ILIKE %s"] * len(tokens)
    )
    likes = [f"%{t}%" for t in tokens]
    sql = f"""
        SELECT {search_mod._COLS}, ({score_terms}) AS hits
        FROM notes
        WHERE ingest_status = 'done' AND ({where_terms})
        ORDER BY hits DESC, created_at DESC
        LIMIT {_TOP_K}
    """
    return conn.execute(sql, [*likes, *likes]).fetchall()


def _build_context(rows: list[tuple]) -> str:
    """把召回的笔记拼成喂给 LLM 的来源上下文。"""
    blocks = []
    for i, r in enumerate(rows, 1):
        title, summary, content = r[2], r[6], r[7]
        excerpt = (content or summary or "")[:600]
        blocks.append(f"[{i}] {title}\n{summary}\n{excerpt}")
    return "\n\n".join(blocks)


def _save_history(question: str, answer: str, source_ids: list[uuid.UUID], user_id) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO qa_history (question, answer, source_ids, user_id) VALUES (%s, %s, %s, %s)",
            (question, answer, source_ids, user_id),
        )
