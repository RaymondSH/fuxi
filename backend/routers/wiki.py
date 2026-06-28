"""Wiki 主题页 HTTP 接口。

  GET  /wiki            主题页列表
  GET  /wiki/{slug}     主题页详情（结构化 sections + 观点矛盾 conflict）
  POST /wiki/compile    编译主题页（异步：建占位行 + 后台编译，返回 slug）
  GET  /wiki/{slug}/status  查编译状态（复用 jobs 表）

sections / conflict 以 jsonb 存（见 sql/04_wiki.sql）。详情里把引用到的 note id
解析成 {id,title,type}，方便前端渲染可点击的来源角标。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from db import pool
from workers import compile_worker

router = APIRouter(prefix="/wiki", tags=["wiki"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}


class WikiSummary(BaseModel):
    slug: str
    title: str
    updated: str | None = None
    source_count: int


class WikiDetail(BaseModel):
    slug: str
    title: str
    updated: str | None = None
    source_ids: list[uuid.UUID] = []
    sources: list[dict] = []      # 解析后的来源 [{id,title,type}]
    sections: list[dict] = []     # [{heading, paragraphs:[{text, cites:[id]}]}]
    conflict: dict | None = None  # {topic, sides:[{note_id, claim}]}


class CompileRequest(BaseModel):
    title: str
    source_note_ids: list[uuid.UUID]
    slug: str | None = None  # 留空则据 title 生成


class CompileResponse(BaseModel):
    slug: str
    status: str  # queued


@router.post("/compile", response_model=CompileResponse, status_code=202)
def compile(req: CompileRequest, background: BackgroundTasks) -> CompileResponse:
    """编译主题页：建占位行 + 入队 compile job，后台跑 LLM 综合。

    前端拿 slug 轮询 GET /wiki/{slug}/status，compiled_at 非空即完成。
    """
    if not req.source_note_ids:
        raise HTTPException(status_code=400, detail="至少需要一个来源笔记")
    slug = req.slug or compile_worker._slugify(req.title)
    compile_worker.enqueue_compile(slug, req.title, req.source_note_ids)
    background.add_task(compile_worker.run, slug)
    return CompileResponse(slug=slug, status="queued")


@router.get("/{slug}/status")
def compile_status(slug: str) -> dict:
    """查编译状态：复用 jobs 表的 compile 行（status/stage/progress/error_msg）。"""
    with pool.connection() as conn:
        job = conn.execute(
            """
            SELECT status, stage, progress, error_msg, finished_at
            FROM jobs
            WHERE job_type = 'compile' AND payload->>'slug' = %s
            ORDER BY queued_at DESC LIMIT 1
            """,
            (slug,),
        ).fetchone()
        done = conn.execute(
            "SELECT compiled_at IS NOT NULL FROM wiki_pages WHERE slug = %s",
            (slug,),
        ).fetchone()
    if done is None:
        raise HTTPException(status_code=404, detail="主题页不存在")
    if job is None:
        return {"slug": slug, "status": "idle", "compiled": bool(done and done[0])}
    return {
        "slug": slug,
        "status": job[0],
        "stage": job[1],
        "progress": job[2],
        "error": job[3],
        "compiled": bool(done and done[0]),
    }


@router.get("", response_model=dict)
def list_wiki() -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT slug, title, COALESCE(compiled_at, updated_at),
                   COALESCE(array_length(source_note_ids, 1), 0)
            FROM wiki_pages
            ORDER BY COALESCE(compiled_at, updated_at) DESC
            """
        ).fetchall()
    return {
        "items": [
            WikiSummary(
                slug=r[0], title=r[1],
                updated=r[2].date().isoformat() if r[2] else None,
                source_count=r[3],
            )
            for r in rows
        ]
    }


@router.get("/{slug}", response_model=WikiDetail)
def get_wiki(slug: str) -> WikiDetail:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT slug, title, COALESCE(compiled_at, updated_at),
                   source_note_ids, sections, conflict
            FROM wiki_pages WHERE slug = %s
            """,
            (slug,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="主题页不存在")

        slug_, title, updated, source_ids, sections, conflict = row
        source_ids = source_ids or []
        sources = []
        if source_ids:
            note_rows = conn.execute(
                "SELECT id, title, source_type FROM notes WHERE id = ANY(%s)",
                (source_ids,),
            ).fetchall()
            sources = [
                {"id": str(n[0]), "title": n[1], "type": _TYPE_MAP.get(n[2], "link")}
                for n in note_rows
            ]

    return WikiDetail(
        slug=slug_,
        title=title,
        updated=updated.date().isoformat() if updated else None,
        source_ids=source_ids,
        sources=sources,
        sections=sections or [],
        conflict=conflict,
    )
