"""鉴权服务：密码哈希、JWT 签发/解码、FastAPI 依赖。

  - 密码用 bcrypt（passlib）哈希存库，不存明文。
  - 登录签发 HS256 JWT（payload: sub=user_id, role, exp）。
  - get_current_user / require_admin 作为路由依赖注入当前用户。

外部 SDK（passlib/jwt）只在本模块 new，其他地方 `from services import auth`。
设计见 docs/auth-design.md。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings
from db import pool

_JWT_ALG = "HS256"
# bcrypt 只用密码前 72 字节；显式截断以兼容 bcrypt>=4.1（超长会抛 ValueError）
_BCRYPT_MAX = 72
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    username: str | None
    email: str
    display_name: str | None
    role: str
    daily_token_limit: int | None
    is_active: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def token_limit(self) -> int | None:
        """有效每日额度：用户自定义优先，否则用配置默认；admin 不限（None）。"""
        if self.is_admin:
            return None
        return self.daily_token_limit if self.daily_token_limit is not None else settings.default_daily_token_limit


# ── 密码 ──

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8")[:_BCRYPT_MAX], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:_BCRYPT_MAX], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ──

def create_access_token(user_id: uuid.UUID, role: str) -> str:
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="服务未配置 JWT_SECRET")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALG)


def _decode(token: str) -> dict:
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="服务未配置 JWT_SECRET")
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="无效的凭证")


def _load_user(user_id: str) -> CurrentUser | None:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, username, email, display_name, role, daily_token_limit, is_active "
            "FROM users WHERE id = %s",
            (uid,),
        ).fetchone()
    if row is None:
        return None
    return CurrentUser(
        id=row[0], username=row[1], email=row[2], display_name=row[3],
        role=row[4], daily_token_limit=row[5], is_active=row[6],
    )


# ── FastAPI 依赖 ──

def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """解析 Bearer JWT → 查库 → 校验启用状态，返回当前用户。"""
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=401, detail="需要登录")
    payload = _decode(cred.credentials)
    user = _load_user(payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """仅管理员可访问。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
