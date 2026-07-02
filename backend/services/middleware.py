"""HTTP 中间件：全局未捕获异常兜底。

捕获非 HTTPException 的异常 → 结构化记录（含 path/method/user_id）→ 返回 500 通用文案，
不把堆栈/内部细节泄露给客户端。HTTPException 仍走 FastAPI 默认处理（含 401/429 等业务态）。
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from services.logging import get_logger

log = get_logger("errors")


def _client_ip(req: Request) -> str:
    # 经反向代理时取 X-Forwarded-For 首段；否则取直连 client
    xff = req.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    if req.client:
        return req.client.host
    return "-"


def _peek_user_id(req: Request) -> str | None:
    """尽量从已认证的 request.state 取 user_id；取不到不抛（本中间件用于兜底，不能因鉴权失败而自身报错）。"""
    user = getattr(req.state, "user", None)
    if user is not None:
        uid = getattr(user, "id", None)
        if uid is not None:
            return str(uid)
    return None


class CatchErrorsMiddleware(BaseHTTPMiddleware):
    """未捕获异常 → 500 通用文案，堆栈只进日志不进响应。"""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — 兜底，必须吞并记日志
            # 独立 worker 的异常不在 HTTP 链路内，由 job_runner 与具体 worker 记录。
            # 这里只兜同步请求处理链路里漏出来的异常。
            log.exception(
                "unhandled error",
                extra={
                    "event": "unhandled_error",
                    "path": request.url.path,
                    "method": request.method,
                    "user_id": _peek_user_id(request),
                    "ip": _client_ip(request),
                },
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "服务器内部错误"},
            )
