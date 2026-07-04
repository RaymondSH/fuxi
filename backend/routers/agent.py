"""M4 治理 Agent 运行、提案和审批 API。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from db import pool
from services import audit, quota, spaces
from services.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])


class RunRequest(BaseModel):
    space_id: uuid.UUID


@router.post("/runs", status_code=202)
def start_run(req: RunRequest, request: Request,
              user: CurrentUser = Depends(get_current_user)) -> dict:
    spaces.assert_space_role(user, req.space_id, "space_admin")
    quota.check_quota(user)
    run_id, job_id = uuid.uuid4(), uuid.uuid4()
    with pool.connection() as conn:
        conn.execute("INSERT INTO agent_runs(id,space_id,created_by) VALUES(%s,%s,%s)",
                     (run_id, req.space_id, user.id))
        conn.execute(
            "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
            "%s,'agent_plan',jsonb_build_object('run_id',%s::text,'space_id',%s::text,"
            "'actor_id',%s::text),'queued','queued','治理 Agent 规划')",
            (job_id, run_id, req.space_id, user.id)
        )
    audit.log("agent_run", request=request, user_id=user.id, target_type="space",
              target_id=req.space_id)
    return {"run_id": run_id, "job_id": job_id}


@router.get("/proposals")
def list_proposals(space_id: uuid.UUID, status: str = "pending",
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    spaces.assert_space_role(user, space_id, "viewer")
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id,note_id,issue_id,action,payload,rationale,status,created_at,error_msg "
            "FROM agent_proposals WHERE space_id=%s AND status=%s ORDER BY created_at DESC",
            (space_id, status),
        ).fetchall()
    return {"items": [{"id": r[0], "note_id": r[1], "issue_id": r[2], "action": r[3],
                       "payload": r[4], "rationale": r[5], "status": r[6],
                       "created_at": r[7].isoformat(), "error_msg": r[8]} for r in rows]}


def _review(proposal_id, approve, user, request):
    with pool.connection() as conn:
        row = conn.execute("SELECT space_id FROM agent_proposals WHERE id=%s",
                           (proposal_id,)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="提案不存在")
    spaces.assert_space_role(user, row[0], "space_admin")
    status = "approved" if approve else "rejected"
    with pool.connection() as conn:
        updated = conn.execute(
            "UPDATE agent_proposals SET status=%s,reviewed_by=%s,reviewed_at=NOW() "
            "WHERE id=%s AND status='pending' RETURNING id",
            (status, user.id, proposal_id),
        ).fetchone()
        if updated is None:
            raise HTTPException(status_code=409, detail="提案已处理")
        job_id = None
        if approve:
            job_id = uuid.uuid4()
            conn.execute(
                "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
                "%s,'proposal_execute',jsonb_build_object('proposal_id',%s::text),"
                "'queued','queued','执行已审批治理提案')", (job_id, proposal_id)
            )
    audit.log(f"agent_proposal_{status}", request=request, user_id=user.id,
              target_type="agent_proposal", target_id=proposal_id)
    return {"id": proposal_id, "status": status, "job_id": job_id}


@router.post("/proposals/{proposal_id}/approve", status_code=202)
def approve(proposal_id: uuid.UUID, request: Request,
            user: CurrentUser = Depends(get_current_user)) -> dict:
    return _review(proposal_id, True, user, request)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: uuid.UUID, request: Request,
           user: CurrentUser = Depends(get_current_user)) -> dict:
    return _review(proposal_id, False, user, request)
