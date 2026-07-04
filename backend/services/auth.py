"""鉴权服务：密码哈希、JWT 签发/解码、FastAPI 依赖。

  - 密码用 bcrypt 直接哈希存库，不存明文（弃 passlib：已停更且与 bcrypt>=4.1 不兼容）。
  - 登录签发 HS256 JWT（payload: sub=user_id, role, exp）。
  - get_current_user / require_admin 作为路由依赖注入当前用户。

外部 SDK（bcrypt/jwt）只在本模块 new，其他地方 `from services import auth`。
最终架构见 docs/architecture.md。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import secrets
from fastapi import Depends, HTTPException, Request
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
    password_changed_at: datetime | None = None

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


def validate_password(pw: str) -> None:
    """密码强度策略：≥8 位 + 含字母 + 含数字。不满足抛 400。

    在建号 / 改密 / 自助改密复用。比单纯的 min_length=6 更强但仍宽松，
    避免过严（如强制特殊符号）困扰中文用户。后续可按需收紧。
    """
    if len(pw) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    if not any(c.isalpha() for c in pw):
        raise HTTPException(status_code=400, detail="密码需包含字母")
    if not any(c.isdigit() for c in pw):
        raise HTTPException(status_code=400, detail="密码需包含数字")


# ── JWT（双 token：access 短时 + refresh 长时，带 jti 可撤销）──

def _new_jti() -> str:
    """生成唯一 token id（用于 access 黑名单 / refresh 表关联）。"""
    return uuid.uuid4().hex + secrets.token_hex(8)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="服务未配置 JWT_SECRET")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": _new_jti(),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALG)


def create_refresh_token(user_id: uuid.UUID, *, ua: str | None = None, ip: str | None = None) -> str:
    """签发 refresh token 并落 refresh_tokens 表；返回 token 字符串。"""
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="服务未配置 JWT_SECRET")
    now = datetime.now(timezone.utc)
    jti = _new_jti()
    exp = now + timedelta(days=settings.jwt_refresh_expire_days)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALG)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (user_id, jti, expires_at, user_agent, ip) VALUES (%s, %s, %s, %s, %s)",
            (str(user_id), jti, exp, ua, ip),
        )
    return token


def _decode(token: str) -> dict:
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="服务未配置 JWT_SECRET")
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="无效的凭证")


def _is_revoked(jti: str) -> bool:
    """access jti 是否在黑名单（token_revocations）。"""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM token_revocations WHERE jti = %s",
            (jti,),
        ).fetchone()
    return row is not None


def verify_refresh(token: str) -> tuple[uuid.UUID, str]:
    """校验 refresh token：签名 + 未过期 + 表中未撤销 + 用户启用。
    返回 (user_id, jti)。失败抛 401。"""
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="无效的凭证")
    jti = payload.get("jti", "")
    user = _load_user(payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT revoked_at FROM refresh_tokens WHERE jti = %s",
            (jti,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="无效的凭证")
        if row[0] is not None:  # revoked_at
            raise HTTPException(status_code=401, detail="凭证已撤销，请重新登录")
    return user.id, jti


# ── 撤销 ──

def revoke_refresh(jti: str) -> None:
    """撤销单个 refresh token（登出用）。"""
    with pool.connection() as conn:
        conn.execute("UPDATE refresh_tokens SET revoked_at = NOW() WHERE jti = %s", (jti,))


def revoke_access(jti: str, exp: datetime, *, reason: str = "logout") -> None:
    """把 access jti 写黑名单（登出/改密用）。exp 是该 access 的过期时间，行届时失效。"""
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO token_revocations (jti, expires_at, reason) VALUES (%s, %s, %s) "
            "ON CONFLICT (jti) DO NOTHING",
            (jti, exp, reason),
        )


def revoke_all_user_tokens(user_id: uuid.UUID) -> None:
    """改密 / 停用账号：撤销其所有 refresh token（access 因无状态短期自然过期，15min 内失效）。"""
    with pool.connection() as conn:
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL",
            (str(user_id),),
        )


def revoke_access_token(token: str, *, reason: str = "logout") -> None:
    """解析 access token 并把其 jti 入黑名单（登出用）。token 无效则忽略。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        revoke_access(jti, datetime.fromtimestamp(exp, tz=timezone.utc), reason=reason)


def _load_user(user_id: str) -> CurrentUser | None:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, username, email, display_name, role, daily_token_limit, is_active, "
            "password_changed_at "
            "FROM users WHERE id = %s",
            (uid,),
        ).fetchone()
    if row is None:
        return None
    return CurrentUser(
        id=row[0], username=row[1], email=row[2], display_name=row[3],
        role=row[4], daily_token_limit=row[5], is_active=row[6],
        password_changed_at=row[7],
    )


# ── FastAPI 依赖 ──

def get_current_user(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """解析 Bearer / httpOnly Cookie access token → 校验类型/撤销/用户状态。

    解析出的 user 同步写 request.state.user，供异常中间件 / 日志取 user_id。
    access token 的 jti 若在 token_revocations 黑名单则拒（登出/改密后立即失效）。
    """
    token = cred.credentials if cred and cred.credentials else request.cookies.get("fuxi_access", "")
    if not token:
        raise HTTPException(status_code=401, detail="需要登录")
    payload = _decode(token)
    # refresh token 只用于 /auth/refresh，绝不能作为业务 access token 使用。
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效的访问凭证")
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="无效的访问凭证")
    if _is_revoked(jti):
        raise HTTPException(status_code=401, detail="凭证已撤销，请重新登录")
    user = _load_user(payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    issued_at = payload.get("iat")
    if user.password_changed_at is not None and issued_at is not None:
        issued = datetime.fromtimestamp(float(issued_at), tz=timezone.utc)
        changed = user.password_changed_at
        if changed.tzinfo is None:
            changed = changed.replace(tzinfo=timezone.utc)
        if issued < changed:
            raise HTTPException(status_code=401, detail="密码已修改，请重新登录")
    request.state.user = user
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """仅管理员可访问。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
