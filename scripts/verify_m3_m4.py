"""生产验收：M3 生命周期与 M4 协作/连接器/Agent 主链路。"""
from __future__ import annotations

import secrets
import time
import uuid

import httpx

from db import pool
from services import distribution
from services.auth import hash_password

WEB = "http://127.0.0.1:19000"
PASSWORD = "FuxiTest2026"


def _ok(response: httpx.Response, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url}: "
            f"expected {expected}, got {response.status_code}: {response.text[:500]}"
        )
    return response.json() if response.content else {}


def _wait_jobs(job_ids: list[uuid.UUID]) -> None:
    for _ in range(80):
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT status FROM jobs WHERE id = ANY(%s)", (job_ids,)
            ).fetchall()
        if len(rows) == len(job_ids) and all(row[0] in ("done", "failed") for row in rows):
            return
        time.sleep(0.25)
    raise AssertionError("M3/M4 验收任务未在时限内结束")


def main() -> int:
    suffix = secrets.token_hex(4)
    user_id, space_id, source_id, note_id = (uuid.uuid4() for _ in range(4))
    job_ids: list[uuid.UUID] = []

    try:
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO users(id,username,email,password_hash,display_name,role,is_active)
                VALUES(%s,%s,%s,%s,%s,'member',TRUE)
                """,
                (
                    user_id,
                    f"verify_m34_{suffix}",
                    f"verify_m34_{suffix}@example.invalid",
                    hash_password(PASSWORD),
                    "Verify M3/M4",
                ),
            )
            conn.execute(
                "INSERT INTO spaces(id,slug,name,owner_id) VALUES(%s,%s,%s,%s)",
                (space_id, f"verify-m34-{suffix}", "Verify M3/M4", user_id),
            )
            conn.execute(
                "INSERT INTO space_members(space_id,user_id,role) VALUES(%s,%s,'space_admin')",
                (space_id, user_id),
            )
            conn.execute(
                """
                INSERT INTO source_documents(id,space_id,source_type,locator,display_name)
                VALUES(%s,%s,'manual',%s,%s)
                """,
                (source_id, space_id, f"verify://{suffix}", "Verify source"),
            )
            conn.execute(
                """
                INSERT INTO notes(
                    id,title,source_type,summary,content,tags,ingest_status,
                    space_id,created_by,source_document_id
                )
                VALUES(%s,%s,'manual','verify','verify content',%s,'done',%s,%s,%s)
                """,
                (note_id, f"Verify note {suffix}", [f"verify-{suffix}"],
                 space_id, user_id, source_id),
            )

        with httpx.Client(base_url=WEB, timeout=20.0) as client:
            _ok(client.post(
                "/api/auth/login",
                json={
                    "identifier": f"verify_m34_{suffix}",
                    "password": PASSWORD,
                    "client": "web",
                },
            ))

            edited = _ok(
                client.patch(
                    f"/api/notes/{note_id}",
                    json={"title": f"Verify edited {suffix}"},
                ),
                202,
            )
            job_ids.append(uuid.UUID(edited["job_id"]))
            versions = _ok(client.get(f"/api/notes/{note_id}/versions"))["items"]
            assert versions and versions[0]["change_type"] == "edit"

            _ok(client.delete(f"/api/notes/{note_id}"), 204)
            trash = _ok(client.get("/api/notes/trash"))["items"]
            assert str(note_id) in {item["id"] for item in trash}
            restored = _ok(client.post(f"/api/notes/{note_id}/restore"), 202)
            job_ids.append(uuid.UUID(restored["job_id"]))

            subscription = _ok(
                client.post(
                    "/api/subscriptions",
                    json={
                        "space_id": str(space_id),
                        "scope_type": "space",
                        "scope_value": str(space_id),
                    },
                ),
                201,
            )
            distribution.emit_change(
                space_id, note_id, "updated", f"Verify event {suffix}"
            )
            notifications = _ok(client.get("/api/notifications"))
            assert notifications["unread"] == 1
            _ok(
                client.delete(f"/api/subscriptions/{subscription['id']}"),
                204,
            )

            connector = _ok(
                client.post(
                    "/api/connectors",
                    json={
                        "space_id": str(space_id),
                        "provider": "confluence",
                        "name": f"Verify connector {suffix}",
                        "config": {"base_url": "https://example.invalid"},
                        "credentials": {
                            "email": "verify@example.invalid",
                            "api_token": secrets.token_urlsafe(24),
                        },
                    },
                ),
                201,
            )
            listed = _ok(client.get(f"/api/connectors?space_id={space_id}"))["items"]
            assert len(listed) == 1 and "credentials" not in listed[0]
            _ok(client.delete(f"/api/connectors/{connector['id']}"), 204)

            agent = _ok(
                client.post("/api/agent/runs", json={"space_id": str(space_id)}),
                202,
            )
            job_ids.append(uuid.UUID(agent["job_id"]))
            _wait_jobs(job_ids)

            # 最终保持软删除态，让 ES 删除路径也接受生产验收。
            _ok(client.delete(f"/api/notes/{note_id}"), 204)

        print("PASS: lifecycle / trash / notifications / connector crypto / agent queue")
        return 0
    finally:
        with pool.connection() as conn:
            conn.execute("DELETE FROM audit_log WHERE user_id=%s", (user_id,))
            conn.execute("DELETE FROM jobs WHERE id=ANY(%s) OR note_id=%s", (job_ids, note_id))
            conn.execute("DELETE FROM notes WHERE id=%s", (note_id,))
            conn.execute("DELETE FROM source_documents WHERE id=%s", (source_id,))
            conn.execute("DELETE FROM spaces WHERE id=%s", (space_id,))
            conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


if __name__ == "__main__":
    raise SystemExit(main())
