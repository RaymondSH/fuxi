"""入库 HTTP 接口。

  POST /ingest/url    {url}              链接入库
  POST /ingest/file   multipart 文件     PDF/Word/Excel/图片 入库
  GET  /ingest/{id}                      查入库状态

入库是慢操作（抓取 + GLM 提炼），所以接口只建一条 pending 笔记并立即返回 note_id，
真正的处理丢进 BackgroundTasks 异步跑。前端拿 note_id 轮询 GET 查状态。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from db import pool
from workers import ingest_worker

router = APIRouter(prefix="/ingest", tags=["ingest"])

# DB → API 映射（见 docs/api-contract.md）
_STATUS_MAP = {"queued": "pending", "running": "processing", "done": "done", "failed": "failed"}
_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}


class IngestUrlRequest(BaseModel):
    url: HttpUrl


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


@router.post("/url", response_model=IngestResponse, status_code=202)
def ingest_url(req: IngestUrlRequest, background: BackgroundTasks) -> IngestResponse:
    url = str(req.url)
    note_id = ingest_worker.enqueue_url(url)
    background.add_task(ingest_worker.run, note_id, url=url)
    return IngestResponse(note_id=note_id, status="pending")


@router.post("/file", response_model=IngestResponse, status_code=202)
async def ingest_file(
    background: BackgroundTasks, file: UploadFile = File(...)
) -> IngestResponse:
    filename = file.filename or "upload"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    note_id = ingest_worker.enqueue_file(filename, len(data))
    background.add_task(ingest_worker.run, note_id, data=data, filename=filename)
    return IngestResponse(note_id=note_id, status="pending")


@router.get("/jobs")
def list_jobs() -> dict:
    """入库队列：进行中 + 最近完成的任务，驱动前端进度卡片。"""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT j.id, j.note_id, n.source_type, j.title, j.sub,
                   j.stage, j.progress, j.status, j.error_msg
            FROM jobs j
            JOIN notes n ON n.id = j.note_id
            WHERE j.job_type = 'ingest'
            ORDER BY j.queued_at DESC
            LIMIT 50
            """
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
def get_status(note_id: uuid.UUID) -> NoteStatus:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT title, source_type, ingest_status, error_msg, summary, tags "
            "FROM notes WHERE id = %s",
            (note_id,),
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
