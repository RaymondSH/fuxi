"""入库 HTTP 接口。

  POST /ingest/url    {url}              链接入库
  POST /ingest/file   multipart 文件     PDF/Word/Excel/图片 入库
  GET  /ingest/{id}                      查入库状态

入库是慢操作（抓取 + GLM 提炼），所以接口只建 pending 笔记与持久化 job 并立即返回，
独立 job_runner 消费任务。前端拿 note_id 轮询 GET 查状态。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, HttpUrl

from db import pool
from services import audit, quota, spaces
from services.auth import CurrentUser, get_current_user
from workers import ingest_worker

router = APIRouter(prefix="/ingest", tags=["ingest"])

# DB → API 映射（见 docs/api-contract.md）
_STATUS_MAP = {"queued": "pending", "running": "processing", "done": "done", "failed": "failed"}
_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}


class IngestUrlRequest(BaseModel):
    url: HttpUrl
    space_id: uuid.UUID | None = None  # M2：归属空间；None 时用 default 空间


class IngestResponse(BaseModel):
    note_id: uuid.UUID
    status: str


class IngestJob(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    type: str
    title: str
    sub: str = ""
    stage: str
    progress: int
    status: str
    error_msg: str | None = None


class NoteStatus(BaseModel):
    note_id: uuid.UUID
    title: str
    source_type: str
    ingest_status: str
    error_msg: str | None = None
    summary: str | None = None
    tags: list[str] = []


def _resolve_space(admin: CurrentUser, space_id: uuid.UUID | None) -> uuid.UUID:
    """解析入库目标空间：None → default 空间；校验调用者对该空间有 editor+ 权限。

    sysadmin 恒通过；普通用户需是该空间成员且角色 ≥ editor。
    """
    with pool.connection() as conn:
        if space_id is None:
            row = conn.execute("SELECT id FROM spaces WHERE is_default").fetchone()
            if row is None:
                raise HTTPException(status_code=500, detail="default 空间不存在，请先迁移")
            space_id = row[0]
    spaces.assert_space_role(admin, space_id, "editor")
    return space_id


@router.post("/url", response_model=IngestResponse, status_code=202)
def ingest_url(
    req: IngestUrlRequest,
    request: Request,
    admin: CurrentUser = Depends(get_current_user),
) -> IngestResponse:
    url = str(req.url)
    space_id = _resolve_space(admin, req.space_id)
    quota.check_quota(admin)
    note_id = ingest_worker.enqueue_url(url, space_id=space_id, created_by=admin.id)
    audit.log("ingest_url", request=request, user_id=admin.id, target_type="note", target_id=note_id, detail={"url": url, "space_id": str(space_id)})
    return IngestResponse(note_id=note_id, status="pending")


@router.post("/file", response_model=IngestResponse, status_code=202)
async def ingest_file(
    request: Request,
    file: UploadFile = File(...),
    space_id: uuid.UUID | None = None,
    admin: CurrentUser = Depends(get_current_user),
) -> IngestResponse:
    filename = file.filename or "upload"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    sid = _resolve_space(admin, space_id)
    quota.check_quota(admin)
    note_id = ingest_worker.enqueue_file(
        filename, len(data), data=data, space_id=sid, created_by=admin.id
    )
    audit.log(
        "ingest_file", request=request, user_id=admin.id, target_type="note", target_id=note_id,
        detail={"filename": filename, "size": len(data), "space_id": str(sid)},
    )
    return IngestResponse(note_id=note_id, status="pending")


@router.get("/jobs")
def list_jobs(admin: CurrentUser = Depends(get_current_user)) -> dict:
    """入库队列：进行中 + 最近完成的任务，驱动前端进度卡片。

    M2：按用户可见空间过滤（只看自己空间的入库任务）。sysadmin 看全部。
    """
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, admin)
        frag, params = spaces.space_filter_from(sids, "n")
        rows = conn.execute(
            f"""
            SELECT j.id, j.note_id, n.source_type, j.title, j.sub,
                   j.stage, j.progress, j.status, j.error_msg
            FROM jobs j
            JOIN notes n ON n.id = j.note_id
            WHERE j.job_type = 'ingest' AND n.deleted_at IS NULL{frag}
            ORDER BY j.queued_at DESC
            LIMIT 50
            """,
            params,
        ).fetchall()
    items = [
        IngestJob(
            id=r[0],
            note_id=r[1],
            type=_TYPE_MAP.get(r[2], "link"),
            title=r[3] or "",
            sub=r[4] or "",
            stage=r[5] or "queued",
            progress=r[6],
            status=_STATUS_MAP.get(r[7], r[7]),
            error_msg=r[8],
        )
        for r in rows
    ]
    return {"items": items}


@router.get("/{note_id}", response_model=NoteStatus)
def get_status(
    note_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> NoteStatus:
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        frag, params = spaces.space_filter_from(sids)
        row = conn.execute(
            "SELECT title, source_type, ingest_status, error_msg, summary, tags "
            f"FROM notes WHERE id = %s AND deleted_at IS NULL{frag}",
            [note_id, *params],
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    title, source_type, status, error_msg, summary, tags = row
    return NoteStatus(
        note_id=note_id,
        title=title,
        source_type=source_type,
        ingest_status=status,
        error_msg=error_msg,
        summary=summary,
        tags=tags or [],
    )
