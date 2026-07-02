"""把已入库的 done 笔记批量灌进 Elasticsearch（ik 中文分词索引）。

用途：ES 刚接上或重建索引后，把 PG 里已有的笔记补进 ES。
新建笔记在 ingest_worker._save 里已自动索引，本脚本只补存量。

运行（在服务器上，带 backend 到 PYTHONPATH，需 ES_URL 已配置）：
  cd /opt/fuxi/backend && PYTHONPATH=. bash -lc ".venv/bin/python ../scripts/reindex_es.py"
"""
from __future__ import annotations

import sys

from db import pool
from services import es


def main() -> None:
    if not es._is_enabled():
        print("ES_URL 未配置，无需 reindex（关键词路走 ILIKE）")
        return

    es.ensure_index()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, COALESCE(summary,''), COALESCE(content,''),
                   tags, source_type, space_id::text
            FROM notes
            WHERE ingest_status = 'done' AND deleted_at IS NULL
            """
        ).fetchall()

    ok, fail = 0, 0
    for nid, title, summary, content, tags, source_type, space_id in rows:
        try:
            es.index_note(
                str(nid),
                title=title,
                summary=summary,
                content=content,
                tags=tags or [],
                source_type=source_type,
                space_id=space_id,
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  失败 {nid}: {exc}")
            fail += 1
    # ES 近实时，索引后强制 refresh 让计数立即可见
    es._get_client().post(f"/{es._INDEX}/_refresh")
    print(f"reindex 完成：成功 {ok} 篇，失败 {fail} 篇")


if __name__ == "__main__":
    sys.exit(main())
