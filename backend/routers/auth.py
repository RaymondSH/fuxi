"""鉴权 HTTP 接口。

  POST /auth/login           邮箱+密码登录，返回 JWT
  GET  /auth/me              当前用户信息
  GET  /auth/users           用户列表（admin）
  POST /auth/users           建号（admin，不开放自助注册）
  PATCH /auth/users/{id}     改角色/额度/启用/重置密码（admin）

接口只做解析请求 → 调 services.auth → 组装响应；密码/JWT 逻辑在 services/auth.py。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, EmailStr, Field

from config import settings
from db import pool
from services import auth, quota
from services.auth import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


# ── 模型 ──

class LoginRequest(BaseModel):
    identifier: str  # 用户名或邮箱
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str | None = None
    email: str
    display_name: str | None = None
    role: str
    daily_token_limit: int | None = None
    is_active: bool = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str | None = None
    role: str = "member"
    daily_token_limit: int | None = None


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=2)
    display_name: str | None = None
    role: str | None = None
    daily_token_limit: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6)


# 统一的用户列选取顺序，_to_out 按此索引
_USER_COLS = "id, username, email, display_name, role, daily_token_limit, is_active"


def _to_out(row) -> UserOut:
    return UserOut(
        id=row[0], username=row[1], email=row[2], display_name=row[3],
        role=row[4], daily_token_limit=row[5], is_active=row[6],
    )


# ── 接口 ──

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    ident = req.identifier.strip()
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {_USER_COLS}, password_hash "
            "FROM users WHERE username = %s OR email = %s LIMIT 1",
            (ident, ident),
        ).fetchone()
    # 统一错误文案，避免泄露「账号是否存在」
    if row is None or not auth.verify_password(req.password, row[7]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not row[6]:  # is_active
        raise HTTPException(status_code=403, detail="账号已停用")
    token = auth.create_access_token(row[0], row[4])  # id, role
    return LoginResponse(access_token=token, user=_to_out(row))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(auth.get_current_user)) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, email=user.email, display_name=user.display_name,
        role=user.role, daily_token_limit=user.daily_token_limit, is_active=user.is_active,
    )


@router.get("/users", response_model=dict)
def list_users(_: CurrentUser = Depends(auth.require_admin)) -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_USER_COLS} FROM users ORDER BY created_at"
        ).fetchall()
    return {"items": [_to_out(r) for r in rows]}


@router.get("/usage", response_model=dict)
def usage_overview(_: CurrentUser = Depends(auth.require_admin)) -> dict:
    """各用户今日 token 用量 + 有效额度，驱动管理员用量看板。"""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.email, u.display_name, u.role, u.daily_token_limit,
                   COALESCE(t.used, 0)::int AS used_today
            FROM users u
            LEFT JOIN (
                SELECT user_id, SUM(total_tokens) AS used
                FROM token_usage WHERE usage_day = %s GROUP BY user_id
            ) t ON t.user_id = u.id
            ORDER BY used_today DESC, u.created_at
            """,
            (quota.today(),),
        ).fetchall()
    items = []
    for r in rows:
        role = r[3]
        # 有效额度：admin 不限（null）；member 用自定义额度，未设则用配置默认
        limit = None if role == "admin" else (r[4] if r[4] is not None else settings.default_daily_token_limit)
        items.append({
            "id": str(r[0]), "email": r[1], "display_name": r[2], "role": role,
            "limit": limit, "used_today": r[5],
        })
    return {"items": items, "tz": settings.usage_tz}


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(req: CreateUserRequest, _: CurrentUser = Depends(auth.require_admin)) -> UserOut:
    if req.role not in ("member", "admin"):
        raise HTTPException(status_code=400, detail="role 只能是 member 或 admin")
    with pool.connection() as conn:
        dup = conn.execute(
            "SELECT email = %s AS email_dup, username = %s AS name_dup FROM users "
            "WHERE email = %s OR username = %s",
            (req.email, req.username, req.email, req.username),
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail="邮箱已存在" if dup[0] else "用户名已存在",
            )
        row = conn.execute(
            f"""
            INSERT INTO users (username, email, password_hash, display_name, role, daily_token_limit)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING {_USER_COLS}
            """,
            (req.username, req.email, auth.hash_password(req.password), req.display_name,
             req.role, req.daily_token_limit),
        ).fetchone()
    return _to_out(row)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    req: UpdateUserRequest,
    admin: CurrentUser = Depends(auth.require_admin),
) -> UserOut:
    sets, params = [], []
    if req.username is not None:
        sets.append("username = %s"); params.append(req.username)
    if req.display_name is not None:
        sets.append("display_name = %s"); params.append(req.display_name)
    if req.role is not None:
        if req.role not in ("member", "admin"):
            raise HTTPException(status_code=400, detail="role 只能是 member 或 admin")
        sets.append("role = %s"); params.append(req.role)
    if req.daily_token_limit is not None:
        sets.append("daily_token_limit = %s"); params.append(req.daily_token_limit)
    if req.is_active is not None:
        # 防自锁：管理员不能停用自己
        if req.is_active is False and user_id == admin.id:
            raise HTTPException(status_code=400, detail="不能停用自己")
        sets.append("is_active = %s"); params.append(req.is_active)
    if req.password is not None:
        sets.append("password_hash = %s"); params.append(auth.hash_password(req.password))
    if not sets:
        raise HTTPException(status_code=400, detail="没有可更新的字段")

    params.append(user_id)
    with pool.connection() as conn:
        try:
            row = conn.execute(
                f"UPDATE users SET {', '.join(sets)} WHERE id = %s "
                f"RETURNING {_USER_COLS}",
                params,
            ).fetchone()
        except UniqueViolation:
            raise HTTPException(status_code=409, detail="用户名或邮箱已被占用")
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _to_out(row)
