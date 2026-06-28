"""系统状态 HTTP 接口。

  GET /system/status   版本 / 存储后端 / 数据库与扩展版本 / 知识库规模 / 占用与磁盘容量

驱动前端左下角「系统情况」面板。只读聚合，登录用户均可见。
"""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter

from config import settings
from db import pool

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
def status() -> dict:
    with pool.connection() as conn:
        pgvector = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        pgver = conn.execute("SELECT current_setting('server_version')").fetchone()
        notes = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
        entities = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        wikis = conn.execute("SELECT count(*) FROM wiki_pages").fetchone()[0]
        db_size = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]

    # 磁盘容量：local 后端取落盘目录所在文件系统；R2 时此数仅代表服务器盘，前端据 backend 区分说明
    disk = None
    try:
        root = settings.storage_local_root
        path = root if os.path.isdir(root) else "/"
        total, used, free = shutil.disk_usage(path)
        disk = {"total_bytes": total, "used_bytes": used, "free_bytes": free}
    except OSError:
        disk = None

    return {
        "version": settings.app_version,
        "storage_backend": settings.storage_backend,
        "pg_version": (pgver[0] if pgver else "").split(" ")[0],
        "pgvector_version": pgvector[0] if pgvector else None,
        "notes": int(notes),
        "entities": int(entities),
        "wikis": int(wikis),
        "db_size_bytes": int(db_size),
        "disk": disk,
    }
