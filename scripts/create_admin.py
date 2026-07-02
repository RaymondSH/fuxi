"""引导首个管理员（系统不开放自助注册，第一个 admin 用本脚本建）。

运行（在服务器上，带 backend 到 PYTHONPATH）：
  cd /opt/fuxi/backend && PYTHONPATH=. .venv/bin/python ../scripts/create_admin.py \
      --email admin@example.com --password '强密码'

幂等：邮箱已存在则改其密码并提升为 admin（方便重置）。
"""
from __future__ import annotations

import argparse
import sys

from db import pool
from services import auth


def main() -> int:
    parser = argparse.ArgumentParser(description="创建 / 重置管理员账号")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--username", default=None, help="登录用户名，可选（可用 用户名 或 邮箱 登录）")
    parser.add_argument("--name", default=None, help="显示名，可选")
    args = parser.parse_args()

    if len(args.password) < 6:
        print("密码至少 6 位", file=sys.stderr)
        return 1

    try:
        auth.validate_password(args.password)
    except Exception as exc:  # validate_password 抛 HTTPException(400)
        print(f"密码强度不足：{getattr(exc, 'detail', exc)}", file=sys.stderr)
        return 1

    pw_hash = auth.hash_password(args.password)
    with pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (email, password_hash, display_name, username, role)
            VALUES (%s, %s, %s, %s, 'admin')
            ON CONFLICT (email) DO UPDATE
              SET password_hash = EXCLUDED.password_hash,
                  role = 'admin',
                  is_active = TRUE,
                  display_name = COALESCE(EXCLUDED.display_name, users.display_name),
                  username = COALESCE(EXCLUDED.username, users.username)
            RETURNING id, email, username, role
            """,
            (args.email, pw_hash, args.name, args.username),
        ).fetchone()
    print(f"✅ 管理员就绪：{row[1]}（id={row[0]}, username={row[2]}, role={row[3]}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
