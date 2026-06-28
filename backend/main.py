"""FastAPI 入口。

  uvicorn main:app --reload --port 8000

目前挂载 ingest 路由；search / graph / notes / wiki 后续逐个加进来。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from routers import graph, ingest, notes, qa, search, wiki
from services import es


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动时确保 ES 索引存在（未配置 ES 时为空操作，关键词路回退 ILIKE）
    es.ensure_index()
    yield


app = FastAPI(title="fuxi 知识库 API", version="0.1.0", lifespan=lifespan)

# 所有业务路由统一挂在 /api 下（对齐 docs/api-contract.md）
app.include_router(ingest.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(qa.router, prefix="/api")
app.include_router(wiki.router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
