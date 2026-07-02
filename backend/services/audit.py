"""审计日志服务：关键安全/写操作落 audit_log 表 + 结构化日志双写。

设计：
- DB 表 audit_log 供查询/看板；结构化日志（fuxi.audit logger）供 journald 归档。
- 写审计失败绝不阻塞业务：内部 try/except，失败只 log.error，不抛。
- IP/User-Agent 从 Request 取（经反代取 X-Forwarded-For 首段）。
- user_id 可空（登录失败、匿名事件）。

用法：
    from services import audit
    audit.log("login_success", request=request, user_id=uid, detail={"ip": ip})
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from starlette.requests import Request

from db import pool
from services.logging import get_logger

_logger = get_logger("audit")


def _client_ip(req: Request | None) -> str | None:
    if req is None:
        return None
    xff = req.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    if req.client:
        return req.client.host
    return None


def log(
    action: str,
    *,
    request: Request | None = None,
    user_id: uuid.UUID | str | None = None,
    target_type: str | None = None,
    target_id: Any | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """记录一条审计事件（DB + 结构化日志双写）。失败不抛。"""
    uid = str(user_id) if user_id else None
    tid = str(target_id) if target_id is not None else None
    ip = _client_ip(request)
    ua = request.headers.get("user-agent") if request else None
    detail_json = json.dumps(detail or {}, ensure_ascii=False, default=str)

    # 结构化日志（始终输出，即使 DB 写失败也留痕）
    _logger.info(
        "audit: %s",
        action,
        extra={
            "event": "audit",
            "action": action,
            "user_id": uid,
            "target_type": target_type,
            "target_id": tid,
            "detail": detail or {},
            "ip": ip,
        },
    )

    # DB 落表（失败不抛，仅 log.error）
    try:
        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, action, target_type, target_id, detail, ip, user_agent) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)",
                (uid, action, target_type, tid, detail_json, ip, ua),
            )
    except Exception as exc:  # noqa: BLE001 — 审计不能阻塞业务
        _logger.error("audit_log write failed: action=%s err=%s", action, exc)
