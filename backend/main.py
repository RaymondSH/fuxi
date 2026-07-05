"""FastAPI 入口。

  uvicorn main:app --reload --port 8000

挂载全部业务路由（auth / ingest / search / notes / graph / qa / wiki / system），
统一挂在 /api 下。除 auth 自身按需鉴权外，业务路由统一要求登录；
ingest 整组仅管理员，notes DELETE、wiki compile 等写操作在各 router 内单独挂 require_admin。

运维：结构化日志（setup_logging）+ 全局未捕获异常兜底（CatchErrorsMiddleware）。
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from config import settings
from routers import agent, auth, collaboration, connectors, governance, graph, ingest, mcp_admin, notes, qa, search, spaces, system, tags, wiki
from services import es
from services.auth import get_current_user, require_admin
from services.logging import setup_logging
from services.middleware import CatchErrorsMiddleware
import mcp_server

# 在创建 app 之前配日志，确保 startup/uvicorn 日志也走统一格式。
setup_logging(level=settings.log_level, fmt=settings.log_format)

# MCP server 懒加载：mcp 未装时跳过挂载（is_available 返回 False），不影响其余接口。
_mcp_app = None
_mcp_session_cm = None
if mcp_server.is_available():
    _mcp_instance = mcp_server._get_mcp()
    _mcp_app = mcp_server.get_app()
    _mcp_session_cm = _mcp_instance.session_manager.run()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动时确保 ES 索引存在（未配置 ES 时为空操作，关键词路回退 ILIKE）
    es.ensure_index()
    # MCP session manager 需在 lifespan 内 run（stateless_http 也需要）
    if _mcp_session_cm is not None:
        await _mcp_session_cm.__aenter__()
    try:
        yield
    finally:
        if _mcp_session_cm is not None:
            await _mcp_session_cm.__aexit__(None, None, None)


app = FastAPI(title="fuxi 知识库 API", version=settings.app_version, lifespan=lifespan)


def _error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        423: "locked",
        429: "rate_limited",
        503: "service_unavailable",
    }.get(status_code, "http_error")


@app.exception_handler(HTTPException)
async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": _error_code(exc.status_code), "message": message}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, _exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": "请求参数不合法"}},
    )

# CORS：移动端 App（尤其 Expo Web 调试平台）直接访问后端时需要。
# Web 前端走 Next.js /api 反代同源，不受影响；移动端走 Bearer JWT。
# CORS_ORIGINS 逗号分隔；生产建议收紧到实际域名。
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 全局未捕获异常兜底：记录结构化日志后返回 500 通用文案，不泄露堆栈。
# 放在 CORS 之后（后加的中间件在最外层执行），故异常处理包住 CORS 之外的全部链路。
app.add_middleware(CatchErrorsMiddleware)

# auth 自身公开（login）/ 内部按需鉴权，不挂全局依赖
app.include_router(auth.router, prefix="/api")

# 业务路由统一挂在 /api 下（对齐 docs/api-contract.md），统一要求登录。
# 写操作在各 router 内按系统角色或空间角色校验。
_auth = [Depends(get_current_user)]
app.include_router(ingest.router, prefix="/api", dependencies=_auth)
app.include_router(search.router, prefix="/api", dependencies=_auth)
app.include_router(notes.router, prefix="/api", dependencies=_auth)
app.include_router(tags.router, prefix="/api", dependencies=_auth)
app.include_router(graph.router, prefix="/api", dependencies=_auth)
app.include_router(qa.router, prefix="/api", dependencies=_auth)
app.include_router(wiki.router, prefix="/api", dependencies=_auth)
app.include_router(spaces.router, prefix="/api", dependencies=_auth)
app.include_router(system.router, prefix="/api", dependencies=_auth)
app.include_router(governance.router, prefix="/api", dependencies=_auth)
app.include_router(connectors.router, prefix="/api", dependencies=_auth)
app.include_router(collaboration.router, prefix="/api", dependencies=_auth)
app.include_router(agent.router, prefix="/api", dependencies=_auth)
# MCP token 管理（仅管理员）
app.include_router(mcp_admin.router, prefix="/api", dependencies=[Depends(require_admin)])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# MCP app 自带 /mcp 路由。挂在根路径且置于普通路由之后，使公开地址保持精确 /mcp
# （若 mount 到 /mcp，FastMCP 默认路径会变成 /mcp/mcp）。
if _mcp_app is not None:
    app.mount("/", _mcp_app)

# 移动端 standalone SPA
import os
_mobile_dir = os.path.join(os.path.dirname(__file__), '..', settings.mobile_dir)
if os.path.isdir(_mobile_dir):
    app.mount("/m", StaticFiles(directory=_mobile_dir, html=True), name="mobile")
