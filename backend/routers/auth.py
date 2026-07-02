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
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, EmailStr, Field

from config import settings
from db import pool
from services import audit, auth, quota
from services.auth import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


# ── 模型 ──

class LoginRequest(BaseModel):
    identifier: str  # 用户名或邮箱
    password: str
    client: Literal["web", "mobile"] = "web"


class UserOut(BaseModel):
    id: uuid.UUID
    username: str | None = None
    email: str
    display_name: str | None = None
    role: str
    daily_token_limit: int | None = None
    is_active: bool = True


class LoginResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str | None = None
    client: Literal["web", "mobile"] = "web"


class RefreshResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2)
    email: EmailStr
    password: str  # 强度由 auth.validate_password 校验（≥8 位 + 字母 + 数字）
    display_name: str | None = None
    role: str = "member"
    daily_token_limit: int | None = None


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=2)
    display_name: str | None = None
    role: str | None = None
    daily_token_limit: int | None = None
    is_active: bool | None = None
    password: str | None = None  # 强度由 auth.validate_password 校验


# 统一的用户列选取顺序，_to_out 按此索引
_USER_COLS = "id, username, email, display_name, role, daily_token_limit, is_active"


def _to_out(row) -> UserOut:
    return UserOut(
        id=row[0], username=row[1], email=row[2], display_name=row[3],
        role=row[4], daily_token_limit=row[5], is_active=row[6],
    )


def _lock_active(locked_until: datetime | None, *, now: datetime | None = None) -> bool:
    """锁定时间尚未到期才算锁定；便于单测覆盖自动解锁边界。"""
    if locked_until is None:
        return False
    current = now or datetime.now(timezone.utc)
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > current


def _set_auth_cookies(response: Response, access: str, refresh: str | None = None) -> None:
    """Web token 只进 httpOnly Cookie；当前部署为 HTTP，故 secure=False。"""
    response.set_cookie(
        "fuxi_access",
        access,
        max_age=settings.jwt_access_expire_minutes * 60,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    if refresh is not None:
        response.set_cookie(
            "fuxi_refresh",
            refresh,
            max_age=settings.jwt_refresh_expire_days * 86400,
            httponly=True,
            secure=False,
            samesite="lax",
            path="/",
        )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("fuxi_access", path="/")
    response.delete_cookie("fuxi_refresh", path="/")


# ── 接口 ──

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, response: Response) -> LoginResponse:
    ident = req.identifier.strip()
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {_USER_COLS}, password_hash, failed_login_attempts, locked_until "
            "FROM users WHERE username = %s OR email = %s LIMIT 1",
            (ident, ident),
        ).fetchone()
        # 只在 locked_until 尚未到期时拒绝；过期后清零，避免永久锁号。
        locked_active = bool(row is not None and _lock_active(row[9]))
        if locked_active:
            raise HTTPException(status_code=423, detail="账号已锁定，请稍后再试")
        attempts_base = row[8] if row is not None else 0
        if row is not None and row[9] is not None:
            conn.execute(
                "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = %s",
                (row[0],),
            )
            attempts_base = 0
        # 统一错误文案，避免泄露「账号是否存在」
        if row is None or not auth.verify_password(req.password, row[7]):
            # 失败递增；达阈值则锁定
            if row is not None:
                attempts = attempts_base + 1
                if attempts >= settings.login_max_attempts:
                    conn.execute(
                        "UPDATE users SET failed_login_attempts = %s, locked_until = NOW() + (%s || ' minutes')::interval "
                        "WHERE id = %s",
                        (attempts, settings.login_lock_minutes, row[0]),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET failed_login_attempts = %s WHERE id = %s",
                        (attempts, row[0]),
                    )
            audit.log("login_failed", request=request, user_id=row[0] if row else None, detail={"identifier": ident})
            raise HTTPException(status_code=401, detail="账号或密码错误")
        if not row[6]:  # is_active
            audit.log("login_failed", request=request, user_id=row[0], detail={"reason": "inactive"})
            raise HTTPException(status_code=403, detail="账号已停用")
        # 成功：清零失败计数 + 锁定 + 记最近登录时间
        conn.execute(
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login_at = NOW() WHERE id = %s",
            (row[0],),
        )
    access = auth.create_access_token(row[0], row[4])  # id, role
    refresh = auth.create_refresh_token(
        row[0],
        ua=request.headers.get("user-agent"),
        ip=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or None,
    )
    audit.log("login_success", request=request, user_id=row[0])
    if req.client == "web":
        _set_auth_cookies(response, access, refresh)
        return LoginResponse(user=_to_out(row))
    return LoginResponse(access_token=access, refresh_token=refresh, user=_to_out(row))


@router.post("/refresh", response_model=RefreshResponse)
def refresh(req: RefreshRequest, request: Request, response: Response) -> RefreshResponse:
    """用 refresh token 换新的 access token（refresh 不轮换，简单稳定）。"""
    refresh_token = req.refresh_token or request.cookies.get("fuxi_refresh", "")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="缺少 refresh token")
    uid, _jti = auth.verify_refresh(refresh_token)
    # role 从库读（不信任旧 token 里的 role，避免改角色后旧 token 仍带旧 role）
    with pool.connection() as conn:
        row = conn.execute("SELECT role FROM users WHERE id = %s", (uid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="账号不存在")
    access = auth.create_access_token(uid, row[0])
    # 只有显式提交 refresh token 的非浏览器客户端才拿到 token 响应；
    # 仅凭 Cookie 的请求始终只刷新 httpOnly Cookie，防止 JS 借 client 参数导出 access。
    if req.refresh_token is None:
        _set_auth_cookies(response, access)
        return RefreshResponse()
    return RefreshResponse(access_token=access)


@router.post("/logout", status_code=204)
def logout(
    req: LogoutRequest,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(auth.get_current_user),
) -> None:
    """撤销 refresh token + 把当前 access jti 写黑名单 → 真正登出。"""
    try:
        refresh_token = req.refresh_token or request.cookies.get("fuxi_refresh", "")
        uid, jti = auth.verify_refresh(refresh_token)
        if uid == user.id:
            auth.revoke_refresh(jti)
    except HTTPException:
        # refresh 无效也继续登出当前 access（客户端可能已过期）
        pass
    access_token = (
        request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        or request.cookies.get("fuxi_access", "")
    )
    if access_token:
        auth.revoke_access_token(access_token, reason="logout")
    _clear_auth_cookies(response)
    audit.log("logout", request=request, user_id=user.id)
    return None


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(auth.get_current_user)) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, email=user.email, display_name=user.display_name,
        role=user.role, daily_token_limit=user.daily_token_limit, is_active=user.is_active,
    )


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str  # 强度由 auth.validate_password 校验


@router.post("/change-password", status_code=204)
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(auth.get_current_user),
) -> None:
    """自助改密：验旧密码 → 校验新密码强度 → 更新 + password_changed_at → 撤销旧 token 强制重登。"""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = %s",
            (user.id,),
        ).fetchone()
        if row is None or not auth.verify_password(req.old_password, row[0]):
            audit.log("change_password_failed", request=request, user_id=user.id, detail={"reason": "wrong_old"})
            raise HTTPException(status_code=401, detail="旧密码错误")
        if req.new_password == req.old_password:
            raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
        auth.validate_password(req.new_password)
        conn.execute(
            "UPDATE users SET password_hash = %s, password_changed_at = NOW() WHERE id = %s",
            (auth.hash_password(req.new_password), user.id),
        )
    # 撤销该用户所有 refresh（强制重登）；当前 access 也入黑名单立即失效
    auth.revoke_all_user_tokens(user.id)
    access_token = (
        request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        or request.cookies.get("fuxi_access", "")
    )
    if access_token:
        auth.revoke_access_token(access_token, reason="password_change")
    _clear_auth_cookies(response)
    audit.log("change_password", request=request, user_id=user.id)
    return None


@router.get("/users", response_model=dict)
def list_users(_: CurrentUser = Depends(auth.require_admin)) -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_USER_COLS} FROM users ORDER BY created_at"
        ).fetchall()
    return {"items": [_to_out(r) for r in rows]}


@router.get("/usage", response_model=dict)
def usage_overview(
    days: int = Query(7, ge=1, le=90, description="趋势天数"),
    _: CurrentUser = Depends(auth.require_admin),
) -> dict:
    """各用户今日 token 用量 + 有效额度，驱动管理员用量看板。

    升级：附最近 N 天组织趋势（org_trend）、组织今日合计（org_today）、
    以及今日用量已达额度 80% 的告警名单（alerts）。
    """
    today = quota.today()
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
            (today,),
        ).fetchall()
        # 组织最近 N 天的逐日合计（含今天，缺日补 0），驱动趋势折线
        trend_rows = conn.execute(
            """
            SELECT usage_day, SUM(total_tokens)::int AS total
            FROM token_usage
            WHERE usage_day >= (%s::date - (%s - 1))
            GROUP BY usage_day
            ORDER BY usage_day
            """,
            (today, days),
        ).fetchall()

    items = []
    org_today = 0
    alerts: list[dict] = []
    for r in rows:
        uid, email, display_name, role, limit_cfg, used = r
        # 有效额度：admin 不限（null）；member 用自定义额度，未设则用配置默认
        limit = None if role == "admin" else (limit_cfg if limit_cfg is not None else settings.default_daily_token_limit)
        items.append({
            "id": str(uid), "email": email, "display_name": display_name, "role": role,
            "limit": limit, "used_today": used,
        })
        org_today += used
        # 80% 告警：有限额且今日已用 ≥ 80%
        if limit is not None and used >= int(limit * 0.8):
            alerts.append({
                "id": str(uid), "email": email, "display_name": display_name,
                "used_today": used, "limit": limit,
                "pct": round(used / limit * 100) if limit else 0,
            })

    # 趋势：补齐缺日（无消耗的天补 0），保证前端折线连续
    trend_map = {r[0]: r[1] for r in trend_rows}
    org_trend: list[dict] = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        org_trend.append({"day": d.isoformat(), "total": trend_map.get(d, 0)})

    return {
        "items": items,
        "tz": settings.usage_tz,
        "org_today": org_today,
        "org_trend": org_trend,
        "alerts": alerts,
    }


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    req: CreateUserRequest,
    request: Request,
    admin: CurrentUser = Depends(auth.require_admin),
) -> UserOut:
    if req.role not in ("member", "admin"):
        raise HTTPException(status_code=400, detail="role 只能是 member 或 admin")
    auth.validate_password(req.password)
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
    audit.log(
        "user_create", request=request, user_id=admin.id,
        target_type="user", target_id=row[0],
        detail={"role": req.role, "email": req.email},
    )
    return _to_out(row)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    req: UpdateUserRequest,
    request: Request,
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
        auth.validate_password(req.password)
        sets.append("password_hash = %s"); params.append(auth.hash_password(req.password))
        sets.append("password_changed_at = NOW()")
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
    # 审计：记录改动字段（不含密码明文），停用/改密单独标 action 便于筛选
    changed = [s.split(" =")[0] for s in sets]
    action = "user_update"
    if req.is_active is False:
        action = "user_deactivate"
    elif req.password is not None:
        action = "user_reset_password"
    audit.log(
        action, request=request, user_id=admin.id,
        target_type="user", target_id=user_id,
        detail={"fields": changed},
    )
    # 停用 / 改密 → 撤销该用户所有 refresh token，强制其重登（access 15min 内自然过期）
    if req.is_active is False or req.password is not None:
        auth.revoke_all_user_tokens(user_id)
    return _to_out(row)
