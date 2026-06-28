"""FastAPI 入口。

  uvicorn main:app --reload --port 8000

目前挂载 ingest 路由；search / graph / notes / wiki 后续逐个加进来。
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from config import settings
from routers import auth, graph, ingest, notes, qa, search, system, wiki
from services import es
from services.auth import get_current_user, require_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动时确保 ES 索引存在（未配置 ES 时为空操作，关键词路回退 ILIKE）
    es.ensure_index()
    yield


app = FastAPI(title="fuxi 知识库 API", version=settings.app_version, lifespan=lifespan)

# auth 自身公开（login）/ 内部按需鉴权，不挂全局依赖
app.include_router(auth.router, prefix="/api")

# 业务路由统一挂在 /api 下（对齐 docs/api-contract.md），统一要求登录。
# 入库整组仅管理员；notes DELETE、wiki compile 等写操作在各 router 内单独挂 require_admin。
_auth = [Depends(get_current_user)]
app.include_router(ingest.router, prefix="/api", dependencies=[Depends(require_admin)])
app.include_router(search.router, prefix="/api", dependencies=_auth)
app.include_router(notes.router, prefix="/api", dependencies=_auth)
app.include_router(graph.router, prefix="/api", dependencies=_auth)
app.include_router(qa.router, prefix="/api", dependencies=_auth)
app.include_router(wiki.router, prefix="/api", dependencies=_auth)
app.include_router(system.router, prefix="/api", dependencies=_auth)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
