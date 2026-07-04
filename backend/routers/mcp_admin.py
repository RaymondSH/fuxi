"""MCP API token 管理 HTTP 接口（admin）。

  GET    /mcp-admin/tokens       token 列表（不含明文哈希，仅 prefix 识别用）
  POST   /mcp-admin/tokens       生成 token：明文仅本次返回一次
  PATCH  /mcp-admin/tokens/{id}  改名 / 启停
  DELETE /mcp-admin/tokens/{id}  删除（admin）

与登录用 JWT 分开：MCP 客户端（Claude Desktop / 自建 Agent）拿 token 后用
Bearer <token> 调 /mcp。token 明文只在创建时返回一次，库里存 bcrypt 哈希。
"""
from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db import pool
from services import audit
from services.auth import CurrentUser, require_admin
from services.auth import hash_password, verify_password

router = APIRouter(prefix="/mcp-admin/tokens", tags=["mcp-admin"])

# token 明文：32 字节随机 → urlsafe，足够不可猜且便于粘贴
_TOKEN_BYTES = 32
_PREFIX_LEN = 8


class McpTokenOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    is_active: bool
    space_id: uuid.UUID | None = None
    space_name: str | None = None
    created_at: str
    last_used_at: str | None = None


class CreateTokenRequest(BaseModel):
    name: str = Field(min_length=1, description="token 名字，便于后台识别")
    space_id: uuid.UUID | None = Field(None, description="绑定的空间；留空=默认空间")


class CreateTokenResponse(BaseModel):
    token: str  # 明文，仅本次返回
    token_id: uuid.UUID
    name: str
    prefix: str
    space_id: uuid.UUID | None = None


class UpdateTokenRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    space_id: uuid.UUID | None = None


def _resolve_space(space_id: uuid.UUID | None) -> uuid.UUID | None:
    """校验 space_id 存在并返回；None → default 空间（避免遗留全库后门）。"""
    with pool.connection() as conn:
        if space_id is None:
            row = conn.execute("SELECT id FROM spaces WHERE is_default").fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM spaces WHERE id = %s", (space_id,)
            ).fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="指定的空间不存在")
    return row[0]


@router.get("", response_model=dict)
def list_tokens(_: CurrentUser = Depends(require_admin)) -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT t.id, t.name, t.prefix, t.is_active, t.space_id, s.name, "
            "t.created_at, t.last_used_at "
            "FROM mcp_tokens t LEFT JOIN spaces s ON s.id = t.space_id "
            "ORDER BY t.created_at DESC"
        ).fetchall()
    return {"items": [_to_out(r) for r in rows]}


@router.post("", response_model=CreateTokenResponse, status_code=201)
def create_token(
    req: CreateTokenRequest,
    request: Request,
    admin: CurrentUser = Depends(require_admin),
) -> CreateTokenResponse:
    """生成 token：明文仅本次返回，库里只存哈希与前缀。绑定到指定空间（默认 default）。"""
    plain = secrets.token_urlsafe(_TOKEN_BYTES)
    prefix = plain[:_PREFIX_LEN]
    token_id = uuid.uuid4()
    space_id = _resolve_space(req.space_id)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO mcp_tokens (id, name, token_hash, prefix, space_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (token_id, req.name.strip(), hash_password(plain), prefix, space_id),
        )
    audit.log("mcp_token_create", request=request, user_id=admin.id,
              target_type="mcp_token", target_id=token_id,
              detail={"name": req.name.strip(), "space_id": str(space_id)})
    return CreateTokenResponse(token=plain, token_id=token_id, name=req.name.strip(),
                              prefix=prefix, space_id=space_id)


@router.patch("/{token_id}", response_model=McpTokenOut)
def update_token(
    token_id: uuid.UUID,
    req: UpdateTokenRequest,
    request: Request,
    admin: CurrentUser = Depends(require_admin),
) -> McpTokenOut:
    sets, vals = [], []
    if req.name is not None:
        sets.append("name = %s"); vals.append(req.name.strip())
    if req.is_active is not None:
        sets.append("is_active = %s"); vals.append(req.is_active)
    if req.space_id is not None:
        sid = _resolve_space(req.space_id)
        sets.append("space_id = %s"); vals.append(sid)
    if not sets:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    vals.append(token_id)
    with pool.connection() as conn:
        row = conn.execute(
            f"UPDATE mcp_tokens SET {', '.join(sets)} WHERE id = %s "
            "RETURNING id, name, prefix, is_active, space_id",
            vals,
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="token 不存在")
    # 带 space_name 再查一次（UPDATE ... RETURNING 拿不到 JOIN 列）
    with pool.connection() as conn:
        full = conn.execute(
            "SELECT t.id, t.name, t.prefix, t.is_active, t.space_id, s.name, "
            "t.created_at, t.last_used_at "
            "FROM mcp_tokens t LEFT JOIN spaces s ON s.id = t.space_id WHERE t.id = %s",
            (token_id,),
        ).fetchone()
    audit.log("mcp_token_update", request=request, user_id=admin.id,
              target_type="mcp_token", target_id=token_id)
    return _to_out(full)


@router.delete("/{token_id}", status_code=204)
def delete_token(
    token_id: uuid.UUID,
    request: Request,
    admin: CurrentUser = Depends(require_admin),
) -> None:
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM mcp_tokens WHERE id = %s", (token_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="token 不存在")
    audit.log("mcp_token_delete", request=request, user_id=admin.id,
              target_type="mcp_token", target_id=token_id)


# ---------- 校验（供 mcp_server 中间件用，非 HTTP 接口） ----------

def verify_token(plain: str) -> tuple[uuid.UUID, uuid.UUID | None] | None:
    """校验一个 Bearer token 是否有效（active 且哈希匹配）。

    命中即更新 last_used_at。线性扫所有 active token 做 bcrypt.checkpw：
    token 数量小（管理员手动建），可接受；要扩展再加索引/缓存。

    返回 (token_id, space_id)：space_id 为该 token 绑定的空间；异常空值由 MCP 中间件拒绝。
    供 mcp_server 中间件把空间作用域注入到各工具。
    """
    if not plain:
        return None
    prefix = plain[:_PREFIX_LEN]
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, token_hash, space_id FROM mcp_tokens "
            "WHERE is_active = TRUE AND prefix = %s",
            (prefix,),
        ).fetchall()
        for tid, token_hash, space_id in rows:
            if verify_password(plain, token_hash):
                conn.execute(
                    "UPDATE mcp_tokens SET last_used_at = NOW() WHERE id = %s",
                    (tid,),
                )
                return tid, space_id
    return None


def _to_out(r) -> McpTokenOut:
    return McpTokenOut(
        id=r[0],
        name=r[1],
        prefix=r[2],
        is_active=r[3],
        space_id=r[4],
        space_name=r[5],
        created_at=r[6].isoformat(),
        last_used_at=r[7].isoformat() if r[7] else None,
    )
