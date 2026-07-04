"""笔记 HTTP 接口。

  GET    /notes                 笔记列表（分页 / 类型 / 标签过滤）
  GET    /notes/{id}            单篇详情（含实体、要点、正文分段）
  POST   /notes/{id}/generate-qa  触发文档→Q&A 生成（admin，后台跑）
  GET    /notes/{id}/qa           该笔记已生成的问答对
  DELETE /notes/{id}             删除（admin）

正文 original 由 notes.content 按空行切成段落数组返回，对齐前端渲染。
"""
from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from db import pool
from services import audit, lifecycle, quota, spaces
from services.auth import CurrentUser, get_current_user
from workers import qa_gen_worker

router = APIRouter(prefix="/notes", tags=["notes"])

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel", "image": "image", "manual": "link"}
# 实体类别收敛到前端的三类着色
_CAT_MAP = {"concept": "concept", "product": "product", "company": "company"}

# 列表与详情共用的列选取顺序
_LIST_COLS = "id, source_type, title, COALESCE(source,''), published_date, tags, COALESCE(summary,'')"


class NoteSummary(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    source: str = ""
    date: str | None = None
    tags: list[str] = []
    summary: str = ""


class NoteListResponse(BaseModel):
    items: list[NoteSummary]
    total: int
    page: int
    size: int


@router.get("", response_model=NoteListResponse)
def list_notes(
    q: str = Query("", description="标题/摘要模糊匹配"),
    type: str | None = Query(None, description="api 类型：link/pdf/word/excel/image"),
    tag: str | None = Query(None, description="单标签过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> NoteListResponse:
    """笔记浏览列表。按创建时间倒序，支持类型 / 标签 / 关键词过滤。

    本期仅展示 ingest_status='done' 的笔记（入库异常排查仍走 /ingest/jobs）。
    M2：按用户可见空间过滤（sysadmin 看全部）。
    """
    where = ["ingest_status = 'done'", "deleted_at IS NULL"]
    params: list = []
    # M2 空间 ACL
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
    space_frag, space_params = spaces.space_filter_from(sids)
    if space_frag:
        where.append(space_frag[5:])  # 去掉前导 " AND "
        params.extend(space_params)
    # api 类型 → DB source_type
    if type:
        reverse = {v: k for k, v in _TYPE_MAP.items()}
        st = reverse.get(type)
        if st:
            where.append("source_type = %s")
            params.append(st)
    if tag:
        where.append("%s = ANY(tags)")
        params.append(tag)
    if q.strip():
        where.append("(title ILIKE %s OR COALESCE(summary,'') ILIKE %s)")
        like = f"%{q.strip()}%"
        params.extend([like, like])

    clause = " AND ".join(where)
    offset = (page - 1) * size
    with pool.connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM notes WHERE {clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT {_LIST_COLS} FROM notes WHERE {clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            [*params, size, offset],
        ).fetchall()
    return NoteListResponse(
        items=[
            NoteSummary(
                id=r[0],
                type=_TYPE_MAP.get(r[1], "link"),
                title=r[2],
                source=r[3],
                date=r[4].isoformat() if r[4] else None,
                tags=r[5] or [],
                summary=r[6],
            )
            for r in rows
        ],
        total=total,
        page=page,
        size=size,
    )


@router.get("/trash", response_model=NoteListResponse)
def list_trash(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> NoteListResponse:
    """回收站；普通用户只看其 editor+ 空间，sysadmin 看全部。"""
    params: list = []
    membership = ""
    if not user.is_admin:
        membership = (
            "AND EXISTS (SELECT 1 FROM space_members sm WHERE sm.space_id=notes.space_id "
            "AND sm.user_id=%s AND sm.role IN ('editor','space_admin'))"
        )
        params.append(user.id)
    offset = (page - 1) * size
    with pool.connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM notes WHERE deleted_at IS NOT NULL {membership}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT {_LIST_COLS} FROM notes WHERE deleted_at IS NOT NULL {membership} "
            "ORDER BY deleted_at DESC LIMIT %s OFFSET %s",
            [*params, size, offset],
        ).fetchall()
    return NoteListResponse(
        items=[NoteSummary(
            id=r[0], type=_TYPE_MAP.get(r[1], "link"), title=r[2], source=r[3],
            date=r[4].isoformat() if r[4] else None, tags=r[5] or [], summary=r[6],
        ) for r in rows],
        total=total, page=page, size=size,
    )


class EntityRef(BaseModel):
    id: uuid.UUID
    name: str
    cat: str


class NoteDetail(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    source: str = ""
    url: str | None = None
    date: str | None = None
    tags: list[str] = []
    entities: list[EntityRef] = []
    summary: str = ""
    keypoints: list[str] = []
    original: list[str] = []
    related_note_ids: list[uuid.UUID] = []
    revision: int = 1
    authority: float = 0.5
    can_edit: bool = False
    can_delete: bool = False
    refresh_policy: str = "manual"
    source_status: str = "active"
    space_id: uuid.UUID


@router.get("/{note_id}", response_model=NoteDetail)
def get_note(note_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> NoteDetail:
    # M2：先取笔记 + 其空间，校验用户对该空间可见（无权按 404，不泄露存在性）
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT notes.id, notes.source_type, notes.title, COALESCE(notes.source,''),
                   notes.url, notes.published_date, notes.tags, COALESCE(notes.summary,''),
                   notes.key_points, COALESCE(notes.content,''), notes.related_note_ids,
                   notes.space_id, notes.revision, COALESCE(notes.authority,0.5),
                   COALESCE(s.refresh_policy,'manual'),COALESCE(s.status,'active')
            FROM notes LEFT JOIN source_documents s ON s.id=notes.source_document_id
            WHERE notes.id = %s AND notes.deleted_at IS NULL
            """,
            (note_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="笔记不存在")
        # sysadmin 全可见；普通用户需是该空间成员
        space_id = row[11]
        if space_id is None:
            raise HTTPException(status_code=404, detail="笔记不存在")
        if not user.is_admin:
            member = conn.execute(
                "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s",
                (space_id, user.id),
            ).fetchone()
            if member is None:
                raise HTTPException(status_code=404, detail="笔记不存在")  # 无权按 404
        # 浏览计数 +1（详情被打开即计一次）
        conn.execute("UPDATE notes SET views_count = views_count + 1 WHERE id = %s", (note_id,))

        entity_rows = conn.execute(
            """
            SELECT e.id, e.name, e.type
            FROM note_entities ne JOIN entities e ON e.id = ne.entity_id
            WHERE ne.note_id = %s
            ORDER BY ne.mention_count DESC, e.name
            """,
            (note_id,),
        ).fetchall()

        related = row[10] or []
        if related:
            visible_related = conn.execute(
                """
                SELECT id FROM notes
                WHERE id = ANY(%s) AND space_id = %s AND ingest_status = 'done'
                  AND deleted_at IS NULL
                """,
                (related, space_id),
            ).fetchall()
            related = [r[0] for r in visible_related]

        role = spaces.role_in_space(conn, user, space_id)

    (nid, source_type, title, source, url, pub_date,
     tags, summary, key_points, content, _related, _space_id, revision, authority,
     refresh_policy, source_status) = row

    return NoteDetail(
        id=nid,
        type=_TYPE_MAP.get(source_type, "link"),
        title=title,
        source=source,
        url=url,
        date=pub_date.isoformat() if pub_date else None,
        tags=tags or [],
        entities=[
            EntityRef(id=e[0], name=e[1], cat=_CAT_MAP.get(e[2], "concept"))
            for e in entity_rows
        ],
        summary=summary,
        keypoints=key_points or [],
        original=[p.strip() for p in content.split("\n\n") if p.strip()],
        related_note_ids=related,
        revision=revision,
        authority=float(authority),
        can_edit=spaces._ROLE_LEVEL.get(role or "", 0) >= spaces._ROLE_LEVEL["editor"],
        can_delete=spaces._ROLE_LEVEL.get(role or "", 0) >= spaces._ROLE_LEVEL["space_admin"],
        refresh_policy=refresh_policy,
        source_status=source_status,
        space_id=space_id,
    )


@router.post("/{note_id}/generate-qa", status_code=202)
def trigger_generate_qa(
    note_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """触发文档→Q&A 生成：建 qa_gen job，后台跑生成流程，立即返回。

    M2：需该空间 editor+ 权限（sysadmin 恒通过）。
    """
    spaces.assert_note_role(user, note_id, "editor")
    quota.check_quota(user)
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id FROM notes WHERE id = %s AND ingest_status = 'done' AND deleted_at IS NULL", (note_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="笔记不存在或未入库完成")
    qa_gen_worker.enqueue_qa_gen(note_id, actor_id=user.id)
    audit.log("qa_gen_trigger", request=request, user_id=user.id,
              target_type="note", target_id=note_id)
    return {"note_id": note_id, "status": "pending"}


class GeneratedQaItem(BaseModel):
    question: str
    answer: str


@router.get("/{note_id}/qa", response_model=dict)
def list_generated_qa(note_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> dict:
    """该笔记已生成的问答对（最新一批）。

    M2：需该空间可见（viewer+；sysadmin 恒通过）。
    """
    spaces.assert_note_role(user, note_id, "viewer")
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT question, answer FROM generated_qa WHERE note_id = %s "
            "ORDER BY created_at",
            (note_id,),
        ).fetchall()
    return {"items": [GeneratedQaItem(question=r[0], answer=r[1]) for r in rows]}


class NotePatch(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    date: datetime.date | None = None
    authority: float | None = None


class SourcePolicyPatch(BaseModel):
    refresh_policy: str


@router.patch("/{note_id}", status_code=202)
def update_note(
    note_id: uuid.UUID, req: NotePatch, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_note_role(user, note_id, "editor")
    values = req.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="没有可更新字段")
    if "authority" in values and values["authority"] is not None and not 0 <= values["authority"] <= 1:
        raise HTTPException(status_code=422, detail="authority 必须在 0~1")
    for required in ("title", "content", "tags", "authority"):
        if required in values and values[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} 不能为 null")
    if "date" in values:
        values["published_date"] = values.pop("date")
    allowed = {"title", "content", "tags", "published_date", "authority"}
    with pool.connection() as conn:
        if conn.execute(
            "SELECT 1 FROM notes WHERE id=%s AND deleted_at IS NULL", (note_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="笔记不存在")
        lifecycle.save_version(conn, note_id, "edit", user.id)
        fields = [k for k in values if k in allowed]
        assignments = ", ".join(f"{k} = %s" for k in fields)
        # 仅正文实际变化时才删除已生成 QA（payload 带 content 但值不变不触发）
        content_changed = False
        if "content" in values:
            old = conn.execute("SELECT content FROM notes WHERE id=%s", (note_id,)).fetchone()
            content_changed = old is not None and old[0] != values["content"]
        conn.execute(
            f"UPDATE notes SET {assignments} WHERE id = %s AND deleted_at IS NULL",
            [*(values[k] for k in fields), note_id],
        )
        if content_changed:
            conn.execute("DELETE FROM generated_qa WHERE note_id=%s", (note_id,))
    # ES 文档包含 title/tags/content；这些字段变化时都要同步索引。
    # date/authority 只从 PostgreSQL 读取，无需重建。
    needs_reindex = any(key in values for key in ("title", "content", "tags"))
    job_id = lifecycle.enqueue_reindex(note_id, user.id) if needs_reindex else None
    audit.log("note_update", request=request, user_id=user.id, target_type="note",
              target_id=note_id, detail={"fields": sorted(values)})
    return {"note_id": note_id, "job_id": job_id, "status": "pending" if job_id else "done"}


@router.patch("/{note_id}/source")
def update_source_policy(
    note_id: uuid.UUID, req: SourcePolicyPatch, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    if req.refresh_policy not in ("manual", "daily", "weekly"):
        raise HTTPException(status_code=422, detail="非法刷新策略")
    spaces.assert_note_role(user, note_id, "space_admin")
    with pool.connection() as conn:
        cur = conn.execute(
            """
            UPDATE source_documents SET refresh_policy=%s,status='active',
                next_refresh_at=CASE %s WHEN 'daily' THEN NOW()+INTERVAL '1 day'
                    WHEN 'weekly' THEN NOW()+INTERVAL '7 days' ELSE NULL END
            WHERE id=(SELECT source_document_id FROM notes WHERE id=%s)
            """,
            (req.refresh_policy, req.refresh_policy, note_id),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="来源不存在")
    audit.log("source_policy_update", request=request, user_id=user.id,
              target_type="note", target_id=note_id,
              detail={"refresh_policy": req.refresh_policy})
    return {"note_id": note_id, "refresh_policy": req.refresh_policy}


@router.get("/{note_id}/versions")
def list_versions(note_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> dict:
    spaces.assert_note_role(user, note_id, "viewer")
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT version_no, change_type, created_by, created_at
            FROM note_versions WHERE note_id=%s ORDER BY version_no DESC
            """,
            (note_id,),
        ).fetchall()
    return {"items": [
        {"version": r[0], "change_type": r[1], "created_by": r[2],
         "created_at": r[3].isoformat()} for r in rows
    ]}


@router.post("/{note_id}/versions/{version_no}/restore", status_code=202)
def restore_version(
    note_id: uuid.UUID, version_no: int, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_note_role(user, note_id, "editor")
    try:
        lifecycle.restore_version(note_id, version_no, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.log("note_version_restore", request=request, user_id=user.id,
              target_type="note", target_id=note_id, detail={"version": version_no})
    return {"note_id": note_id, "status": "pending"}


@router.post("/{note_id}/restore", status_code=202)
def restore_note(
    note_id: uuid.UUID, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_note_role(user, note_id, "editor")
    with pool.connection() as conn:
        if conn.execute(
            "SELECT 1 FROM notes WHERE id=%s AND deleted_at IS NOT NULL", (note_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="已删除笔记不存在")
        # 恢复前留一个 undelete 版本快照，与 delete/restore 路径一致，
        # 让版本历史完整记录「软删除 → 恢复」的来回。
        lifecycle.save_version(conn, note_id, "undelete", user.id)
        cur = conn.execute(
            "UPDATE notes SET deleted_at=NULL,deleted_by=NULL WHERE id=%s AND deleted_at IS NOT NULL",
            (note_id,),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="已删除笔记不存在")
    job_id = lifecycle.enqueue_reindex(note_id, user.id)
    audit.log("note_restore", request=request, user_id=user.id,
              target_type="note", target_id=note_id)
    return {"note_id": note_id, "job_id": job_id, "status": "pending"}


@router.post("/{note_id}/refresh", status_code=202)
def refresh_note(
    note_id: uuid.UUID, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    spaces.assert_note_role(user, note_id, "editor")
    job_id = uuid.uuid4()
    with pool.connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (id,job_type,note_id,payload,status,stage,title)
            SELECT %s,'source_refresh',id,jsonb_build_object('actor_id',%s::text),
                   'queued','queued',title
            FROM notes WHERE id=%s AND deleted_at IS NULL
            """,
            (job_id, user.id, note_id),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="笔记不存在")
    audit.log("note_refresh", request=request, user_id=user.id,
              target_type="note", target_id=note_id)
    return {"note_id": note_id, "job_id": job_id, "status": "pending"}


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: uuid.UUID, request: Request, user: CurrentUser = Depends(get_current_user)) -> None:
    """M3 软删除；需该空间 space_admin 权限。"""
    spaces.assert_note_role(user, note_id, "space_admin")
    with pool.connection() as conn:
        if conn.execute(
            "SELECT 1 FROM notes WHERE id=%s AND deleted_at IS NULL", (note_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="笔记不存在")
        lifecycle.save_version(conn, note_id, "delete", user.id)
        cur = conn.execute(
            "UPDATE notes SET deleted_at=NOW(),deleted_by=%s WHERE id=%s AND deleted_at IS NULL",
            (user.id, note_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="笔记不存在")
        conn.execute("DELETE FROM generated_qa WHERE note_id=%s", (note_id,))
    lifecycle.reindex(note_id)
    audit.log("note_delete", request=request, user_id=user.id, target_type="note", target_id=note_id)
