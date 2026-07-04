"""M3 治理待办与扫描 API。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from db import pool
from services import audit, quota, spaces
from services.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/issues")
def list_issues(
    space_id: uuid.UUID, status: str = "open", type: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_space_role(user, space_id, "viewer")
    where, params = ["space_id=%s", "status=%s"], [space_id, status]
    if type:
        where.append("issue_type=%s"); params.append(type)
    clause = " AND ".join(where)
    offset = (page - 1) * size
    with pool.connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM governance_issues WHERE {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id,note_id,issue_type,severity,status,title,evidence,last_seen_at
            FROM governance_issues WHERE {clause}
            ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                     last_seen_at DESC
            LIMIT %s OFFSET %s
            """,
            [*params, size, offset],
        ).fetchall()
    return {
        "items": [
            {"id": r[0], "note_id": r[1], "type": r[2], "severity": r[3],
             "status": r[4], "title": r[5], "evidence": r[6],
             "last_seen_at": r[7].isoformat()} for r in rows
        ],
        "total": total, "page": page, "size": size,
    }


class ScanRequest(BaseModel):
    space_id: uuid.UUID


@router.post("/scans", status_code=202)
def start_scan(
    req: ScanRequest, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_space_role(user, req.space_id, "space_admin")
    quota.check_quota(user)
    run_id, job_id = uuid.uuid4(), uuid.uuid4()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO governance_runs(id,space_id,created_by) VALUES(%s,%s,%s)",
            (run_id, req.space_id, user.id),
        )
        conn.execute(
            """
            INSERT INTO jobs(id,job_type,payload,status,stage,title)
            VALUES(%s,'governance_scan',
                   jsonb_build_object('run_id',%s::text,'space_id',%s::text,'actor_id',%s::text),
                   'queued','queued','知识治理巡检')
            """,
            (job_id, run_id, req.space_id, user.id),
        )
    audit.log("governance_scan", request=request, user_id=user.id,
              target_type="space", target_id=req.space_id)
    # run 行默认 status='queued'；对外映射成 pending 与 ingest.status 枚举一致
    return {"run_id": run_id, "job_id": job_id, "status": "pending"}


@router.get("/runs")
def list_runs(
    space_id: uuid.UUID,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_space_role(user, space_id, "viewer")
    offset = (page - 1) * size
    with pool.connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM governance_runs WHERE space_id=%s", (space_id,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT id,status,stats,error_msg,created_at,finished_at FROM governance_runs "
            "WHERE space_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (space_id, size, offset),
        ).fetchall()
    # run 状态用独立词表 queued/running/done/failed；对外映射到前端轮询习惯的
    # pending/processing/done/failed（与 ingest.status 枚举对齐）。
    _STATUS_MAP = {"queued": "pending", "running": "processing", "done": "done", "failed": "failed"}
    return {
        "items": [
            {"id": r[0], "status": _STATUS_MAP.get(r[1], r[1]), "stats": r[2], "error_msg": r[3],
             "created_at": r[4].isoformat(),
             "finished_at": r[5].isoformat() if r[5] else None} for r in rows
        ],
        "total": total, "page": page, "size": size,
    }


class IssuePatch(BaseModel):
    status: str
    resolution_note: str | None = None


@router.patch("/issues/{issue_id}")
def update_issue(
    issue_id: uuid.UUID, req: IssuePatch, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    if req.status not in ("open", "resolved", "ignored"):
        raise HTTPException(status_code=422, detail="非法治理状态")
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT space_id FROM governance_issues WHERE id=%s", (issue_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="治理待办不存在")
    spaces.assert_space_role(user, row[0], "editor")
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE governance_issues SET status=%s,resolution_note=%s,
                resolved_at=CASE WHEN %s='open' THEN NULL ELSE NOW() END,
                resolved_by=CASE WHEN %s='open' THEN NULL ELSE %s END
            WHERE id=%s
            """,
            (req.status, req.resolution_note, req.status, req.status, user.id, issue_id),
        )
    audit.log("governance_issue_update", request=request, user_id=user.id,
              target_type="governance_issue", target_id=issue_id,
              detail={"status": req.status})
    return {"id": issue_id, "status": req.status}
