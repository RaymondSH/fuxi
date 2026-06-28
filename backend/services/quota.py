"""每日 token 配额：检查（超额抛 429）+ 记录用量到 token_usage。

按 USAGE_TZ 的自然日聚合 token_usage.total_tokens，与用户有效额度比较：
  - admin / 额度为 None 视为不限；
  - member 用 users.daily_token_limit，未设则用 config.default_daily_token_limit。
设计见 docs/auth-design.md。
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from config import settings
from db import pool
from services.auth import CurrentUser
from services.usage import Usage


def today() -> date:
    """按配置时区算「自然日」，配额次日 0 点重置以此为界。"""
    return datetime.now(ZoneInfo(settings.usage_tz)).date()


def used_today(user_id) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage "
            "WHERE user_id = %s AND usage_day = %s",
            (user_id, today()),
        ).fetchone()
    return int(row[0]) if row else 0


def check_quota(user: CurrentUser) -> None:
    """超过当日额度抛 429；不限额（admin / None）直接放行。"""
    limit = user.token_limit()
    if limit is None:
        return
    if used_today(user.id) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"今日 token 额度（{limit}）已用完，次日 0 点重置",
        )


def record_usage(user_id, operation: str, u: Usage | None) -> None:
    """把一次操作累计的 usage 落库；无用量（如纯关键词检索）不记。"""
    if u is None or u.total_tokens <= 0:
        return
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO token_usage "
            "(user_id, usage_day, operation, prompt_tokens, completion_tokens, total_tokens) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, today(), operation, u.prompt_tokens, u.completion_tokens, u.total_tokens),
        )
