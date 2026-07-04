"""MCP server：把知识库检索/问答/笔记/图谱/主题页暴露为 Agent 可调用工具。

挂载方式见 main.py：用 Starlette Mount 把 mcp.streamable_http_app() 挂到 /mcp，
外层包一层 Bearer token 中间件（与登录用 JWT 分开的 MCP API token）。

工具（全部只读，无副作用，适合 LLM Agent 调用）：
  search       关键词/语义检索笔记
  ask          基于知识库的 RAG 问答
  get_note     取单篇笔记详情
  list_notes   笔记列表（分页 / 类型 / 标签）
  get_graph    知识图谱节点与边
  get_entity   实体详情 + 相关笔记
  list_wiki    主题页列表
  get_wiki     主题页详情（结构化 sections）

鉴权设计：SDK 自带的 TokenVerifier 走 OAuth 2.1（太重），这里改用轻量
Starlette 中间件在请求进入 streamable_http_app 前校验 Bearer token，
与 fuxi 既有的 JWT/Bearer 鉴权一致。stateless_http=True 匹配无状态设计。

M2 空间绑定：每个 MCP token 必须绑定一个空间（mcp_tokens.space_id）。
中间件校验通过后把 token 的 space_id 注入 ContextVar，各工具据此过滤 ——
等价于该空间的 viewer（只读该空间内容）。未绑定空间的异常 token 直接拒绝。
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from db import pool
from config import settings
from routers import mcp_admin

# 懒加载：mcp 可能未装（仅当需要 MCP 时才装），避免拖累整个后端启动。
_mcp = None

# 当前请求绑定的 MCP token 空间（None 仅是进入鉴权中间件前的默认值）。
# 中间件校验 token 后 set，工具读取 —— 把「该 token 能看哪些空间」透传给各工具，
# 不必给每个工具签名加参数（FastMCP 工具签名会暴露给 LLM，参数越少越好）。
_mcp_space_ids: contextvars.ContextVar[list[uuid.UUID] | None] = contextvars.ContextVar(
    "fuxi_mcp_space_ids", default=None
)


def _space_ids() -> list[uuid.UUID] | None:
    """当前请求的可见空间集合（供工具读）。None=全库可见。"""
    return _mcp_space_ids.get()


def _space_filter(alias: str = "notes") -> tuple[str, list]:
    """快捷：按当前 token 的空间生成 SQL 过滤片段。"""
    from services import spaces
    return spaces.space_filter_from(_space_ids(), alias=alias)


def _get_mcp():
    """懒构造 FastMCP 实例。首次调用时 import mcp 并注册全部工具。"""
    global _mcp
    if _mcp is not None:
        return _mcp
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    allowed_hosts = [h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()]
    mcp = FastMCP(
        "fuxi",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
    )

    _register_tools(mcp)
    _mcp = mcp
    return mcp


def get_app():
    """返回挂好 Bearer 中间件的 streamable_http ASGI app，供 main.py mount。"""
    mcp = _get_mcp()
    return _auth_wrapper(mcp.streamable_http_app())


def is_available() -> bool:
    """mcp SDK 是否可用（未安装时 main.py 跳过挂载，不影响其余接口）。"""
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


# ---------- Bearer 鉴权中间件 ----------

def _auth_wrapper(app):
    """把 streamable_http_app 包一层鉴权 ASGI 中间件。

    用裸 ASGI 包装而非 Starlette Middleware，避免与 streamable_http_app 的
    lifespan/session_manager 冲突：鉴权只看 headers，纯前置拦截。

    校验通过后把 token 绑定的 space_id 写进 ContextVar，供该请求内的各工具读取。
    （ASGI 在同一次调用栈内执行，ContextVar 在请求范围内可见。）
    """
    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        result = await asyncio.to_thread(mcp_admin.verify_token, token)
        if result is None:
            response = JSONResponse(
                {"error": {"code": "unauthorized", "message": "无效或已撤销的 MCP token"}},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        _token_id, space_id = result
        # token 必须绑定空间；未绑直接拒绝，不能退化为全库权限。
        if space_id is None:
            response = JSONResponse(
                {"error": {"code": "unauthorized", "message": "MCP token 未绑定空间"}},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        ctx_token = _mcp_space_ids.set([space_id])
        try:
            await app(scope, receive, send)
        finally:
            _mcp_space_ids.reset(ctx_token)

    return wrapped


# ---------- 工具实现 ----------

_TYPE_MAP = {"url": "link", "pdf": "pdf", "docx": "word", "xlsx": "excel",
             "image": "image", "manual": "link"}


def _register_tools(mcp) -> None:

    @mcp.tool()
    def search(q: str, mode: str = "hybrid", tags: list[str] | None = None,
               limit: int = 10) -> str:
        """在知识库里检索笔记。mode: hybrid（默认，关键词+语义融合）/ keyword / semantic。
        q 为空但 tags 非空时走「按标签浏览」（不打分、不调 LLM）。
        返回 JSON：[{id, title, type, summary, score}]。仅检索 token 绑定空间内的笔记。"""
        from routers import search as search_mod
        tags = tags or []
        limit = max(1, min(limit, 20))
        sf, sfp = _space_filter()
        sids = _space_ids()
        es_sids = [str(s) for s in sids] if sids is not None else None
        with pool.connection() as conn:
            # 标签浏览模式：q 空 + tags 非空，与 HTTP /search 一致，不调 LLM/不计费
            if not q and tags:
                rows = search_mod._tag_search(conn, tags, "all", sf, sfp)[:limit]
            else:
                vec = search_mod._try_embed(q) if mode in ("hybrid", "semantic") else None
                kw_rows = search_mod._keyword_search(
                    conn, q, tags, "all", sf, sfp, es_sids
                )
                sem_rows = (
                    search_mod._semantic_search(conn, vec, tags, "all", sf, sfp)
                    if vec is not None
                    else []
                )
                if mode == "semantic":
                    rows = sem_rows or kw_rows
                elif mode == "keyword":
                    rows = kw_rows
                else:
                    rows = search_mod._rrf_fuse(kw_rows, sem_rows) if sem_rows else kw_rows
                rows = rows[:limit]
        items = []
        for r in rows:
            items.append({
                "id": str(r[0]), "title": r[2], "type": _TYPE_MAP.get(r[1], "link"),
                "summary": r[6], "score": round(float(r[8]), 4) if len(r) > 8 and r[8] is not None else None,
            })
        return json.dumps({"items": items}, ensure_ascii=False)

    @mcp.tool()
    def ask(question: str) -> str:
        """基于知识库提问，返回带来源依据的回答（RAG）。
        返回 JSON：{answer, sources:[{id,title,type}], generated}。
        缺 API_KEY 时 generated=false，仅返回检索到的来源。仅检索 token 绑定空间。"""
        from routers import qa as qa_mod
        from services import llm
        rows, qa_pairs = qa_mod._retrieve(question, _space_ids())
        sources = [{"id": str(r[0]), "title": r[2], "type": _TYPE_MAP.get(r[1], "link")}
                   for r in rows]
        if not sources:
            return json.dumps({
                "answer": "知识库中没有足够来源回答这个问题。",
                "sources": [],
                "generated": False,
            }, ensure_ascii=False)
        context = qa_mod._build_context(rows, qa_pairs)
        try:
            answer = llm.answer(question, context, None)
            generated = True
        except Exception:  # noqa: BLE001 — 缺密钥降级
            generated = False
            answer = "（未配置 API_KEY 或调用失败，无法生成回答。）"
        return json.dumps({"answer": answer, "sources": sources, "generated": generated},
                          ensure_ascii=False)

    @mcp.tool()
    def get_note(note_id: str) -> str:
        """取单篇笔记详情：标题/摘要/要点/标签/实体/正文。note_id 为 UUID 字符串。
        返回 JSON；不存在或不在 token 绑定空间内返回 {error}。"""
        try:
            nid = uuid.UUID(note_id)
        except ValueError:
            return json.dumps({"error": "note_id 不是合法 UUID"}, ensure_ascii=False)
        sf, sfp = _space_filter()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT id, source_type, title, COALESCE(source,''), COALESCE(summary,''), "
                f"key_points, tags, COALESCE(content,'') FROM notes WHERE id = %s AND ingest_status='done' AND deleted_at IS NULL{sf}",
                [nid, *sfp],
            ).fetchone()
        if row is None:
            return json.dumps({"error": "笔记不存在"}, ensure_ascii=False)
        return json.dumps({
            "id": str(row[0]), "type": _TYPE_MAP.get(row[1], "link"), "title": row[2],
            "source": row[3], "summary": row[4], "key_points": row[5] or [],
            "tags": row[6] or [], "content": row[7],
        }, ensure_ascii=False)

    @mcp.tool()
    def list_notes(q: str = "", type: str = "", tag: str = "",
                   page: int = 1, size: int = 20) -> str:
        """笔记列表（分页）。q 关键词、type(link/pdf/word/excel/image)、tag 单标签过滤。
        返回 JSON：{items, total, page, size}。仅列 token 绑定空间内的笔记。"""
        where = ["ingest_status = 'done'", "deleted_at IS NULL"]
        params: list = []
        if type:
            reverse = {v: k for k, v in _TYPE_MAP.items()}
            st = reverse.get(type)
            if st:
                where.append("source_type = %s"); params.append(st)
        if tag:
            where.append("%s = ANY(tags)"); params.append(tag)
        if q.strip():
            where.append("(title ILIKE %s OR COALESCE(summary,'') ILIKE %s)")
            like = f"%{q.strip()}%"
            params.extend([like, like])
        sf, sfp = _space_filter()
        clause = " AND ".join(where) + sf
        params_with_space = [*params, *sfp]
        page = max(1, page); size = max(1, min(size, 100))
        offset = (page - 1) * size
        with pool.connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM notes WHERE {clause}", params_with_space).fetchone()[0]
            rows = conn.execute(
                f"SELECT id, source_type, title, COALESCE(source,''), COALESCE(summary,'') "
                f"FROM notes WHERE {clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                [*params_with_space, size, offset],
            ).fetchall()
        items = [{"id": str(r[0]), "type": _TYPE_MAP.get(r[1], "link"), "title": r[2],
                  "source": r[3], "summary": r[4]} for r in rows]
        return json.dumps({"items": items, "total": total, "page": page, "size": size},
                          ensure_ascii=False)

    @mcp.tool()
    def get_graph(filter: str = "all") -> str:
        """知识图谱：实体节点 + 共现边。filter: all/concept/product/company。
        返回 JSON：{nodes:[{id,name,cat,count}], edges:[[id,id],...]}。
        节点提及数与共现边都限定在 token 绑定空间内现算（M2 起不用全局视图）。"""
        _cats = {"concept", "product", "company"}
        # 子查询里 notes 起别名 ne_space，故空间片段按该别名生成。
        ne_sf, ne_sfp = _space_filter(alias="ne_space")
        with pool.connection() as conn:
            if filter in _cats:
                node_rows = conn.execute(
                    f"""
                    SELECT e.id, e.name, e.type, COALESCE(cnt.note_count, 0)
                    FROM entities e
                    LEFT JOIN (
                        SELECT ne.entity_id, COUNT(*)::int AS note_count
                        FROM note_entities ne
                        JOIN notes ne_space ON ne_space.id = ne.note_id
                        WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                        GROUP BY ne.entity_id
                    ) cnt ON cnt.entity_id = e.id
                    WHERE e.type = %s AND cnt.note_count IS NOT NULL
                    ORDER BY COALESCE(cnt.note_count, 0) DESC
                    """,
                    [*ne_sfp, filter],
                ).fetchall()
            else:
                node_rows = conn.execute(
                    f"""
                    SELECT e.id, e.name, e.type, COALESCE(cnt.note_count, 0)
                    FROM entities e
                    LEFT JOIN (
                        SELECT ne.entity_id, COUNT(*)::int AS note_count
                        FROM note_entities ne
                        JOIN notes ne_space ON ne_space.id = ne.note_id
                        WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                        GROUP BY ne.entity_id
                    ) cnt ON cnt.entity_id = e.id
                    WHERE cnt.note_count IS NOT NULL
                    ORDER BY COALESCE(cnt.note_count, 0) DESC
                    """,
                    ne_sfp,
                ).fetchall()
            edge_rows = conn.execute(
                f"""
                SELECT a.entity_id AS from_id, b.entity_id AS to_id
                FROM note_entities a
                JOIN note_entities b
                  ON a.note_id = b.note_id AND a.entity_id < b.entity_id
                JOIN notes ne_space ON ne_space.id = a.note_id
                WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                GROUP BY a.entity_id, b.entity_id
                """,
                ne_sfp,
            ).fetchall()
        node_ids = {r[0] for r in node_rows}
        nodes = [{"id": str(r[0]), "name": r[1],
                  "cat": r[2] if r[2] in _cats else "concept", "count": r[3]}
                 for r in node_rows]
        edges = [[str(a), str(b)] for a, b in edge_rows if a in node_ids and b in node_ids]
        return json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)

    @mcp.tool()
    def get_entity(entity_id: str) -> str:
        """实体详情 + 相关笔记。entity_id 为 UUID 字符串。
        返回 JSON：{id,name,cat,count,aliases,notes:[{id,title,type,date}]}。
        提及数与相关笔记都限定在 token 绑定空间内。"""
        try:
            eid = uuid.UUID(entity_id)
        except ValueError:
            return json.dumps({"error": "entity_id 不是合法 UUID"}, ensure_ascii=False)
        _cats = {"concept", "product", "company"}
        ne_sf, ne_sfp = _space_filter(alias="ne_space")
        n_sf, n_sfp = _space_filter(alias="n")
        with pool.connection() as conn:
            row = conn.execute(
                f"""
                SELECT e.id, e.name, e.type, e.aliases, COALESCE(cnt.note_count, 0)
                FROM entities e
                LEFT JOIN (
                    SELECT ne.entity_id, COUNT(*)::int AS note_count
                    FROM note_entities ne
                    JOIN notes ne_space ON ne_space.id = ne.note_id
                    WHERE ne_space.ingest_status = 'done' AND ne_space.deleted_at IS NULL{ne_sf}
                    GROUP BY ne.entity_id
                ) cnt ON cnt.entity_id = e.id
                WHERE e.id = %s AND cnt.note_count IS NOT NULL
                """,
                [*ne_sfp, eid],
            ).fetchone()
            if row is None:
                return json.dumps({"error": "实体不存在"}, ensure_ascii=False)
            note_rows = conn.execute(
                f"""
                SELECT n.id, n.title, n.source_type, n.published_date
                FROM note_entities ne JOIN notes n ON n.id = ne.note_id
                WHERE ne.entity_id = %s AND n.ingest_status = 'done' AND n.deleted_at IS NULL{n_sf}
                ORDER BY n.published_date DESC NULLS LAST, n.created_at DESC
                """,
                [eid, *n_sfp],
            ).fetchall()
        return json.dumps({
            "id": str(row[0]), "name": row[1],
            "cat": row[2] if row[2] in _cats else "concept", "count": row[4],
            "aliases": row[3] or [],
            "notes": [{"id": str(n[0]), "title": n[1],
                       "type": _TYPE_MAP.get(n[2], "link"),
                       "date": n[3].isoformat() if n[3] else None} for n in note_rows],
        }, ensure_ascii=False)

    @mcp.tool()
    def list_wiki() -> str:
        """主题页列表。返回 JSON：{items:[{slug,title,updated,source_count}]}。
        仅列 token 绑定空间内的主题页。只要还有至少 1 条有效来源就展示该 wiki。"""
        sf, sfp = _space_filter(alias="wiki_pages")
        with pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT slug, title, COALESCE(compiled_at, updated_at),
                       COALESCE(array_length(source_note_ids, 1), 0)
                FROM wiki_pages WHERE COALESCE(array_length(
                    (SELECT array_agg(sid.note_id) FROM unnest(source_note_ids) AS sid(note_id)
                     JOIN notes sn ON sn.id=sid.note_id
                     WHERE sn.deleted_at IS NULL AND sn.ingest_status='done'), 1), 0) > 0
                {sf}
                ORDER BY COALESCE(compiled_at, updated_at) DESC
                """,
                sfp,
            ).fetchall()
        items = [{"slug": r[0], "title": r[1],
                  "updated": r[2].date().isoformat() if r[2] else None,
                  "source_count": r[3]} for r in rows]
        return json.dumps({"items": items}, ensure_ascii=False)

    @mcp.tool()
    def get_wiki(slug: str) -> str:
        """主题页详情：结构化 sections + 引用来源 + 观点矛盾。返回 JSON；不存在返回 {error}。
        不在 token 绑定空间内的主题页按不存在处理（不泄露存在性）。"""
        wiki_sf, wiki_sfp = _space_filter(alias="wiki_pages")
        with pool.connection() as conn:
            row = conn.execute(
                f"""
                SELECT slug, title, COALESCE(compiled_at, updated_at),
                       source_note_ids, sections, conflict FROM wiki_pages
                WHERE slug = %s AND COALESCE(array_length(
                    (SELECT array_agg(sid.note_id) FROM unnest(source_note_ids) AS sid(note_id)
                     JOIN notes sn ON sn.id=sid.note_id
                     WHERE sn.deleted_at IS NULL AND sn.ingest_status='done'), 1), 0) > 0
                {wiki_sf}
                """,
                [slug, *wiki_sfp],
            ).fetchone()
            if row is None:
                return json.dumps({"error": "主题页不存在"}, ensure_ascii=False)
            slug_, title, updated, source_ids, sections, conflict = row
            sources = []
            if source_ids:
                note_sf, note_sfp = _space_filter(alias="notes")
                note_rows = conn.execute(
                    f"SELECT id, title, source_type FROM notes "
                    f"WHERE id = ANY(%s) AND ingest_status='done' AND deleted_at IS NULL{note_sf}",
                    [source_ids, *note_sfp],
                ).fetchall()
                sources = [{"id": str(n[0]), "title": n[1],
                            "type": _TYPE_MAP.get(n[2], "link")} for n in note_rows]
        return json.dumps({
            "slug": slug_, "title": title,
            "updated": updated.date().isoformat() if updated else None,
            "sources": sources, "sections": sections or [], "conflict": conflict,
        }, ensure_ascii=False)
