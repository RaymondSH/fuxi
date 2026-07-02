"""空间（Spaces）管理 HTTP 接口。

  GET    /spaces                 列出当前用户可见空间（成员空间；sysadmin 看全部）
  POST   /spaces                 创建空间（任意登录用户；创建者成为 space_admin）
  GET    /spaces/{id}            空间详情（须可见）
  PATCH  /spaces/{id}            改 name/description（space_admin）
  DELETE /spaces/{id}            删除空间（space_admin；default 空间受保护不可删）
  GET    /spaces/{id}/members    成员列表（viewer+ 可见）
  POST   /spaces/{id}/members    加成员（space_admin；指定 user_id + role）
  PATCH  /spaces/{id}/members/{user_id}  改成员角色（space_admin）
  DELETE /spaces/{id}/members/{user_id}  移除成员（space_admin）

双层角色：系统级 users.role（member/admin=sysadmin）+ 空间级 space_members.role
（viewer/editor/space_admin）。sysadmin 对全部空间天然 space_admin，不写 membership 行。
角色判定见 services/spaces.py。所有写操作落 audit_log。
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db import pool
from services import audit, spaces
from services.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/spaces", tags=["spaces"])

_VALID_ROLES = ("viewer", "editor", "space_admin")
# slug：小写字母/数字/连字符，2-40 位。中文标题另走 name 字段。
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


# ── 响应模型 ──

class SpaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    is_default: bool
    owner_id: uuid.UUID | None = None
    created_at: str
    my_role: str | None = None     # 当前用户在此空间的角色；sysadmin 视角恒为 space_admin
    member_count: int = 0


class SpaceListResponse(BaseModel):
    items: list[SpaceOut]


class CreateSpaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    slug: str | None = Field(None, description="留空则按 name 生成；自定义须 a-z0-9-")
    description: str | None = None


class UpdateSpaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    role: str
    created_at: str


class MemberListResponse(BaseModel):
    items: list[MemberOut]


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: str = "viewer"  # viewer | editor | space_admin


class UpdateMemberRequest(BaseModel):
    role: str  # viewer | editor | space_admin


# ── 工具 ──

def _slugify(name: str) -> str:
    """中英文标题 → slug：转小写，非 [a-z0-9] 转连字符，去首尾连字符，截断。"""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:40] or "space"


def _row_to_space(r) -> SpaceOut:
    return SpaceOut(
        id=r[0], name=r[1], slug=r[2], description=r[3], is_default=r[4],
        owner_id=r[5], created_at=r[6].isoformat(), my_role=r[7], member_count=r[8] or 0,
    )


def _require_space_visible(conn, user: CurrentUser, space_id: uuid.UUID) -> None:
    """空间必须存在且对当前用户可见，否则 404（不泄露存在性）。

    sysadmin 看全部；普通用户须是该空间成员。
    """
    visible = spaces.visible_space_ids(conn, user)
    if visible is None:
        return  # sysadmin 全可见
    if space_id not in visible:
        raise HTTPException(status_code=404, detail="空间不存在或你无权访问")


# ── 空间 CRUD ──

@router.get("", response_model=SpaceListResponse)
def list_spaces(user: CurrentUser = Depends(get_current_user)) -> SpaceListResponse:
    """列出当前用户可见的空间。

    普通用户只看自己是成员的空间；sysadmin 看全部。每行带 my_role 与 member_count。
    sysadmin 的 my_role 标记为 space_admin（对全部空间的天然角色）。
    """
    with pool.connection() as conn:
        if user.is_admin:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.slug, s.description, s.is_default, s.owner_id,
                       s.created_at, 'space_admin'::text AS my_role,
                       (SELECT COUNT(*) FROM space_members WHERE space_id = s.id)
                FROM spaces s
                ORDER BY s.is_default DESC, s.created_at ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.slug, s.description, s.is_default, s.owner_id,
                       s.created_at, sm.role AS my_role,
                       (SELECT COUNT(*) FROM space_members WHERE space_id = s.id)
                FROM spaces s
                JOIN space_members sm ON sm.space_id = s.id AND sm.user_id = %s
                ORDER BY s.is_default DESC, s.created_at ASC
                """,
                (user.id,),
            ).fetchall()
    return SpaceListResponse(items=[_row_to_space(r) for r in rows])


@router.post("", response_model=SpaceOut, status_code=201)
def create_space(
    req: CreateSpaceRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> SpaceOut:
    """创建空间。创建者自动成为该空间的 space_admin。

    任意登录用户均可创建（自助开空间），无需系统 admin。slug 留空则据 name 生成，
    自定义须匹配 a-z0-9- 且全库唯一。
    """
    slug = (req.slug or _slugify(req.name)).strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="slug 须为 2-40 位小写字母/数字/连字符，且以字母或数字开头",
        )
    try:
        with pool.connection() as conn:
            # 唯一约束冲突会抛 psycopg IntegrityError
            cur = conn.execute(
                """
                INSERT INTO spaces (slug, name, description, owner_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, name, slug, description, is_default, owner_id, created_at
                """,
                (slug, req.name.strip(), req.description, user.id),
            )
            row = cur.fetchone()
            assert row is not None
            space_id = row[0]
            # 创建者即 space_admin
            conn.execute(
                "INSERT INTO space_members (space_id, user_id, role) VALUES (%s, %s, 'space_admin')",
                (space_id, user.id),
            )
            member_count = 1
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — 唯一约束等 DB 错误转友好提示
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="slug 已存在，请换一个")
        raise HTTPException(status_code=500, detail="创建失败")

    audit.log("space_create", request=request, user_id=user.id,
              target_type="space", target_id=space_id,
              detail={"name": req.name.strip(), "slug": slug})
    return SpaceOut(
        id=space_id, name=row[1], slug=row[2], description=row[3], is_default=row[4],
        owner_id=row[5], created_at=row[6].isoformat(),
        my_role="space_admin", member_count=member_count,
    )


@router.get("/{space_id}", response_model=SpaceOut)
def get_space(space_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> SpaceOut:
    with pool.connection() as conn:
        _require_space_visible(conn, user, space_id)
        row = conn.execute(
            """
            SELECT s.id, s.name, s.slug, s.description, s.is_default, s.owner_id,
                   s.created_at, COALESCE(sm.role, 'space_admin') AS my_role,
                   (SELECT COUNT(*) FROM space_members WHERE space_id = s.id)
            FROM spaces s
            LEFT JOIN space_members sm ON sm.space_id = s.id AND sm.user_id = %s
            WHERE s.id = %s
            """,
            (user.id, space_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="空间不存在或你无权访问")
    return _row_to_space(row)


@router.patch("/{space_id}", response_model=SpaceOut)
def update_space(
    space_id: uuid.UUID,
    req: UpdateSpaceRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> SpaceOut:
    """改空间 name/description。需 space_admin 权限（sysadmin 恒通过）。"""
    spaces.assert_space_role(user, space_id, "space_admin")
    sets, vals = [], []
    if req.name is not None:
        sets.append("name = %s"); vals.append(req.name.strip())
    if req.description is not None:
        sets.append("description = %s"); vals.append(req.description)
    if not sets:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    vals.append(space_id)
    with pool.connection() as conn:
        row = conn.execute(
            f"""
            UPDATE spaces SET {', '.join(sets)} WHERE id = %s
            RETURNING id, name, slug, description, is_default, owner_id, created_at
            """,
            vals,
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="空间不存在")
        member_count = conn.execute(
            "SELECT COUNT(*) FROM space_members WHERE space_id = %s", (space_id,)
        ).fetchone()[0]
    audit.log("space_update", request=request, user_id=user.id,
              target_type="space", target_id=space_id, detail={"fields": sets})
    return SpaceOut(
        id=row[0], name=row[1], slug=row[2], description=row[3], is_default=row[4],
        owner_id=row[5], created_at=row[6].isoformat(),
        my_role="space_admin", member_count=member_count,
    )


@router.delete("/{space_id}", status_code=204)
def delete_space(
    space_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """删除空间。需 space_admin 权限。default 空间受保护不可删。

    有笔记或 Wiki 时返回 409，避免产生无归属内容；删除成功会级联撤销 MCP token。
    """
    spaces.assert_space_role(user, space_id, "space_admin")
    with pool.connection() as conn:
        is_default = conn.execute(
            "SELECT is_default FROM spaces WHERE id = %s", (space_id,)
        ).fetchone()
        if is_default is None:
            raise HTTPException(status_code=404, detail="空间不存在")
        if is_default[0]:
            raise HTTPException(status_code=400, detail="默认空间不可删除")
        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM notes WHERE space_id = %s),
              (SELECT COUNT(*) FROM wiki_pages WHERE space_id = %s)
            """,
            (space_id, space_id),
        ).fetchone()
        if counts[0] or counts[1]:
            raise HTTPException(
                status_code=409,
                detail=f"空间仍有 {counts[0]} 篇笔记和 {counts[1]} 个主题页，请先迁移或清理内容",
            )
        cur = conn.execute("DELETE FROM spaces WHERE id = %s", (space_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="空间不存在")
    audit.log("space_delete", request=request, user_id=user.id,
              target_type="space", target_id=space_id)


# ── 成员管理 ──

@router.get("/{space_id}/members", response_model=MemberListResponse)
def list_members(space_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> MemberListResponse:
    """成员列表。需该空间 viewer+ 权限（能看空间内容就能看成员）。"""
    spaces.assert_space_role(user, space_id, "viewer")
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT sm.user_id, u.email, u.display_name, sm.role, sm.created_at
            FROM space_members sm
            JOIN users u ON u.id = sm.user_id
            WHERE sm.space_id = %s
            ORDER BY
                CASE sm.role WHEN 'space_admin' THEN 0 WHEN 'editor' THEN 1 ELSE 2 END,
                u.email
            """,
            (space_id,),
        ).fetchall()
    return MemberListResponse(items=[
        MemberOut(user_id=r[0], email=r[1], display_name=r[2], role=r[3], created_at=r[4].isoformat())
        for r in rows
    ])


class UserLookup(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    is_member: bool  # 是否已是该空间成员


@router.get("/{space_id}/members/search", response_model=dict)
def search_users(
    space_id: uuid.UUID,
    q: str = "",
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """按 email/display_name 模糊查用户，供加成员时选人。需该空间 space_admin 权限。

    标注 is_member（已是成员的不再重复加）。只返回 active 用户，最多 10 条。
    """
    spaces.assert_space_role(user, space_id, "space_admin")
    term = q.strip()
    if len(term) < 2:
        return {"items": []}
    like = f"%{term}%"
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.email, u.display_name,
                   EXISTS(SELECT 1 FROM space_members WHERE space_id = %s AND user_id = u.id) AS is_member
            FROM users u
            WHERE u.is_active = TRUE
              AND (u.email ILIKE %s OR COALESCE(u.display_name, '') ILIKE %s)
            ORDER BY u.email
            LIMIT 10
            """,
            (space_id, like, like),
        ).fetchall()
    return {"items": [
        UserLookup(user_id=r[0], email=r[1], display_name=r[2], is_member=r[3])
        for r in rows
    ]}


@router.post("/{space_id}/members", response_model=MemberOut, status_code=201)
def add_member(
    space_id: uuid.UUID,
    req: AddMemberRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> MemberOut:
    """加成员。需 space_admin 权限。指定 user_id + role。

    user 须存在且 active。已存在则 409。sysadmin 加入某空间会显式写一行（罕见，通常 sysadmin
    不需要 membership，但若管理员想以普通成员身份出现在成员列表里可显式加）。
    """
    spaces.assert_space_role(user, space_id, "space_admin")
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role 须为 {', '.join(_VALID_ROLES)}")
    with pool.connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE id = %s AND is_active = TRUE", (req.user_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="用户不存在或已停用")
        dup = conn.execute(
            "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s",
            (space_id, req.user_id),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail="该用户已是空间成员")
        conn.execute(
            "INSERT INTO space_members (space_id, user_id, role) VALUES (%s, %s, %s)",
            (space_id, req.user_id, req.role),
        )
        row = conn.execute(
            """
            SELECT sm.user_id, u.email, u.display_name, sm.role, sm.created_at
            FROM space_members sm JOIN users u ON u.id = sm.user_id
            WHERE sm.space_id = %s AND sm.user_id = %s
            """,
            (space_id, req.user_id),
        ).fetchone()
    audit.log("space_member_add", request=request, user_id=user.id,
              target_type="space_member", target_id=f"{space_id}:{req.user_id}",
              detail={"role": req.role})
    return MemberOut(user_id=row[0], email=row[1], display_name=row[2],
                     role=row[3], created_at=row[4].isoformat())


@router.patch("/{space_id}/members/{user_id}", response_model=MemberOut)
def update_member(
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    req: UpdateMemberRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> MemberOut:
    """改成员角色。需 space_admin 权限。不能改自己（避免把自己降级后失管）。"""
    spaces.assert_space_role(user, space_id, "space_admin")
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role 须为 {', '.join(_VALID_ROLES)}")
    if user_id == user.id and not user.is_admin:
        raise HTTPException(status_code=400, detail="不能修改自己的空间角色")
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE space_members SET role = %s WHERE space_id = %s AND user_id = %s "
            "RETURNING user_id",
            (req.role, space_id, user_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="该用户不是空间成员")
        full = conn.execute(
            """
            SELECT sm.user_id, u.email, u.display_name, sm.role, sm.created_at
            FROM space_members sm JOIN users u ON u.id = sm.user_id
            WHERE sm.space_id = %s AND sm.user_id = %s
            """,
            (space_id, user_id),
        ).fetchone()
    audit.log("space_member_update", request=request, user_id=user.id,
              target_type="space_member", target_id=f"{space_id}:{user_id}",
              detail={"role": req.role})
    return MemberOut(user_id=full[0], email=full[1], display_name=full[2],
                     role=full[3], created_at=full[4].isoformat())


@router.delete("/{space_id}/members/{user_id}", status_code=204)
def remove_member(
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """移除成员。需 space_admin 权限。不能移除自己（避免误操作把自己踢出后失管）。"""
    spaces.assert_space_role(user, space_id, "space_admin")
    if user_id == user.id and not user.is_admin:
        raise HTTPException(status_code=400, detail="不能移除自己")
    with pool.connection() as conn:
        cur = conn.execute(
            "DELETE FROM space_members WHERE space_id = %s AND user_id = %s",
            (space_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="该用户不是空间成员")
    audit.log("space_member_remove", request=request, user_id=user.id,
              target_type="space_member", target_id=f"{space_id}:{user_id}")
