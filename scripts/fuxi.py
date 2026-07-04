#!/usr/bin/env python3
"""fuxi 统一运维入口：账号、维护、索引、演示数据与生产验收。"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

WEB_URL = "http://127.0.0.1:19000"
BACKEND_URL = "http://127.0.0.1:8000"
VERIFY_PASSWORD = "FuxiTest2026"


def _pool():
    from db import pool

    return pool


def _http_ok(response: Any, expected: int = 200) -> dict[str, Any]:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url}: "
            f"expected {expected}, got {response.status_code}: {response.text[:500]}"
        )
    return response.json() if response.content else {}


def command_admin(args: argparse.Namespace) -> int:
    from services import auth

    try:
        auth.validate_password(args.password)
    except Exception as exc:  # HTTPException carries the user-facing reason in detail.
        print(f"密码强度不足：{getattr(exc, 'detail', exc)}", file=sys.stderr)
        return 1

    password_hash = auth.hash_password(args.password)
    with _pool().connection() as conn:
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
            (args.email, password_hash, args.name, args.username),
        ).fetchone()
    print(f"管理员就绪：{row[1]}（id={row[0]}, username={row[2]}, role={row[3]}）")
    return 0


def command_maintenance(_: argparse.Namespace) -> int:
    refresh_count = scan_count = connector_count = agent_count = 0
    with _pool().connection() as conn:
        due = conn.execute(
            """
            SELECT n.id,n.title FROM source_documents s
            JOIN notes n ON n.source_document_id=s.id
            WHERE s.status='active' AND s.refresh_policy<>'manual'
              AND s.next_refresh_at<=NOW() AND n.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM jobs j WHERE j.note_id=n.id
                  AND j.job_type='source_refresh' AND j.status IN ('queued','running')
              )
            """
        ).fetchall()
        for note_id, title in due:
            conn.execute(
                "INSERT INTO jobs(id,job_type,note_id,payload,status,stage,title) "
                "VALUES(%s,'source_refresh',%s,'{}','queued','queued',%s)",
                (uuid.uuid4(), note_id, title),
            )
            refresh_count += 1

        spaces = conn.execute(
            """
            SELECT s.id FROM spaces s
            WHERE NOT EXISTS (
                SELECT 1 FROM governance_runs r
                WHERE r.space_id=s.id AND r.created_at>NOW()-INTERVAL '23 hours'
            )
            """
        ).fetchall()
        for (space_id,) in spaces:
            run_id, job_id = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                "INSERT INTO governance_runs(id,space_id) VALUES(%s,%s)",
                (run_id, space_id),
            )
            conn.execute(
                """
                INSERT INTO jobs(id,job_type,payload,status,stage,title)
                VALUES(%s,'governance_scan',
                    jsonb_build_object('run_id',%s::text,'space_id',%s::text),
                    'queued','queued','定时知识治理巡检')
                """,
                (job_id, run_id, space_id),
            )
            scan_count += 1

        connectors = conn.execute(
            """
            SELECT c.id,c.name FROM connector_accounts c
            WHERE c.status='active'
              AND (c.last_synced_at IS NULL OR c.last_synced_at<NOW()-INTERVAL '1 hour')
              AND NOT EXISTS (
                SELECT 1 FROM jobs j WHERE j.job_type='connector_sync'
                  AND j.status IN ('queued','running')
                  AND j.payload->>'connector_id'=c.id::text
              )
            """
        ).fetchall()
        for connector_id, name in connectors:
            conn.execute(
                "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
                "%s,'connector_sync',jsonb_build_object('connector_id',%s::text),"
                "'queued','queued',%s)",
                (uuid.uuid4(), connector_id, f"定时同步 {name}"),
            )
            connector_count += 1

        agent_spaces = conn.execute(
            """
            SELECT s.id FROM spaces s WHERE EXISTS (
                SELECT 1 FROM governance_issues gi
                WHERE gi.space_id=s.id AND gi.status='open'
            ) AND NOT EXISTS (
                SELECT 1 FROM agent_runs ar
                WHERE ar.space_id=s.id AND ar.created_at>NOW()-INTERVAL '23 hours'
            )
            """
        ).fetchall()
        for (space_id,) in agent_spaces:
            run_id = uuid.uuid4()
            conn.execute(
                "INSERT INTO agent_runs(id,space_id) VALUES(%s,%s)",
                (run_id, space_id),
            )
            conn.execute(
                "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
                "%s,'agent_plan',jsonb_build_object('run_id',%s::text,'space_id',%s::text),"
                "'queued','queued','定时治理 Agent 规划')",
                (uuid.uuid4(), run_id, space_id),
            )
            agent_count += 1

    print(
        f"queued refresh={refresh_count} governance={scan_count} "
        f"connectors={connector_count} agent={agent_count}"
    )
    return 0


def command_reindex(_: argparse.Namespace) -> int:
    from services import es

    if not es._is_enabled():
        print("ES_URL 未配置，无需 reindex（关键词检索将回退 ILIKE）")
        return 0

    es.ensure_index()
    with _pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id,title,COALESCE(summary,''),COALESCE(content,''),
                   tags,source_type,space_id::text
            FROM notes
            WHERE ingest_status='done' AND deleted_at IS NULL
            """
        ).fetchall()

    ok = fail = 0
    for note_id, title, summary, content, tags, source_type, space_id in rows:
        try:
            es.index_note(
                str(note_id),
                title=title,
                summary=summary,
                content=content,
                tags=tags or [],
                source_type=source_type,
                space_id=space_id,
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"失败 {note_id}: {exc}", file=sys.stderr)
            fail += 1
    es._get_client().post(f"/{es._INDEX}/_refresh")
    print(f"reindex 完成：成功 {ok} 篇，失败 {fail} 篇")
    return 1 if fail else 0


DEMO_NOTES = [
    {
        "slug": "rag-chunking",
        "title": "RAG 分块策略实战",
        "source_type": "pdf",
        "tags": ["RAG", "Embedding", "分块"],
        "summary": "递归字符切分兼顾语义边界与工程成本，通常是长文档入库的稳健默认。",
        "content": "固定窗口简单但会切断语义；滑动窗口可缓解边界丢失；语义切分召回更好但成本更高。",
        "entities": [("RAG", "concept"), ("Embedding", "concept")],
    },
    {
        "slug": "hybrid-search",
        "title": "语义检索与关键词检索",
        "source_type": "url",
        "tags": ["检索", "RRF", "Embedding"],
        "summary": "关键词检索精确，语义检索擅长同义改写，RRF 可以稳定融合两路结果。",
        "content": "关键词和语义检索的失败模式互补，实际系统通常采用混合检索。",
        "entities": [("RAG", "concept"), ("Embedding", "concept")],
    },
    {
        "slug": "pgvector",
        "title": "pgvector HNSW 调优笔记",
        "source_type": "url",
        "tags": ["PostgreSQL", "pgvector", "性能"],
        "summary": "HNSW 无需训练，ef_search 是召回与延迟的主要调节参数。",
        "content": "构建 HNSW 时需要关注 maintenance_work_mem 和并行构建参数。",
        "entities": [("pgvector", "product"), ("PostgreSQL", "product")],
    },
    {
        "slug": "agent-map",
        "title": "AI Agent 市场地图",
        "source_type": "image",
        "tags": ["Agent", "市场"],
        "summary": "Agent 生态可分为记忆、编排、垂直应用和评测可观测四层。",
        "content": "长期记忆、可靠编排和可重复评测是 Agent 产品化的主要基础设施。",
        "entities": [("Agent", "concept")],
    },
    {
        "slug": "es-ik",
        "title": "Elasticsearch 中文分词实践",
        "source_type": "docx",
        "tags": ["Elasticsearch", "中文分词"],
        "summary": "建索引用 ik_max_word，查询用 ik_smart，并为专有名词维护词典。",
        "content": "中文关键词检索需要合理分词，并可与向量检索通过 RRF 融合。",
        "entities": [("Elasticsearch", "product")],
    },
    {
        "slug": "long-context",
        "title": "长上下文会取代 RAG 吗",
        "source_type": "url",
        "tags": ["RAG", "LLM"],
        "summary": "长上下文简化单文档问答，但无法替代动态大规模语料中的检索和权限过滤。",
        "content": "长上下文和 RAG 解决的问题不同：前者扩大单次输入，后者负责选择、更新和授权。",
        "entities": [("RAG", "concept")],
    },
]


def command_seed_demo(_: argparse.Namespace) -> int:
    with _pool().connection() as conn:
        default_space = conn.execute(
            "SELECT id FROM spaces WHERE is_default ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not default_space:
            print("default 空间不存在，请先初始化 SQL 01~33", file=sys.stderr)
            return 1
        space_id = default_space[0]
        titles = [note["title"] for note in DEMO_NOTES]
        conn.execute("DELETE FROM notes WHERE title=ANY(%s)", (titles,))

        note_ids: dict[str, uuid.UUID] = {}
        for note in DEMO_NOTES:
            note_id = uuid.uuid4()
            note_ids[note["slug"]] = note_id
            conn.execute(
                """
                INSERT INTO notes(
                    id,title,source_type,summary,content,tags,ingest_status,space_id
                )
                VALUES(%s,%s,%s,%s,%s,%s,'done',%s)
                """,
                (
                    note_id,
                    note["title"],
                    note["source_type"],
                    note["summary"],
                    note["content"],
                    note["tags"],
                    space_id,
                ),
            )
            for name, entity_type in note["entities"]:
                entity = conn.execute(
                    """
                    INSERT INTO entities(name,type) VALUES(%s,%s)
                    ON CONFLICT(name,type) DO UPDATE SET name=EXCLUDED.name
                    RETURNING id
                    """,
                    (name, entity_type),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO note_entities(note_id,entity_id,mention_count)
                    VALUES(%s,%s,1) ON CONFLICT(note_id,entity_id) DO NOTHING
                    """,
                    (note_id, entity[0]),
                )

        source_ids = list(note_ids.values())
        sections = [
            {
                "heading": "核心结论",
                "paragraphs": [
                    {
                        "text": "RAG 通过混合检索选择可信上下文，分块、索引和权限过滤共同决定结果质量。",
                        "cites": [str(note_ids["rag-chunking"]), str(note_ids["hybrid-search"])],
                    }
                ],
            }
        ]
        conn.execute("DELETE FROM wiki_pages WHERE slug='rag'")
        conn.execute(
            """
            INSERT INTO wiki_pages(
                slug,title,content,sections,conflict,source_note_ids,space_id,compiled_at
            )
            VALUES('rag','检索增强生成（RAG）','',%s::jsonb,%s::jsonb,%s,%s,NOW())
            """,
            (
                json.dumps(sections, ensure_ascii=False),
                json.dumps(
                    {
                        "topic": "长上下文是否取代 RAG",
                        "sides": [
                            {
                                "note_id": str(note_ids["long-context"]),
                                "claim": "两者解决的问题不同，长期仍会共存。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                source_ids,
                space_id,
            ),
        )
    print(f"演示数据就绪：{len(DEMO_NOTES)} 篇笔记，1 个 Wiki")
    return 0


def command_verify_core(_: argparse.Namespace) -> int:
    import httpx
    from routers.mcp_admin import _PREFIX_LEN
    from services.auth import hash_password

    suffix = secrets.token_hex(4)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    space_a, space_b = uuid.uuid4(), uuid.uuid4()
    note_a, note_b = uuid.uuid4(), uuid.uuid4()
    entity_a, entity_b = uuid.uuid4(), uuid.uuid4()
    token_id = uuid.uuid4()
    worker_note: uuid.UUID | None = None
    mcp_plain = secrets.token_urlsafe(32)
    users = [user_a, user_b]

    try:
        with _pool().connection() as conn:
            for user_id, label in ((user_a, "a"), (user_b, "b")):
                conn.execute(
                    """
                    INSERT INTO users(
                        id,username,email,password_hash,display_name,role,is_active,
                        failed_login_attempts,locked_until
                    )
                    VALUES(%s,%s,%s,%s,%s,'member',TRUE,5,NOW()-INTERVAL '1 minute')
                    """,
                    (
                        user_id,
                        f"verify_{label}_{suffix}",
                        f"verify_{label}_{suffix}@example.invalid",
                        hash_password(VERIFY_PASSWORD),
                        f"Verify {label.upper()}",
                    ),
                )
            conn.execute(
                "INSERT INTO spaces(id,slug,name,owner_id) VALUES(%s,%s,'Verify A',%s)",
                (space_a, f"verify-a-{suffix}", user_a),
            )
            conn.execute(
                "INSERT INTO spaces(id,slug,name,owner_id) VALUES(%s,%s,'Verify B',%s)",
                (space_b, f"verify-b-{suffix}", user_b),
            )
            conn.execute(
                """
                INSERT INTO space_members(space_id,user_id,role)
                VALUES(%s,%s,'space_admin'),(%s,%s,'space_admin'),(%s,%s,'editor')
                """,
                (space_a, user_a, space_b, user_b, space_a, user_b),
            )
            for note_id, title, tag, space_id, creator in (
                (note_a, f"Secret A {suffix}", f"tag-a-{suffix}", space_a, user_a),
                (note_b, f"Secret B {suffix}", f"tag-b-{suffix}", space_b, user_b),
            ):
                conn.execute(
                    """
                    INSERT INTO notes(
                        id,title,source_type,summary,content,tags,ingest_status,space_id,created_by
                    )
                    VALUES(%s,%s,'manual','summary','content',%s,'done',%s,%s)
                    """,
                    (note_id, title, [tag], space_id, creator),
                )
            conn.execute(
                """
                INSERT INTO entities(id,name,type)
                VALUES(%s,%s,'concept'),(%s,%s,'concept')
                """,
                (entity_a, f"Entity A {suffix}", entity_b, f"Entity B {suffix}"),
            )
            conn.execute(
                "INSERT INTO note_entities(note_id,entity_id) VALUES(%s,%s),(%s,%s)",
                (note_a, entity_a, note_b, entity_b),
            )
            conn.execute(
                """
                INSERT INTO mcp_tokens(id,name,token_hash,prefix,space_id)
                VALUES(%s,%s,%s,%s,%s)
                """,
                (
                    token_id,
                    f"verify-{suffix}",
                    hash_password(mcp_plain),
                    mcp_plain[:_PREFIX_LEN],
                    space_a,
                ),
            )

        with httpx.Client(base_url=WEB_URL, timeout=20.0) as client_a:
            login = _http_ok(
                client_a.post(
                    "/api/auth/login",
                    json={
                        "identifier": f"verify_a_{suffix}",
                        "password": VERIFY_PASSWORD,
                        "client": "web",
                    },
                )
            )
            assert login["access_token"] is None and login["refresh_token"] is None
            assert client_a.cookies.get("fuxi_access")
            client_a.cookies.delete("fuxi_access")
            refreshed = _http_ok(
                client_a.post("/api/auth/refresh", json={"client": "web"})
            )
            assert refreshed["access_token"] is None
            notes = _http_ok(client_a.get("/api/notes"))["items"]
            assert {item["id"] for item in notes} == {str(note_a)}
            assert client_a.get(f"/api/notes/{note_b}").status_code == 404
            tags = _http_ok(client_a.get("/api/tags"))["items"]
            assert f"tag-a-{suffix}" in {item["name"] for item in tags}
            graph = _http_ok(client_a.get("/api/graph"))
            assert f"Entity B {suffix}" not in {item["name"] for item in graph["nodes"]}
            assert client_a.delete(f"/api/spaces/{space_a}").status_code == 409

        with httpx.Client(base_url=WEB_URL, timeout=20.0) as client_b:
            _http_ok(
                client_b.post(
                    "/api/auth/login",
                    json={
                        "identifier": f"verify_b_{suffix}",
                        "password": VERIFY_PASSWORD,
                        "client": "web",
                    },
                )
            )
            denied = client_b.post(
                "/api/wiki/compile",
                json={
                    "title": "Denied compile",
                    "source_note_ids": [str(note_a)],
                    "space_id": str(space_a),
                },
            )
            assert denied.status_code == 403
            probe = _http_ok(
                client_b.post(
                    "/api/ingest/url",
                    json={"url": "http://127.0.0.1:9", "space_id": str(space_a)},
                ),
                202,
            )
            worker_note = uuid.UUID(probe["note_id"])

        with httpx.Client(base_url=BACKEND_URL, timeout=20.0) as mobile:
            login = _http_ok(
                mobile.post(
                    "/api/auth/login",
                    json={
                        "identifier": f"verify_a_{suffix}",
                        "password": VERIFY_PASSWORD,
                        "client": "mobile",
                    },
                )
            )
            denied = mobile.get(
                "/api/notes",
                headers={"Authorization": f"Bearer {login['refresh_token']}"},
            )
            assert denied.status_code == 401

        headers = {
            "Authorization": f"Bearer {mcp_plain}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        _http_ok(
            httpx.post(
                f"{WEB_URL}/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "verify", "version": "1"},
                    },
                },
                timeout=20.0,
            )
        )
        result = _http_ok(
            httpx.post(
                f"{WEB_URL}/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "list_notes", "arguments": {"size": 100}},
                },
                timeout=20.0,
            )
        )
        mcp_notes = json.loads(result["result"]["content"][0]["text"])["items"]
        assert {item["id"] for item in mcp_notes} == {str(note_a)}

        worker_status = None
        for _attempt in range(20):
            with _pool().connection() as conn:
                row = conn.execute(
                    "SELECT status FROM jobs WHERE note_id=%s AND job_type='ingest'",
                    (worker_note,),
                ).fetchone()
            worker_status = row[0] if row else None
            if worker_status == "failed":
                break
            time.sleep(0.25)
        assert worker_status == "failed", f"worker 未消费持久化任务：{worker_status}"
        print("PASS: auth / refresh / worker / spaces ACL / graph / tags / MCP")
        return 0
    finally:
        with _pool().connection() as conn:
            conn.execute("DELETE FROM audit_log WHERE user_id=ANY(%s)", (users,))
            note_ids = [note_a, note_b, *([worker_note] if worker_note else [])]
            conn.execute("DELETE FROM notes WHERE id=ANY(%s)", (note_ids,))
            conn.execute("DELETE FROM entities WHERE id=ANY(%s)", ([entity_a, entity_b],))
            conn.execute(
                "DELETE FROM source_documents WHERE space_id=ANY(%s)",
                ([space_a, space_b],),
            )
            conn.execute("DELETE FROM spaces WHERE id=ANY(%s)", ([space_a, space_b],))
            conn.execute("DELETE FROM users WHERE id=ANY(%s)", (users,))


def _wait_jobs(job_ids: list[uuid.UUID]) -> None:
    for _attempt in range(80):
        with _pool().connection() as conn:
            rows = conn.execute(
                "SELECT status FROM jobs WHERE id=ANY(%s)",
                (job_ids,),
            ).fetchall()
        if len(rows) == len(job_ids) and all(row[0] in ("done", "failed") for row in rows):
            return
        time.sleep(0.25)
    raise AssertionError("验收任务未在时限内结束")


def command_verify_advanced(_: argparse.Namespace) -> int:
    import httpx
    from services import distribution
    from services.auth import hash_password

    suffix = secrets.token_hex(4)
    user_id, space_id, source_id, note_id = (uuid.uuid4() for _ in range(4))
    job_ids: list[uuid.UUID] = []

    try:
        with _pool().connection() as conn:
            conn.execute(
                """
                INSERT INTO users(id,username,email,password_hash,display_name,role,is_active)
                VALUES(%s,%s,%s,%s,'Verify M3/M4','member',TRUE)
                """,
                (
                    user_id,
                    f"verify_m34_{suffix}",
                    f"verify_m34_{suffix}@example.invalid",
                    hash_password(VERIFY_PASSWORD),
                ),
            )
            conn.execute(
                "INSERT INTO spaces(id,slug,name,owner_id) VALUES(%s,%s,'Verify M3/M4',%s)",
                (space_id, f"verify-m34-{suffix}", user_id),
            )
            conn.execute(
                "INSERT INTO space_members(space_id,user_id,role) VALUES(%s,%s,'space_admin')",
                (space_id, user_id),
            )
            conn.execute(
                """
                INSERT INTO source_documents(id,space_id,source_type,locator,display_name)
                VALUES(%s,%s,'manual',%s,'Verify source')
                """,
                (source_id, space_id, f"verify://{suffix}"),
            )
            conn.execute(
                """
                INSERT INTO notes(
                    id,title,source_type,summary,content,tags,ingest_status,
                    space_id,created_by,source_document_id
                )
                VALUES(%s,%s,'manual','verify','verify content',%s,'done',%s,%s,%s)
                """,
                (
                    note_id,
                    f"Verify note {suffix}",
                    [f"verify-{suffix}"],
                    space_id,
                    user_id,
                    source_id,
                ),
            )

        with httpx.Client(base_url=WEB_URL, timeout=20.0) as client:
            _http_ok(
                client.post(
                    "/api/auth/login",
                    json={
                        "identifier": f"verify_m34_{suffix}",
                        "password": VERIFY_PASSWORD,
                        "client": "web",
                    },
                )
            )
            edited = _http_ok(
                client.patch(
                    f"/api/notes/{note_id}",
                    json={"title": f"Verify edited {suffix}"},
                ),
                202,
            )
            job_ids.append(uuid.UUID(edited["job_id"]))
            versions = _http_ok(client.get(f"/api/notes/{note_id}/versions"))["items"]
            assert versions and versions[0]["change_type"] == "edit"

            _http_ok(client.delete(f"/api/notes/{note_id}"), 204)
            trash = _http_ok(client.get("/api/notes/trash"))["items"]
            assert str(note_id) in {item["id"] for item in trash}
            restored = _http_ok(client.post(f"/api/notes/{note_id}/restore"), 202)
            job_ids.append(uuid.UUID(restored["job_id"]))

            subscription = _http_ok(
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
                space_id,
                note_id,
                "updated",
                f"Verify event {suffix}",
            )
            assert _http_ok(client.get("/api/notifications"))["unread"] == 1
            _http_ok(client.delete(f"/api/subscriptions/{subscription['id']}"), 204)

            connector = _http_ok(
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
            listed = _http_ok(
                client.get(f"/api/connectors?space_id={space_id}")
            )["items"]
            assert len(listed) == 1 and "credentials" not in listed[0]
            _http_ok(client.delete(f"/api/connectors/{connector['id']}"), 204)

            agent = _http_ok(
                client.post("/api/agent/runs", json={"space_id": str(space_id)}),
                202,
            )
            job_ids.append(uuid.UUID(agent["job_id"]))
            _wait_jobs(job_ids)
            _http_ok(client.delete(f"/api/notes/{note_id}"), 204)

        print("PASS: lifecycle / trash / notifications / connector crypto / agent queue")
        return 0
    finally:
        with _pool().connection() as conn:
            conn.execute("DELETE FROM audit_log WHERE user_id=%s", (user_id,))
            conn.execute(
                "DELETE FROM jobs WHERE id=ANY(%s) OR note_id=%s",
                (job_ids, note_id),
            )
            conn.execute("DELETE FROM notes WHERE id=%s", (note_id,))
            conn.execute("DELETE FROM source_documents WHERE id=%s", (source_id,))
            conn.execute("DELETE FROM spaces WHERE id=%s", (space_id,))
            conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    admin = subparsers.add_parser("admin", help="创建或重置管理员")
    admin.add_argument("--email", required=True)
    admin.add_argument("--password", required=True)
    admin.add_argument("--username")
    admin.add_argument("--name", help="显示名")
    admin.set_defaults(handler=command_admin)

    maintenance = subparsers.add_parser("maintenance", help="加入定时维护任务")
    maintenance.set_defaults(handler=command_maintenance)

    reindex = subparsers.add_parser("reindex", help="重建 Elasticsearch 内容")
    reindex.set_defaults(handler=command_reindex)

    seed_demo = subparsers.add_parser("seed-demo", help="写入幂等演示数据")
    seed_demo.set_defaults(handler=command_seed_demo)

    verify_core = subparsers.add_parser("verify-core", help="运行核心生产验收")
    verify_core.set_defaults(handler=command_verify_core)

    verify_advanced = subparsers.add_parser(
        "verify-advanced",
        help="运行生命周期与 M4 生产验收",
    )
    verify_advanced.set_defaults(handler=command_verify_advanced)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
