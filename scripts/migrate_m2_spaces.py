"""M2 空间迁移 —— 把全局共享数据归入 default 空间，重建 ES 索引带上 space_id。

前置：已执行 sql/18-22（00_init.sql 已含）。本脚本做 SQL 无法做的事：
  1. 确认 default 空间存在、历史数据已回填（SQL 自带，这里只校验）。
  2. 重建 ES 索引：mapping 加了 space_id，必须删旧索引重建（ES mapping 不可原地改字段类型）。
  3. 遍历已入库笔记，调 index_note 重灌（带上 space_id）。
  4. 打印统计。

运行（在服务器上，带 backend 到 PYTHONPATH）：
  cd /opt/fuxi/backend && PYTHONPATH=. .venv/bin/python ../scripts/migrate_m2_spaces.py

幂等：可重复跑。ES 不可达时跳过重建步骤，仅打印 PG 统计。
"""
from __future__ import annotations

import sys

from db import pool
from services import es


def _stats() -> dict:
    """迁移后统计：空间数 / 笔记归入数 / 成员数。"""
    with pool.connection() as conn:
        spaces = conn.execute("SELECT count(*) FROM spaces").fetchone()[0]
        notes_with_space = conn.execute(
            "SELECT count(*) FROM notes WHERE space_id IS NOT NULL"
        ).fetchone()[0]
        notes_total = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
        wiki_with_space = conn.execute(
            "SELECT count(*) FROM wiki_pages WHERE space_id IS NOT NULL"
        ).fetchone()[0]
        members = conn.execute("SELECT count(*) FROM space_members").fetchone()[0]
        users = conn.execute("SELECT count(*) FROM users").fetchone()[0]
    return {
        "spaces": spaces,
        "notes_with_space": notes_with_space,
        "notes_total": notes_total,
        "wiki_with_space": wiki_with_space,
        "members": members,
        "users": users,
    }


def _rebuild_es_index() -> int:
    """删旧 ES 索引 → 重建（带新 mapping）→ 遍历 done 笔记重灌。返回重灌条数。

    mapping 里 space_id 字段由 es._MAPPING 提供（M2 已加）。
    """
    if not es._is_enabled():
        print("⚠️  ES 未配置，跳过索引重建。关键词检索将回退 ILIKE。")
        return 0

    c = es._get_client()

    # 1. 删旧索引（mapping 变了，不能原地改）
    try:
        r = c.delete(f"/{es._INDEX}")
        if r.status_code in (200, 404):
            print(f"🗑️  删除旧索引 {es._INDEX}（{r.status_code}）")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  删旧索引失败（忽略，ensure_index 会重建）：{exc}", file=sys.stderr)

    # 2. 重建（ensure_index 会按新 _MAPPING 建）
    es.ensure_index()

    # 3. 遍历 done 笔记重灌（带 space_id）
    count = 0
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, title, COALESCE(summary,''), COALESCE(content,''), "
            "COALESCE(tags,'{}'), COALESCE(source_type,''), "
            "COALESCE(space_id::text,'') "
            "FROM notes WHERE ingest_status = 'done'"
        ).fetchall()
    for r in rows:
        note_id, title, summary, content, tags, source_type, space_id_str = r
        es.index_note(
            str(note_id), title, summary, content,
            list(tags) if tags else [], source_type,
            space_id=space_id_str,
        )
        count += 1
        if count % 50 == 0:
            print(f"  ... 已重灌 {count} 篇")
    return count


def main() -> int:
    print("=== M2 空间迁移 ===\n")

    # 1. 校验 default 空间 + 回填（SQL 18-22 已做，这里只确认）
    with pool.connection() as conn:
        default = conn.execute(
            "SELECT id, slug, name FROM spaces WHERE is_default"
        ).fetchone()
    if not default:
        print("❌ default 空间不存在！请先执行 sql/18_spaces.sql", file=sys.stderr)
        return 1
    print(f"✅ default 空间：{default[1]}（{default[2]}，id={default[0]}）")

    # 2. 重建 ES 索引（带 space_id）
    print("\n--- 重建 ES 索引（mapping 加 space_id）---")
    reindexed = _rebuild_es_index()
    print(f"✅ 重灌 {reindexed} 篇笔记到 ES")

    # 3. 统计
    s = _stats()
    print("\n--- 统计 ---")
    print(f"  空间数：{s['spaces']}")
    print(f"  笔记归入空间：{s['notes_with_space']} / {s['notes_total']}")
    if s["notes_total"] and s["notes_with_space"] != s["notes_total"]:
        print(f"  ⚠️  {s['notes_total'] - s['notes_with_space']} 篇笔记未归入空间", file=sys.stderr)
    print(f"  wiki 归入空间：{s['wiki_with_space']}")
    print(f"  空间成员：{s['members']}（用户 {s['users']}）")
    if s["users"] and s["members"] < s["users"]:
        print(f"  ⚠️  部分用户未加入 default 空间", file=sys.stderr)

    print("\n=== 迁移完成 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
