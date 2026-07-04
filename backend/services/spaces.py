"""空间（Spaces）权限服务 —— M2 多团队内容隔离的核心。

双层角色模型：
  - 系统级 users.role（member/admin）：admin = sysadmin，管用户/MCP token/全局看板。
    sysadmin 对全部空间天然有 space_admin 权限（不写 space_members 行，避免冗余）。
  - 空间级 space_members.role（viewer/editor/space_admin）：一用户在不同空间可有不同角色。
    viewer       只读空间内容（检索/问答/浏览/图谱/wiki）
    editor       可入库/编辑笔记/生成 Q&A
    space_admin  管空间成员 + 编译 wiki + 删笔记

权限感知检索的关键：把「用户可见空间集合」注入到每条查 notes 的 SQL 和 ES query。
本模块提供两个收敛点：
  - visible_space_ids(conn, user)   → 返回空间 id 列表（sysadmin 返回 None 表示全可见）
  - space_filter(user, alias)       → 返回 (sql_fragment, params)，sysadmin 返回 ("", [])

最终架构见 docs/architecture.md。CurrentUser 见 services/auth.py。
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException

from db import pool
from services.auth import CurrentUser

# 空间内角色权限等级（数字越大权限越大）。用于 require_space_role 比较。
_ROLE_LEVEL = {"viewer": 1, "editor": 2, "space_admin": 3}


def visible_space_ids(conn, user: CurrentUser) -> list[uuid.UUID] | None:
    """用户可见空间集合。

    sysadmin（users.role='admin'）返回 None 表示全可见 —— SQL 不加 space 过滤。
    普通用户返回其 space_members 里的 space_id 列表（空列表也合法，表示看不到任何空间）。
    每次请求查库（与 _load_user 一致，保证成员变更实时生效）。
    """
    if user.is_admin:
        return None
    rows = conn.execute(
        "SELECT space_id FROM space_members WHERE user_id = %s",
        (user.id,),
    ).fetchall()
    return [r[0] for r in rows]


def visible_space_strs(conn, user: CurrentUser) -> list[str] | None:
    """同 visible_space_ids 但返回字符串形式（供 ES terms filter 用）。sysadmin 返回 None。"""
    ids = visible_space_ids(conn, user)
    if ids is None:
        return None
    return [str(i) for i in ids]


def space_filter_from(
    space_ids: list[uuid.UUID] | None,
    alias: str = "notes",
) -> tuple[str, list]:
    """用已查好的 space_ids 生成 SQL 空间过滤片段（避免每路查询重复开连接查 space_members）。

    先 `sids = spaces.visible_space_ids(conn, user)` 拿到集合，再调本函数生成片段。
    space_ids=None（仅 sysadmin 全可见）→ ("", [])。
    与 user 解耦：admin 决策已编码进 space_ids（None=全可见），故无需传 user，MCP 也能复用。
    """
    if space_ids is None:
        return ("", [])
    if not space_ids:
        # 普通用户但无任何空间成员 → 匹配不上任何笔记（空集合 ANY 永假）
        return (f" AND {alias}.space_id = ANY(%s::uuid[])", [[]])
    return (f" AND {alias}.space_id = ANY(%s::uuid[])", [space_ids])


def role_in_space(conn, user: CurrentUser, space_id) -> str | None:
    """用户在某空间的角色。

    sysadmin 返回 'space_admin'（对全部空间天然最高权限，不查表）。
    普通用户查 space_members；非成员返回 None。
    """
    if user.is_admin:
        return "space_admin"
    row = conn.execute(
        "SELECT role FROM space_members WHERE space_id = %s AND user_id = %s",
        (space_id, user.id),
    ).fetchone()
    return row[0] if row else None


def assert_space_role(user: CurrentUser, space_id, min_role: str) -> str:
    """校验用户在某空间有至少 min_role 权限，不满足抛 403。返回实际角色。

    min_role ∈ {viewer, editor, space_admin}。sysadmin 恒通过。
    """
    with pool.connection() as conn:
        role = role_in_space(conn, user, space_id)
    if role is None:
        raise HTTPException(status_code=403, detail="你不在此空间，或空间不存在")
    if _ROLE_LEVEL.get(role, 0) < _ROLE_LEVEL[min_role]:
        raise HTTPException(
            status_code=403,
            detail=f"需要该空间的「{min_role}」权限（你当前是「{role}」）",
        )
    return role


def get_note_space(conn, note_id) -> uuid.UUID | None:
    """取一篇笔记所属空间 id。用于「对单篇笔记的操作」反查其空间再校验角色。"""
    row = conn.execute(
        "SELECT space_id FROM notes WHERE id = %s", (note_id,)
    ).fetchone()
    return row[0] if row else None


def assert_note_role(user: CurrentUser, note_id, min_role: str) -> str:
    """对单篇笔记操作的角色校验：取笔记空间 → 校验角色。sysadmin 恒通过。

    用于 generate-qa / delete / compile 等写操作的前置校验。
    笔记不存在抛 404；无权抛 403。
    """
    with pool.connection() as conn:
        space_id = get_note_space(conn, note_id)
    if space_id is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return assert_space_role(user, space_id, min_role)
