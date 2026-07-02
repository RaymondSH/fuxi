"""生产验收：双用户跨空间隔离、Cookie 鉴权、MCP 空间绑定。

脚本创建唯一前缀的临时用户/空间/笔记/实体/token，调用真实 HTTP API 验证，finally 中清理。
只用于部署后的受控验收：
  cd /opt/fuxi/backend && /bin/bash -lc \
    "PYTHONPATH=. .venv/bin/python ../scripts/verify_m0_m2.py"
"""
from __future__ import annotations

import json
import secrets
import time
import uuid

import httpx

from db import pool
from routers.mcp_admin import _PREFIX_LEN
from services.auth import hash_password

BACKEND = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:19000"
PASSWORD = "FuxiTest2026"


def _ok(response: httpx.Response, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url}: "
            f"expected {expected}, got {response.status_code}: {response.text[:500]}"
        )
    return response.json() if response.content else {}


def main() -> int:
    suffix = secrets.token_hex(4)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    space_a, space_b = uuid.uuid4(), uuid.uuid4()
    note_a, note_b = uuid.uuid4(), uuid.uuid4()
    worker_note: uuid.UUID | None = None
    entity_a, entity_b = uuid.uuid4(), uuid.uuid4()
    token_id = uuid.uuid4()
    mcp_plain = secrets.token_urlsafe(32)
    created_users = [user_a, user_b]

    try:
        with pool.connection() as conn:
            for uid, label in ((user_a, "a"), (user_b, "b")):
                conn.execute(
                    """
                    INSERT INTO users
                      (id, username, email, password_hash, display_name, role, is_active,
                       failed_login_attempts, locked_until)
                    VALUES (%s, %s, %s, %s, %s, 'member', TRUE, 5, NOW() - INTERVAL '1 minute')
                    """,
                    (
                        uid,
                        f"verify_{label}_{suffix}",
                        f"verify_{label}_{suffix}@example.invalid",
                        hash_password(PASSWORD),
                        f"Verify {label.upper()}",
                    ),
                )
            conn.execute(
                "INSERT INTO spaces (id, slug, name, owner_id) VALUES (%s, %s, %s, %s)",
                (space_a, f"verify-a-{suffix}", "Verify A", user_a),
            )
            conn.execute(
                "INSERT INTO spaces (id, slug, name, owner_id) VALUES (%s, %s, %s, %s)",
                (space_b, f"verify-b-{suffix}", "Verify B", user_b),
            )
            conn.execute(
                "INSERT INTO space_members (space_id, user_id, role) VALUES (%s, %s, 'space_admin')",
                (space_a, user_a),
            )
            conn.execute(
                "INSERT INTO space_members (space_id, user_id, role) VALUES (%s, %s, 'space_admin')",
                (space_b, user_b),
            )
            conn.execute(
                "INSERT INTO space_members (space_id, user_id, role) VALUES (%s, %s, 'editor')",
                (space_a, user_b),
            )
            conn.execute(
                """
                INSERT INTO notes
                  (id, title, source_type, summary, content, tags, ingest_status, space_id, created_by)
                VALUES (%s, %s, 'manual', %s, %s, %s, 'done', %s, %s)
                """,
                (
                    note_a, f"Secret A {suffix}", "summary-a", "content-a",
                    [f"tag-a-{suffix}"], space_a, user_a,
                ),
            )
            conn.execute(
                """
                INSERT INTO notes
                  (id, title, source_type, summary, content, tags, ingest_status, space_id, created_by)
                VALUES (%s, %s, 'manual', %s, %s, %s, 'done', %s, %s)
                """,
                (
                    note_b, f"Secret B {suffix}", "summary-b", "content-b",
                    [f"tag-b-{suffix}"], space_b, user_b,
                ),
            )
            conn.execute(
                "INSERT INTO entities (id, name, type) VALUES (%s, %s, 'concept')",
                (entity_a, f"Entity A {suffix}"),
            )
            conn.execute(
                "INSERT INTO entities (id, name, type) VALUES (%s, %s, 'concept')",
                (entity_b, f"Entity B {suffix}"),
            )
            conn.execute(
                "INSERT INTO note_entities (note_id, entity_id) VALUES (%s, %s), (%s, %s)",
                (note_a, entity_a, note_b, entity_b),
            )
            conn.execute(
                """
                INSERT INTO mcp_tokens (id, name, token_hash, prefix, space_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    token_id, f"verify-{suffix}", hash_password(mcp_plain),
                    mcp_plain[:_PREFIX_LEN], space_a,
                ),
            )
        with httpx.Client(base_url=WEB, timeout=20.0) as web_a:
            login = _ok(web_a.post(
                "/api/auth/login",
                json={"identifier": f"verify_a_{suffix}", "password": PASSWORD, "client": "web"},
            ))
            assert login["access_token"] is None and login["refresh_token"] is None
            assert web_a.cookies.get("fuxi_access")
            _ok(web_a.get("/api/auth/me"))

            # 过期锁定已自动解除；Cookie refresh 能补发 access 且不暴露 token 到响应。
            web_a.cookies.delete("fuxi_access")
            refreshed = _ok(web_a.post("/api/auth/refresh", json={"client": "web"}))
            assert refreshed["access_token"] is None and web_a.cookies.get("fuxi_access")

            notes = _ok(web_a.get("/api/notes"))["items"]
            assert {item["id"] for item in notes} == {str(note_a)}
            assert web_a.get(f"/api/notes/{note_b}").status_code == 404
            assert web_a.get(f"/api/ingest/{note_b}").status_code == 404

            tags = _ok(web_a.get("/api/tags"))["items"]
            tag_names = {item["name"] for item in tags}
            assert f"tag-a-{suffix}" in tag_names
            assert f"tag-b-{suffix}" not in tag_names

            graph = _ok(web_a.get("/api/graph"))
            node_names = {item["name"] for item in graph["nodes"]}
            assert f"Entity A {suffix}" in node_names
            assert f"Entity B {suffix}" not in node_names

            status = _ok(web_a.get("/api/system/status"))
            assert status["notes"] == 1 and status["entities"] == 1
            assert web_a.delete(f"/api/spaces/{space_a}").status_code == 409

        with httpx.Client(base_url=WEB, timeout=20.0) as web_b:
            _ok(web_b.post(
                "/api/auth/login",
                json={"identifier": f"verify_b_{suffix}", "password": PASSWORD, "client": "web"},
            ))
            # editor 可以入库，但不能编译 Wiki（须 space_admin）。
            denied_compile = web_b.post(
                "/api/wiki/compile",
                json={
                    "title": "Denied compile",
                    "source_note_ids": [str(note_a)],
                    "space_id": str(space_a),
                },
            )
            assert denied_compile.status_code == 403
            # 故意投递不可达地址，只验证 202 + 独立 worker 消费，不调用外部 AI。
            probe = _ok(
                web_b.post(
                    "/api/ingest/url",
                    json={"url": "http://127.0.0.1:9", "space_id": str(space_a)},
                ),
                202,
            )
            worker_note = uuid.UUID(probe["note_id"])

        # 移动端仍拿 Bearer 双 token；refresh 绝不能冒充 access。
        with httpx.Client(base_url=BACKEND, timeout=20.0) as mobile_a:
            mobile_login = _ok(mobile_a.post(
                "/api/auth/login",
                json={"identifier": f"verify_a_{suffix}", "password": PASSWORD, "client": "mobile"},
            ))
            assert mobile_login["access_token"] and mobile_login["refresh_token"]
            denied = mobile_a.get(
                "/api/notes",
                headers={"Authorization": f"Bearer {mobile_login['refresh_token']}"},
            )
            assert denied.status_code == 401

        # MCP token 只可见绑定空间 A。
        mcp_headers = {
            "Authorization": f"Bearer {mcp_plain}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "verify", "version": "1"},
            },
        }
        _ok(httpx.post(f"{WEB}/mcp", headers=mcp_headers, json=initialize, timeout=20.0))
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {"size": 100}},
        }
        result = _ok(httpx.post(f"{WEB}/mcp", headers=mcp_headers, json=call, timeout=20.0))
        text = result["result"]["content"][0]["text"]
        mcp_notes = json.loads(text)["items"]
        assert {item["id"] for item in mcp_notes} == {str(note_a)}

        # 独立 worker 必须领取持久化队列；探针 payload 非法，预期被消费并落 failed。
        assert worker_note is not None
        worker_status = None
        for _ in range(20):
            with pool.connection() as conn:
                row = conn.execute(
                    "SELECT status FROM jobs WHERE note_id = %s AND job_type = 'ingest'",
                    (worker_note,),
                ).fetchone()
            worker_status = row[0] if row else None
            if worker_status == "failed":
                break
            time.sleep(0.25)
        assert worker_status == "failed", f"worker 未消费持久化任务：{worker_status}"

        print("PASS: auth cookies / refresh isolation / durable worker / spaces ACL / graph / tags / MCP")
        return 0
    finally:
        with pool.connection() as conn:
            conn.execute("DELETE FROM audit_log WHERE user_id = ANY(%s)", (created_users,))
            note_ids = [note_a, note_b]
            if worker_note is not None:
                note_ids.append(worker_note)
            conn.execute("DELETE FROM notes WHERE id = ANY(%s)", (note_ids,))
            conn.execute("DELETE FROM entities WHERE id = ANY(%s)", ([entity_a, entity_b],))
            conn.execute(
                "DELETE FROM source_documents WHERE space_id = ANY(%s)",
                ([space_a, space_b],),
            )
            conn.execute("DELETE FROM spaces WHERE id = ANY(%s)", ([space_a, space_b],))
            conn.execute("DELETE FROM users WHERE id = ANY(%s)", (created_users,))


if __name__ == "__main__":
    raise SystemExit(main())
