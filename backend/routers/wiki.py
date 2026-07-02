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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from db import pool
from services import audit, quota, spaces
from services.auth import CurrentUser, get_current_user
from workers import compile_worker

router = APIRouter(prefix="/wiki", tags=["wiki"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}


class WikiSummary(BaseModel):
    slug: str
    title: str
    updated: str | None = None
    source_count: int
    space_id: uuid.UUID | None = None


class WikiDetail(BaseModel):
    slug: str
    title: str
    updated: str | None = None
    source_ids: list[uuid.UUID] = []
    sources: list[dict] = []      # 解析后的来源 [{id,title,type}]
    sections: list[dict] = []     # [{heading, paragraphs:[{text, cites:[id]}]}]
    conflict: dict | None = None  # {topic, sides:[{note_id, claim}]}
    space_id: uuid.UUID | None = None


class CompileRequest(BaseModel):
    title: str
    source_note_ids: list[uuid.UUID]
    slug: str | None = None  # 留空则据 title 生成
    space_id: uuid.UUID | None = None  # 留空则按来源笔记推断（须同空间）


class CompileResponse(BaseModel):
    slug: str
    status: str  # queued


def _resolve_compile_space(req: CompileRequest, user: CurrentUser) -> uuid.UUID:
    """编译空间解析 + 角色校验。

    来源笔记必须全部同空间；若显式传了 space_id，须与来源一致。校验用户对该空间有 space_admin 权限。
    返回 space_id。
    """
    if not req.source_note_ids:
        raise HTTPException(status_code=400, detail="至少需要一个来源笔记")
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT space_id FROM notes WHERE id = ANY(%s) AND deleted_at IS NULL", (req.source_note_ids,)
        ).fetchall()
    if len(rows) != len(req.source_note_ids):
        raise HTTPException(status_code=400, detail="存在不存在的来源笔记")
    source_spaces = {r[0] for r in rows}
    if len(source_spaces) != 1:
        raise HTTPException(status_code=400, detail="来源笔记必须属于同一空间")
    space_id = next(iter(source_spaces))
    if req.space_id is not None and req.space_id != space_id:
        raise HTTPException(status_code=400, detail="space_id 与来源笔记所在空间不一致")
    spaces.assert_space_role(user, space_id, "space_admin")
    return space_id


@router.post("/compile", response_model=CompileResponse, status_code=202)
def compile(
    req: CompileRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> CompileResponse:
    """编译主题页：建占位行 + 入队 compile job，后台跑 LLM 综合。

    前端拿 slug 轮询 GET /wiki/{slug}/status，compiled_at 非空即完成。

    M2：来源笔记须同空间，编译者需该空间 space_admin 权限。
    """
    space_id = _resolve_compile_space(req, user)
    quota.check_quota(user)
    slug = req.slug or compile_worker._slugify(req.title)
    compile_worker.enqueue_compile(
        slug,
        req.title,
        req.source_note_ids,
        space_id=space_id,
        actor_id=user.id,
    )
    audit.log(
        "wiki_compile", request=request, user_id=user.id, target_type="wiki",
        target_id=slug, detail={"title": req.title, "source_count": len(req.source_note_ids), "space_id": str(space_id)},
    )
    return CompileResponse(slug=slug, status="queued")


@router.get("/{slug}/status")
def compile_status(slug: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """查编译状态：复用 jobs 表的 compile 行（status/stage/progress/error_msg）。

    M2：主题页须在用户可见空间内，否则按 404（不泄露存在性）。
    """
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        sf, sfp = spaces.space_filter_from(sids, alias="wp")
        wiki = conn.execute(
            f"SELECT compiled_at IS NOT NULL FROM wiki_pages wp WHERE slug = %s{sf}",
            [slug, *sfp],
        ).fetchone()
        if wiki is None:
            raise HTTPException(status_code=404, detail="主题页不存在")
        job = conn.execute(
            """
            SELECT status, stage, progress, error_msg, finished_at
            FROM jobs
            WHERE job_type = 'compile' AND payload->>'slug' = %s
            ORDER BY queued_at DESC LIMIT 1
            """,
            (slug,),
        ).fetchone()
    if job is None:
        return {"slug": slug, "status": "idle", "compiled": bool(wiki[0])}
    return {
        "slug": slug,
        "status": job[0],
        "stage": job[1],
        "progress": job[2],
        "error": job[3],
        "compiled": bool(wiki[0]),
    }


@router.get("", response_model=dict)
def list_wiki(user: CurrentUser = Depends(get_current_user)) -> dict:
    """主题页列表。M2：限定用户可见空间（sysadmin 全可见）。"""
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        sf, sfp = spaces.space_filter_from(sids)
        rows = conn.execute(
            f"""
            SELECT slug, title, COALESCE(compiled_at, updated_at),
                   COALESCE(array_length(source_note_ids, 1), 0), space_id
            FROM wiki_pages
            WHERE NOT EXISTS (
                SELECT 1 FROM unnest(source_note_ids) AS sid(note_id)
                JOIN notes sn ON sn.id=sid.note_id WHERE sn.deleted_at IS NOT NULL
            ){sf}
            ORDER BY COALESCE(compiled_at, updated_at) DESC
            """,
            sfp,
        ).fetchall()
    return {
        "items": [
            WikiSummary(
                slug=r[0], title=r[1],
                updated=r[2].date().isoformat() if r[2] else None,
                source_count=r[3],
                space_id=r[4],
            )
            for r in rows
        ]
    }


@router.get("/{slug}", response_model=WikiDetail)
def get_wiki(slug: str, user: CurrentUser = Depends(get_current_user)) -> WikiDetail:
    """主题页详情。M2：不可见空间的主题页按 404（不泄露存在性）。

    sources 里的来源笔记也按可见空间过滤，避免异空间 note id 串入。
    """
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        sf, sfp = spaces.space_filter_from(sids)
        row = conn.execute(
            f"""
            SELECT slug, title, COALESCE(compiled_at, updated_at),
                   source_note_ids, sections, conflict, space_id
            FROM wiki_pages WHERE slug = %s
              AND NOT EXISTS (
                SELECT 1 FROM unnest(source_note_ids) AS sid(note_id)
                JOIN notes sn ON sn.id=sid.note_id WHERE sn.deleted_at IS NOT NULL
              ){sf}
            """,
            [slug, *sfp],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="主题页不存在")

        slug_, title, updated, source_ids, sections, conflict, space_id = row
        source_ids = source_ids or []
        sources = []
        if source_ids:
            # 来源笔记同样限可见空间：万一主题页被改了来源 id 也读不出异空间笔记
            note_rows = conn.execute(
                f"""
                SELECT id, title, source_type FROM notes
                WHERE id = ANY(%s) AND ingest_status = 'done' AND deleted_at IS NULL{sf}
                """,
                [source_ids, *sfp],
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
        space_id=space_id,
    )
