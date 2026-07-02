"""M4 订阅、站内通知与问答反馈。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db import pool
from services import spaces
from services.auth import CurrentUser, get_current_user, require_admin

router = APIRouter(tags=["collaboration"])


class SubscriptionCreate(BaseModel):
    space_id: uuid.UUID
    scope_type: str
    scope_value: str


@router.get("/subscriptions")
def list_subscriptions(user: CurrentUser = Depends(get_current_user)) -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id,space_id,scope_type,scope_value,created_at FROM subscriptions "
            "WHERE user_id=%s ORDER BY created_at DESC", (user.id,)
        ).fetchall()
    return {"items": [{"id": r[0], "space_id": r[1], "scope_type": r[2],
                       "scope_value": r[3], "created_at": r[4].isoformat()} for r in rows]}


@router.post("/subscriptions", status_code=201)
def create_subscription(req: SubscriptionCreate,
                        user: CurrentUser = Depends(get_current_user)) -> dict:
    spaces.assert_space_role(user, req.space_id, "viewer")
    if req.scope_type not in ("space", "tag", "note"):
        raise HTTPException(status_code=422, detail="非法订阅范围")
    if req.scope_type == "note":
        try:
            note_id = uuid.UUID(req.scope_value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="note scope_value 必须为 UUID") from exc
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM notes WHERE id=%s AND space_id=%s AND deleted_at IS NULL",
                (note_id, req.space_id),
            ).fetchone()
        if row is None: raise HTTPException(status_code=404, detail="笔记不存在")
    sub_id = uuid.uuid4()
    with pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO subscriptions(id,user_id,space_id,scope_type,scope_value)
            VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(user_id,space_id,scope_type,scope_value)
            DO UPDATE SET scope_value=EXCLUDED.scope_value RETURNING id
            """,
            (sub_id, user.id, req.space_id, req.scope_type, req.scope_value),
        ).fetchone()
    return {"id": row[0]}


@router.delete("/subscriptions/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: uuid.UUID,
                        user: CurrentUser = Depends(get_current_user)) -> None:
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM subscriptions WHERE id=%s AND user_id=%s",
                           (subscription_id, user.id))
    if cur.rowcount == 0: raise HTTPException(status_code=404, detail="订阅不存在")


@router.get("/notifications")
def list_notifications(
    unread_only: bool = False, user: CurrentUser = Depends(get_current_user),
) -> dict:
    extra = "AND read_at IS NULL" if unread_only else ""
    acl = "" if user.is_admin else (
        "AND EXISTS (SELECT 1 FROM space_members sm "
        "WHERE sm.space_id=notifications.space_id AND sm.user_id=%s)"
    )
    params = [user.id] if user.is_admin else [user.id, user.id]
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT id,title,body,link,read_at,created_at FROM notifications "
            f"WHERE user_id=%s {acl} {extra} ORDER BY created_at DESC LIMIT 100", params
        ).fetchall()
        unread = conn.execute(
            f"SELECT COUNT(*) FROM notifications WHERE user_id=%s {acl} AND read_at IS NULL",
            params,
        ).fetchone()[0]
    return {"unread": unread, "items": [{"id": r[0], "title": r[1], "body": r[2],
                                         "link": r[3], "read_at": r[4].isoformat() if r[4] else None,
                                         "created_at": r[5].isoformat()} for r in rows]}


class ReadRequest(BaseModel):
    ids: list[uuid.UUID] | None = None


@router.post("/notifications/read")
def mark_read(req: ReadRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    with pool.connection() as conn:
        if req.ids:
            cur = conn.execute(
                "UPDATE notifications SET read_at=NOW() WHERE user_id=%s AND id=ANY(%s)",
                (user.id, req.ids),
            )
        else:
            cur = conn.execute(
                "UPDATE notifications SET read_at=NOW() WHERE user_id=%s AND read_at IS NULL",
                (user.id,),
            )
    return {"updated": cur.rowcount}


class FeedbackRequest(BaseModel):
    rating: str
    reason: str | None = None


@router.put("/qa/history/{history_id}/feedback")
def put_feedback(history_id: uuid.UUID, req: FeedbackRequest,
                 user: CurrentUser = Depends(get_current_user)) -> dict:
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating 必须为 up/down")
    with pool.connection() as conn:
        owned = conn.execute(
            "SELECT 1 FROM qa_history WHERE id=%s AND user_id=%s", (history_id, user.id)
        ).fetchone()
        if owned is None: raise HTTPException(status_code=404, detail="问答记录不存在")
        row = conn.execute(
            """
            INSERT INTO qa_feedback(qa_history_id,user_id,rating,reason)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(qa_history_id,user_id) DO UPDATE SET
                rating=EXCLUDED.rating,reason=EXCLUDED.reason,updated_at=NOW()
            RETURNING id
            """,
            (history_id, user.id, req.rating, req.reason),
        ).fetchone()
    return {"id": row[0], "rating": req.rating}


@router.get("/qa/feedback")
def list_feedback(
    rating: str = Query("down"), admin: CurrentUser = Depends(require_admin),
) -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT f.id,f.rating,f.reason,h.question,h.answer,f.created_at,u.email
            FROM qa_feedback f JOIN qa_history h ON h.id=f.qa_history_id
            JOIN users u ON u.id=f.user_id WHERE f.rating=%s
            ORDER BY f.created_at DESC LIMIT 100
            """,
            (rating,),
        ).fetchall()
    return {"items": [{"id": r[0], "rating": r[1], "reason": r[2],
                       "question": r[3], "answer": r[4], "created_at": r[5].isoformat(),
                       "user": r[6]} for r in rows]}
