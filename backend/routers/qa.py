"""问答（RAG）HTTP 接口。

  POST /qa            基于知识库检索 + LLM 生成带来源的回答
  GET  /qa/history    问答历史

骨架策略：检索部分（找相关来源）无密钥也能跑；生成部分缺 API_KEY 时
降级——返回检索到的来源 + 一句提示，而不是报错。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from db import pool
from routers import search as search_mod
from services import guardrails, llm, quota, reranker, spaces, usage
from services.auth import CurrentUser, get_current_user
from services.providers.base import QaStyle

router = APIRouter(tags=["qa"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}
_TOP_K = 5
_QA_RECALL_K = 2  # 回灌：从 generated_qa 取最相似的 N 条问答对拼进上下文
_VALID_STYLES = ("default", "executive", "technical", "eli5")


def _normalize_style(s: str) -> QaStyle:
    """把请求里的 style 字符串收敛到合法枚举，非法值回退 default。"""
    return s if s in _VALID_STYLES else "default"


class QaTurn(BaseModel):
    role: str
    text: str


class QaRequest(BaseModel):
    question: str
    history: list[QaTurn] = []
    style: str = "default"  # default | executive | technical | eli5


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
        safe_question, _ = guardrails.mask_pii(question)
        with pool.connection() as conn:
            sids = spaces.visible_space_ids(conn, user)
        rows, qa_pairs = _retrieve(safe_question, sids)
        sources = [
            Source(id=r[0], title=r[2], type=_TYPE_MAP.get(r[1], "link")) for r in rows
        ]
        context, _ = guardrails.mask_pii(_build_context(rows, qa_pairs))
        if not sources:
            text = "知识库中没有足够来源回答这个问题。"
            generated = False
        else:
            try:
                text = llm.answer(
                    safe_question, context, [t.model_dump() for t in req.history],
                    style=_normalize_style(req.style),
                )
                generated = True
            except Exception:  # noqa: BLE001 — 缺密钥/调用失败时降级，不报错
                generated = False
                text = "（模型暂不可用。以下是检索到的相关来源，供参考。）"

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

        style = _normalize_style(req.style)

        with usage.collect() as u:
            # _retrieve 内含同步阻塞的 embedding 调用，放进线程池跑，
            # 避免占用 event loop 影响流式问答期间的并发请求。
            safe_question, _ = guardrails.mask_pii(question)
            with pool.connection() as conn:
                sids = spaces.visible_space_ids(conn, user)
            rows, qa_pairs = await asyncio.to_thread(_retrieve, safe_question, sids)
            sources = [
                {"id": str(r[0]), "title": r[2], "type": _TYPE_MAP.get(r[1], "link")}
                for r in rows
            ]
            yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}

            context, _ = guardrails.mask_pii(_build_context(rows, qa_pairs))
            full_answer: list[str] = []
            generated = bool(sources)
            try:
                if not sources:
                    raise LookupError("no evidence")
                async for chunk in llm.answer_stream(
                    safe_question, context, [t.model_dump() for t in req.history], style=style
                ):
                    full_answer.append(chunk)
                    yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}
            except Exception:  # noqa: BLE001 — 缺密钥/调用失败时降级，不报错
                generated = False
                if sources:
                    fallback = "（未配置 API_KEY，暂不能生成回答。以下是检索到的相关来源，供参考。）"
                else:
                    fallback = "知识库中没有足够来源回答这个问题。"
                # 降级文案也要作为 token 推给前端，否则前端会收到空回答
                full_answer.append(fallback)
                yield {"event": "token", "data": json.dumps({"text": fallback}, ensure_ascii=False)}

        quota.record_usage(user.id, "qa_stream", u)
        answer_text = "".join(full_answer)
        _save_history(question, answer_text, [uuid.UUID(s["id"]) for s in sources], user.id)
        yield {
            "event": "done",
            "data": json.dumps({"generated": generated}, ensure_ascii=False),
        }

    return EventSourceResponse(event_gen())


@router.post("/qa/agentic/stream")
async def qa_agentic_stream(req: QaRequest, user: CurrentUser = Depends(get_current_user)):
    """有界深度问答：最多 3 个子查询，ACL 召回、重排、回答与引用校验。"""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")
    quota.check_quota(user)

    async def event_gen():
        with usage.collect() as u:
            safe_question, q_masked = guardrails.mask_pii(question)
            try:
                plan = await asyncio.to_thread(llm.plan_queries, safe_question)
                queries = plan.queries[:3] or [safe_question]
            except Exception:
                queries = [safe_question]
            yield {"event": "plan", "data": json.dumps({"queries": queries}, ensure_ascii=False)}

            with pool.connection() as conn:
                sids = spaces.visible_space_ids(conn, user)
            rows = await asyncio.to_thread(_agentic_retrieve, queries, sids, u)
            sources = [
                {"id": str(r[0]), "title": r[2], "type": _TYPE_MAP.get(r[1], "link")}
                for r in rows
            ]
            yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}
            context, c_masked = guardrails.mask_pii(_build_context(rows, []))
            answer_parts: list[str] = []
            generated = bool(sources)
            try:
                if not sources:
                    raise LookupError("no evidence")
                async for chunk in llm.answer_stream(
                    safe_question, context, [t.model_dump() for t in req.history],
                    style=_normalize_style(req.style),
                ):
                    answer_parts.append(chunk)
                    yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}
            except Exception:
                generated = False
                fallback = "证据不足，暂时无法生成可靠回答。" if not sources else "模型暂时不可用，请先查看检索来源。"
                answer_parts.append(fallback)
                yield {"event": "token", "data": json.dumps({"text": fallback}, ensure_ascii=False)}

        answer = "".join(answer_parts)
        verification = guardrails.verify_citations(answer, len(sources))
        yield {"event": "verification", "data": json.dumps(verification, ensure_ascii=False)}
        trace = {"queries": queries, "source_ids": [s["id"] for s in sources]}
        _save_history(
            question, answer, [uuid.UUID(s["id"]) for s in sources], user.id,
            mode="agentic", trace=trace, verification=verification,
        )
        quota.record_usage(user.id, "qa_agentic", u)
        yield {"event": "done", "data": json.dumps({
            "generated": generated, "mode": "agentic", "pii_masked": q_masked or c_masked,
        }, ensure_ascii=False)}

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

def _retrieve(question: str, space_ids: list[uuid.UUID] | None = None) -> tuple[list[tuple], list[tuple]]:
    """检索来源笔记 + 回灌历史问答对。

    有 API_KEY 时走语义检索（notes + generated_qa），否则按问题里的词做关键词召回
    （generated_qa 无向量时无法语义召回，故只回退笔记）。

    返回 (note_rows, qa_pairs)，qa_pairs 形如 [(question, answer), ...]。

    space_ids 限定检索空间：None=全可见（仅 sysadmin），
    列表=仅这些空间。HTTP 路由先 spaces.visible_space_ids(conn, user) 算好再传入，
    MCP 用 token 绑定的单个空间包成列表传入，解耦于 CurrentUser。
    """
    sf, sfp = spaces.space_filter_from(space_ids)
    with pool.connection() as conn:
        vec = search_mod._try_embed(question)
        if vec is not None:
            rows = search_mod._semantic_search(conn, vec, [], "all", sf, sfp)[:_TOP_K]
            qa_pairs = _retrieve_generated_qa(conn, vec, sf, sfp)
            return rows, qa_pairs
        return _token_search(conn, question, sf, sfp), []


def _agentic_retrieve(
    queries: list[str], space_ids: list[uuid.UUID] | None, usage_acc,
) -> list[tuple]:
    """每个子问题走混合召回+重排，按首次最优顺序去重。"""
    sf, sfp = spaces.space_filter_from(space_ids)
    es_sids = [str(i) for i in space_ids] if space_ids is not None else None
    merged: list[tuple] = []
    seen: set[uuid.UUID] = set()
    with pool.connection() as conn:
        for query in queries[:3]:
            kw = search_mod._keyword_search(conn, query, [], "all", sf, sfp, es_sids)
            vec = search_mod._try_embed(query)
            sem = search_mod._semantic_search(conn, vec, [], "all", sf, sfp) if vec else []
            rows = search_mod._rrf_fuse(kw, sem) if sem else kw
            rows = reranker.rerank_rows(query, rows, conn, usage_acc=usage_acc, top_n=20)
            for row in rows:
                if row[0] not in seen:
                    seen.add(row[0]); merged.append(row)
                if len(merged) >= 8:
                    break
    return merged[:8]


def _retrieve_generated_qa(conn, vec, space_frag: str = "", space_params: list | None = None) -> list[tuple]:
    """回灌：按问题向量从 generated_qa 取余弦 top-N 问答对。

    generated_qa 无 space_id 列，但 note_id 指向 notes，故 JOIN notes 注入空间过滤。
    """
    rows = conn.execute(
        f"""
        SELECT gq.question, gq.answer
        FROM generated_qa gq
        JOIN notes ON notes.id = gq.note_id
        WHERE gq.embedding IS NOT NULL AND notes.deleted_at IS NULL{space_frag}
        ORDER BY gq.embedding <=> %s::vector
        LIMIT {_QA_RECALL_K}
        """,
        [*(space_params or []), vec],
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


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


def _token_search(conn, question: str, space_frag: str = "", space_params: list | None = None) -> list[tuple]:
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
        WHERE ingest_status = 'done' AND deleted_at IS NULL AND ({where_terms}){space_frag}
        ORDER BY hits DESC, created_at DESC
        LIMIT {_TOP_K}
    """
    return conn.execute(sql, [*likes, *likes, *(space_params or [])]).fetchall()


def _build_context(rows: list[tuple], qa_pairs: list[tuple] | None = None) -> str:
    """把召回的笔记拼成喂给 LLM 的来源上下文。

    若有回灌的历史问答对，置于来源之前，标注为「已沉淀问答」，供模型优先复用。
    """
    blocks: list[str] = []
    if qa_pairs:
        qa_lines = ["以下是知识库里已沉淀的相关问答，可直接参考："]
        for i, (q, a) in enumerate(qa_pairs, 1):
            qa_lines.append(f"Q{i}: {q}\nA{i}: {a}")
        blocks.append("\n".join(qa_lines))
    for i, r in enumerate(rows, 1):
        title, summary, content = r[2], r[6], r[7]
        excerpt = (content or summary or "")[:600]
        blocks.append(f"[{i}] {title}\n{summary}\n{excerpt}")
    return "\n\n".join(blocks)


def _save_history(
    question: str, answer: str, source_ids: list[uuid.UUID], user_id,
    *, mode: str = "standard", trace: dict | None = None, verification: dict | None = None,
) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO qa_history "
            "(question,answer,source_ids,user_id,mode,trace,verification) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
            (question, answer, source_ids, user_id, mode,
             json.dumps(trace or {}, ensure_ascii=False),
             json.dumps(verification or {}, ensure_ascii=False)),
        )
