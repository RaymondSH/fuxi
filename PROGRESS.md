# fuxi · 实现进度

> 单一进度真相。**每次改完代码都要更新本文件**：改对应条目状态，并在底部「更新日志」追加一行。
> 图例：✅ 已完成　🚧 进行中 / 部分完成　⬜ 未开始

**最后更新：2026-07-02**

## 总览

| 模块 | 进度 |
|------|------|
| 数据库 Schema | ✅ SQL 01~33 已部署到生产并通过真库验收 |
| 后端 · 基础设施 | ✅ 完成（AI 接入已重构为 providers 策略层 + 智谱 GLM） |
| 后端 · 入库 | ✅ 完成（分块 + 原始文件落盘 + ES 同步索引；M2 带空间归属 + editor 角色校验） |
| 后端 · 检索 | ✅ 完成（ES+ik 中文分词关键词路 + chunk 级语义检索；M2 全路按空间 ACL 过滤） |
| 后端 · 笔记详情 / 列表 | ✅ 完成（M1 增 GET /notes 列表分页；M2 详情/列表按空间过滤 + 删除改空间角色校验） |
| 后端 · 知识图谱 | ✅ 完成（M2 丢全局视图改 JOIN + 空间过滤） |
| 后端 · 问答 RAG | ✅ 完成（同步 + SSE 流式；M1 增 Q&A 回灌 + 角色化风格；M2 _retrieve 收 space_ids 按空间过滤） |
| 后端 · Wiki | ✅ 完成（读 + 编译 worker；M1 编译记账；M2 列表/详情/compile 按空间校验） |
| 后端 · MCP Server | ✅ 完成（M1：8 个只读工具 + Bearer API token；M2 token 绑空间 + 各工具按空间过滤） |
| 后端 · 空间权限 | ✅ 完成（M2：spaces 服务 + ACL 注入 + 空间 CRUD/成员 API） |
| 前端 · 框架 | ✅ 完成（Next.js + Tailwind + house style + 导航） |
| 前端 · 全部页面 | ✅ 完成（M1 增笔记列表页 / 标签治理 / MCP 管理 / 风格切换 / 趋势看板；M2 增空间切换 / 空间管理页 / 既有页带 space） |
| 后端 · 鉴权/配额/管理员 | ✅ 完成（Web httpOnly Cookie、移动端 Bearer、access/refresh 类型隔离、改密失效、锁定自动解除；真库验收通过） |
| 前端 · 登录 + 管理后台 | ✅ 代码完成（登录页 + 路由守卫 + /admin 入库·用户·用量·标签·MCP，build 通过） |
| 数据迁移 | ✅ M0~M4 SQL 01~33 已部署；M3/M4 单事务迁移及 12 张核心表验收通过 |
| 部署（linux-server） | ✅ v0.8.0 已上线；backend/frontend/worker、ES8+ik、备份与 maintenance timer 正常运行 |
| M3 · 生命周期与治理 | ✅ 已部署（版本/软删除/刷新、五类巡检、治理页面），生产冒烟通过 |
| M3 · 深度问答 | ✅ 已部署（rerank、PII 掩码、三路 Agentic RAG、引用校验） |
| M4 · 企业接入与分发 | 🚧 框架已部署并通过生产冒烟；四个平台真实凭据联调待外部凭据 |

里程碑完成度：**M0~M3 已部署验收；M4 核心系统已部署验收，真实平台连接器待凭据联调。**
> M2 已实现笔记 / wiki / MCP token 的强制空间归属；检索、RAG、图谱、标签、状态统计和 MCP 均按 ACL 过滤，写操作按 editor/space_admin 角色控制。

---

## 数据库 Schema（`sql/`）

- [x] `01_extensions` 扩展（uuid / vector / pg_trgm）
- [x] `02_notes` 笔记主表 + HNSW + 全文索引（含 source / published_date / related_note_ids）
- [x] `03_graph` entities / relations / note_entities + 图谱视图（提及数 / 共现边）
- [x] `04_wiki` wiki_pages（含 sections / conflict jsonb）+ note_wiki
- [x] `05_history` search_history（含 hybrid）/ qa_history
- [x] `06_jobs` 任务队列（含 stage / progress / note_id）+ pg_notify
- [x] `14_notes_list` notes 加 authority 占位列 + views_count 浏览计数 — M1
- [x] `15_tags` 受控词表（name PK / aliases / description / status / merged_into）— M1
- [x] `16_generated_qa` 文档→Q&A 沉淀表（note_id FK CASCADE + question + answer + embedding vector(1536) HNSW）— M1
- [x] `17_jobs_qa_gen` jobs.job_type 加 'qa_gen'（ALTER DROP/ADD CHECK）— M1
- [x] `19_mcp_tokens` MCP API token（name / bcrypt token_hash / prefix / is_active / last_used_at）— M1
- [x] `18_spaces` spaces + space_members（viewer/editor/space_admin + default 种子）— M2
- [x] `20_notes_space` notes 加 space_id + created_by + 回填 default — M2
- [x] `21_wiki_space` wiki_pages 加 space_id + 回填 default — M2
- [x] `22_mcp_token_space` mcp_tokens 加 space_id + 回填 default — M2
- [x] `23_default_membership` 现有用户全加为 default 空间 editor（向后兼容）— M2
- [x] `24_space_hardening` 全量回填后将 notes/wiki_pages/mcp_tokens.space_id 收紧为 NOT NULL；内容表删除空间 RESTRICT、MCP token CASCADE — M2
- [x] `25_m3_lifecycle` 来源身份、笔记版本、软删除与刷新状态 — M3
- [x] `26_m3_governance` 治理运行记录与幂等待办 — M3
- [x] `27_m3_jobs` note_reindex/source_refresh/governance_scan 持久化任务 — M3
- [x] `28_m3_qa_trace` 深度问答 plan/source/verification 轨迹 — M3
- [x] `29_m4_connectors` 连接器账号、加密凭据、远端对象映射 — M4
- [x] `30_m4_distribution` 变更事件、订阅、站内通知 — M4
- [x] `31_m4_feedback` 问答赞踩反馈 — M4
- [x] `32_m4_agent` Agent 运行与审批提案 — M4
- [x] `33_m4_jobs` connector_sync/agent_plan/proposal_execute — M4
- [x] 在 linux-server 真库执行 SQL 01~33 并验证（PG18 + pgvector 0.8.3，M3/M4 12 张核心表与权限正确）

## 后端 · 基础设施（`backend/`）

- [x] `config.py` 环境配置（AI 服务收敛成一套：`API_KEY`/`AI_BASE_URL`/`CHAT_MODEL`/`VISION_MODEL`/`EMBED_MODEL`）
- [x] `db.py` psycopg 连接池 + pgvector 注册
- [x] `main.py` FastAPI 入口（挂载全部业务路由 /api、CORS、结构化日志 + 全局异常兜底中间件）
- [x] `requirements.txt`
- [x] **AI 接入策略层** `services/providers/`：`base.py` 抽象 LLMProvider/EmbeddingProvider + 共享数据模型；`glm.py` 智谱实现（glm-5.2 对话 + glm-4.6v 视觉 + embedding-3 向量）；`__init__.py` 工厂。`services/llm.py`、`services/embedder.py` 改为薄门面委托。配置即策略，换兼容 OpenAI 协议的 provider 只改配置
- [x] **统一结构化日志**：`services/logging.py`（`setup_logging` 配 JSON 单行 formatter，`fuxi` 根 logger + uvicorn/access 复用同一 handler，`get_logger` 取子 logger；`LOG_LEVEL`/`LOG_FORMAT=text|json` 可控）。es/compile/ingest 统一改用 `get_logger`，ingest 补 start/done/failed 关键埋点
- [x] **全局异常处理**：`services/middleware.py` `CatchErrorsMiddleware`（`BaseHTTPMiddleware`）兜底未捕获异常 → 结构化记录（path/method/user_id/ip）→ 返回 500 通用文案 `{"detail":"服务器内部错误"}`，不泄露堆栈；`get_current_user` 把 user 写 `request.state.user` 供中间件/日志取 user_id

## 后端 · 入库（ingest）

- [x] `services/fetcher.py` 抓取：URL / PDF / docx / xlsx / 图片
- [x] `services/llm.py`（经 providers）提炼：摘要 / 要点 / 标签 / 实体（GLM JSON 结构化输出）
- [x] `services/embedder.py`（经 providers）向量化
- [x] `workers/ingest_worker.py` 编排：抓取→提炼→向量化→写 notes + entities
- [x] `routers/ingest.py` `POST /ingest/url`、`POST /ingest/file`、`GET /ingest/{id}`
- [x] **写 jobs 表**：worker 各步骤更新 stage / progress（fetch→extract→refine→embedding→store→done）
- [x] `GET /ingest/jobs` 入库队列列表接口（含 DB→API 状态/类型映射）
- [x] 路由统一挂 `/api` 前缀（main.py）
- [x] **真库端到端验证**：URL 摄取跑通 fetch→refine(glm-5.2 结构化)→embedding-3→store，状态达 `done`，标题/摘要/标签均由 GLM 生成
- [x] **分块（chunking）**：`services/chunker.py` 用 langchain `RecursiveCharacterTextSplitter`（中文友好分隔符 `。！？；` + `\n`），`chunk_size=800` / `overlap=120` / `min=80`，长文档逐块向量化写 `note_chunks` 表；`notes.embedding` 仍留作文档级回退
- [x] 原始文件落盘：`services/storage.py` 抽象 `LocalStore`/`R2Store` + 工厂，worker 摄取时上传 raw_bytes 并写 `raw_path`；默认 `local` 兜底零依赖，配 R2 凭据即切云
- [x] **入库 token 入账**：`routers/ingest.py` 把 `actor_id`、`space_id` 写入 jobs payload；独立 `job_runner` 消费后由 `ingest_worker.run(...)` 在 fetch→refine→embed 段收集并写入 `token_usage`。任务参数和上传原文件在返回 202 前持久化，进程重启不丢任务

## 后端 · 检索（search）

- [x] `routers/search.py` `POST /search`（关键词 / 语义 / hybrid）
- [x] 关键词检索（Postgres ILIKE + 命中片段高亮 + 打分）
- [x] RRF 混合融合（hybrid）；无 API_KEY 时自动降级关键词
- [x] 写入 search_history
- [x] `GET /tags` 标签云
- [x] `GET /search/history` 搜索历史
- [x] **语义检索真验证**（embedding-3 向量；`%s::vector` 显式转型修通 pgvector 类型适配，`mode` 保持 `semantic` 不降级）
- [x] **语义检索切 chunk 级**：`_semantic_search` 改查 `note_chunks`，`GROUP BY c.note_id` + `MAX(1-(c.embedding<=>%s::vector))` 取每篇最优块，聚合回笔记；`_semantic_search_doc` 留作文档级回退
- [x] **关键词路升级到 Elasticsearch + ik 中文分词**：`services/es.py` 单例 httpx 客户端，单索引 `notes_v1`（ik_max_word 索引 / ik_smart 检索）；`_keyword_search` 走 ES→回查 PG 保序保分→ES 不可达自动回退 ILIKE；ingest/notes 增删同步索引
- [ ] `GET /search/suggestions` 联想

## 后端 · 问答（RAG）

- [x] `routers/qa.py` `POST /qa`：检索来源 + LLM 生成；无密钥时降级（返回来源 + 提示）
- [x] 检索：有 API_KEY 走语义，否则中文 2-gram + 英文词兜底召回
- [x] `services/llm.py`（经 providers）`answer()` RAG 生成函数
- [x] 写入 qa_history、`GET /qa/history`
- [x] **真验证 GLM 生成**（glm-5.2 thinking on，`generated:true`，~8s 延迟返回连贯回答）
- [x] **SSE 流式**：`POST /qa/stream` 用 `sse-starlette EventSourceResponse`；`glm.answer_stream` 走 `AsyncOpenAI` + `stream=True` + `thinking on`，事件序 `sources`→`token`→`done`；同步 `POST /qa` 保留兼容。`qa_stream` 内 `_retrieve` 经 `asyncio.to_thread` 跑（含同步 embedding 调用，不阻塞 event loop）；降级时文案也作 `token` 推送
- [x] **前端接 SSE**：`lib/sse.ts`（fetch POST + ReadableStream 手动解析 SSE 事件，`streamQa` 驱动 `onSources`/`onToken`/`onDone`），`app/qa/page.tsx` 改走 `/qa/stream` 逐字渲染 + 「思考中…」占位
- [x] **Q&A 回灌检索**（M1）：`_retrieve` 返回 `(notes, qa_pairs)`，从 `generated_qa` 按 question 向量取 top-2，`_build_context` 前置「已沉淀问答」让模型复用同义问题的既有答案
- [x] **角色化输出风格**（M1）：`QaStyle = default/executive/technical/eli5`，`build_qa_system(style)` 组合 QA_SYSTEM + 风格提示；`qa`/`qa_stream` 入参 `style`，非法值回退 default；前端问答页分段控件 + 非 default 显示风格徽标

## 后端 · 标签治理（M1）

- [x] `sql/15_tags.sql` 受控词表 `tags`（name PK / aliases / description / status / merged_into）
- [x] `routers/tags.py`：`GET /tags`（标签云，别名归并到规范名）、`GET /tags/vocab`（admin）、`POST /tags`（新建/补别名）、`PATCH /tags/{name}`（改描述/状态）、`POST /tags/merge`（归并：`array_replace` 物理回写 + 同步 ES + 词表标 merged）
- [x] `list_tags` 从 search.py 迁到 tags.py，main.py 挂载
- [x] 前端 `app/admin/tags` 受控词表 + 标签云 + 归并（点击标签云填入归并「旧标签」）

## 后端 · MCP Server（M1 + M2 空间绑定）

- [x] `backend/mcp_server.py`：FastMCP 实例（`stateless_http=True, json_response=True`）+ 8 个只读工具（search/ask/get_note/list_notes/get_graph/get_entity/list_wiki/get_wiki，全返 JSON 字符串）+ `_auth_wrapper` 裸 ASGI Bearer 中间件 + `is_available()`（mcp 未装则跳过）。**M2**：`verify_token` 返回 `(token_id, space_id)`；加 `_mcp_space_ids` ContextVar（`_auth_wrapper` 设）+ `_space_filter()` helper，8 工具按 token 绑定空间过滤；图谱工具用内联 JOIN（同 graph.py）
- [x] `routers/mcp_admin.py`：token CRUD `/mcp-admin/tokens`（admin）+ `verify_token()` 线性扫 active token 做 bcrypt.checkpw + 更新 last_used_at。**M2**：`McpTokenOut` 带 space_id/space_name；`CreateTokenRequest`/`UpdateTokenRequest` 带 space_id（缺省 default）；`list_tokens` JOIN spaces
- [x] `sql/19_mcp_tokens.sql` mcp_tokens 表（bcrypt token_hash + prefix + is_active + last_used_at）+ `21_mcp_token_space.sql` 加 space_id（M2）
- [x] `main.py`：`import mcp_server`，`is_available()` 时构造 FastMCP + `streamable_http_app` + lifespan 内 `session_manager.run()`，`app.mount("/mcp", _mcp_app)`（不挂全局 _auth，自行 Bearer 校验）；`mcp_admin.router` 挂 `/api` 下 require_admin
- [x] 前端 `app/admin/mcp` token 列表 + 创建（一次性明文弹窗 + 复制）+ 启停/删除。**M2**：创建表单加空间选择；token 列表项内联空间下拉（变更即 PATCH）
- [x] `docs/mcp.md` 工具一览 + Claude Desktop 接入配置 + 鉴权设计

## 后端 · 知识图谱（graph）

- [x] `routers/graph.py` `GET /graph`（按类别筛选）— M2 改应用层 JOIN + space 过滤（原查 `entity_cooccurrence` / `entity_note_counts` 全局视图，视图无法接受运行时 space 参数）
- [x] `GET /graph/entities/{id}` 实体详情 + 相关笔记
- [ ] （可选）typed relations 提取写入 relations 表

## 后端 · 空间（Spaces）+ 权限感知（M2，`docs/spaces-design.md`）

双层角色模型：系统级 `users.role`（member/admin）+ 空间级 `space_members.role`（viewer/editor/space_admin），正交。sysadmin 对全部空间天然是 space_admin（不写 membership 行）。ACL 注入模式：每请求 `visible_space_ids(conn, user)` 一次拿集合（sysadmin 返回 None=全可见），透传给所有读路径的 `space_filter_from(sids, alias)` 生成 SQL 片段。

- [x] `services/spaces.py`：`visible_space_ids` / `visible_space_strs`（ES 用）/ `space_filter_from(sids, alias)`（收 space_ids 不收 user，admin 决策已编码进 None，故 MCP 可复用）/ `role_in_space` / `assert_space_role` / `assert_note_role`
- [x] **写路径**：`ingest` POST 注入 CurrentUser + 校验目标空间 editor + 透传 space_id/actor_id；`DELETE /notes/{id}`、`generate-qa` 改 `assert_note_role`（空间角色，原 require_admin）；`wiki compile` 校验来源同空间 + space_admin
- [x] **读路径**：search（PG + ES 双侧）/ qa `_retrieve(question, space_ids)`（收 space_ids 不收 user，MCP 复用）/ notes 详情·列表 全部按空间过滤
- [x] **图谱丢视图改 JOIN**：`get_graph` / `get_entity` 用 `note_entities ne JOIN notes n` + `space_filter_from(sids, alias="n")`，子查询 alias="n"、关联笔记 alias="notes"；旧视图留作向后兼容
- [x] **Wiki 权限感知**：`compile_status` / `list_wiki` / `get_wiki` 加 space 过滤（404 无权）；`_resolve_compile_space()` 校验来源同空间 + space_admin；`compile_worker` 取 wiki 行 space_id 只取同空间笔记（防御性 `AND space_id = %s`）
- [x] **MCP 绑空间**：`mcp_tokens.space_id`（21）；`verify_token` 返回 `(token_id, space_id)`；`mcp_server.py` 加 `_mcp_space_ids` ContextVar（`_auth_wrapper` 设）+ `_space_filter()` helper，8 个工具按 token 空间过滤；`ask` 复用 `qa_mod._retrieve(question, _space_ids())`；图谱工具用内联 JOIN
- [x] `routers/spaces.py`（新）：空间 CRUD + 成员管理 + 用户搜索（`GET /spaces/{id}/members/search`，space_admin 用，因 `/auth/users` 是 sysadmin only）；空间管理员不能改/移除自己；default 不可删；全写操作审计
- [x] `main.py` 挂 `spaces.router` `/api` 下登录依赖

## 后端 · 笔记 / Wiki

- [x] `routers/notes.py` `GET /notes`（列表分页：类型/标签/关键词过滤，仅 done）、`GET /notes/{id}`（含实体/要点/正文分段）、`DELETE /notes/{id}`。**M2**：列表/详情按空间过滤（无权 404）；DELETE 从 require_admin 改 `assert_note_role(space_admin)`
- [x] `POST /notes/{id}/generate-qa`（触发文档→Q&A 生成）+ `GET /notes/{id}/qa`（已生成问答对）— M1。**M2**：generate-qa 从 require_admin 改 editor 空间角色
- [x] `routers/wiki.py` `GET /wiki`、`GET /wiki/{slug}`（结构化 sections + conflict + 来源解析）。**M2**：列表/详情按空间过滤
- [x] `POST /wiki/compile` 创建持久化 job + `GET /wiki/{slug}/status` 读编译任务进度。**M2**：`_resolve_compile_space()` 校验来源同空间 + space_admin
- [x] `workers/compile_worker.py` 多笔记 → LLM 综合 → 写 wiki_pages（结构化 sections / conflict / summary / content / embedding / compiled_at）；`compile_wiki` 用 `response_format=json` + `reasoning_effort=max`。**M2**：`compile_sync`/`enqueue_compile` 收 space_id；`_fetch_sources` 只取同空间笔记
- [x] **compile 记账**：`compile_worker.run(slug, *, actor_id=None)` 包 `usage.collect()` + `quota.record_usage(actor_id, "compile", u)`，wiki.py 透传 `actor_id=admin.id` — M1

## 后端 · 鉴权 / 配额 / 管理员（`docs/auth-design.md`）

分阶段：**1 登录+全路由锁+admin 网关** · 2 配额 429 · 3 历史隔离 · 4 前端登录 · 5 admin 界面。

**阶段 1（已部署并通过真库验证）**
- [x] `sql/08_auth.sql`：`users`（email/bcrypt/role/daily_token_limit/is_active）+ `token_usage` 账本；`00_init.sql` 补挂 07/08
- [x] `services/auth.py`：bcrypt 哈希 + JWT(HS256) 签发/解码 + `get_current_user` / `require_admin` 依赖
- [x] `routers/auth.py`：`POST /auth/login`、`GET /auth/me`、`GET/POST /auth/users`、`PATCH /auth/users/{id}`（admin）
- [x] `main.py`：业务路由统一挂登录依赖；ingest 整组 `require_admin`；notes DELETE、wiki compile 单路由 `require_admin`
- [x] `config.py` + `.env.example`：`JWT_SECRET`/`JWT_EXPIRE_HOURS`/`DEFAULT_DAILY_TOKEN_LIMIT`/`USAGE_TZ`
- [x] `requirements.txt`：`pyjwt` + `bcrypt` + `email-validator`（弃 passlib：1.7.4 与 bcrypt>=4.1 不兼容自检抛 ValueError）
- [x] `scripts/create_admin.py`：引导首个管理员（幂等 upsert）
- [x] 契约 `docs/api-contract.md` 新增「8. 鉴权 Auth」+ 全局鉴权约定 + 权限标注
- [x] 真库验证：SQL 08~24、管理员登录、Cookie/Bearer 客户端、401/403、access/refresh 类型隔离均通过

**阶段 2（token 配额 429，代码完成）**
- [x] `services/usage.py`：ContextVar 累加器（`collect()` 上下文 + `record_call()`），与 provider 解耦
- [x] `services/providers/glm.py`：analyze/answer/answer_stream/describe_image/compile_wiki/embed 六处调用后 `usage.record_call`；流式加 `stream_options={"include_usage":true}` 取末尾 usage
- [x] `services/quota.py`：`today()`(按 USAGE_TZ) / `used_today` / `check_quota`(超额 429) / `record_usage`
- [x] `routers/qa.py`、`routers/search.py`：注入当前用户，调用前 `check_quota`、调用后 `record_usage`（qa/qa_stream 计 qa；search 仅 semantic/hybrid 计费）

**阶段 3（历史 user_id 隔离，代码完成）**
- [x] `sql/09_history_user.sql`：给 search_history/qa_history 加 `user_id`（FK + 索引，幂等迁移），挂进 00_init
- [x] `_save_history` 写入 user_id；`/search/history`、`/qa/history` 默认按当前用户过滤，admin `?scope=all` 看全部

**阶段 4（前端登录 + 守卫，已部署）**
- [x] `lib/api.ts`：Web access/refresh 使用 httpOnly Cookie，401 单飞刷新；429 归类 `rate_limited`；不向 JavaScript 暴露 Web token
- [x] `components/AuthProvider.tsx`（Cookie 会话引导 + 未登录守卫 + login/logout）+ `AppShell.tsx`（登录页全屏、其余套侧栏）
- [x] `app/login/page.tsx` 登录页；`layout.tsx` 包 AuthProvider/AppShell；`Sidebar` 按角色显示导航 + 用户 + 登出

**阶段 5（管理后台，代码完成）**
- [x] `app/admin/layout.tsx` 管理员守卫；入库页迁到 `app/admin/ingest`（删旧 `app/ingest`，根路由改跳 /search）
- [x] `app/admin/users` 用户管理（建号/改角色/改密码/停用）；`app/admin/usage` 用量看板
- [x] 后端 `GET /auth/usage`（admin）今日各用户用量 + 额度 + 组织趋势 + ≥80% 告警（M1 升级 `?days=1..90`）
- [x] 前端 `npm run build` 通过（13 路由，含 /admin/*）；后端 `py_compile` 全过
- [x] **linux-server 真库验证 + 上线**（2026-06-28）：灌 08/09、装依赖、create_admin、login 取 token、unauth 401、ingest admin、authed search/me/usage 200、前端 /login·/admin 200、错误密码 401。passlib 弃用改 bcrypt 直连
**阶段 6（账号安全，M0 步骤4，代码完成）**
- [x] `sql/12_account_security.sql`：users 加 `failed_login_attempts`/`locked_until`/`last_login_at`/`password_changed_at`（幂等迁移，挂进 00_init）
- [x] `services/auth.py` `validate_password(pw)`：≥8 位 + 含字母 + 含数字（建号/改密/自助改密复用，替代旧 `min_length=6`）
- [x] **登录失败锁定**：`POST /auth/login` 失败递增 `failed_login_attempts`，达 `LOGIN_MAX_ATTEMPTS`(5) 置 `locked_until = NOW()+15min`（423 锁定）；成功清零 + 记 `last_login_at`。同一事务内完成避免并发
- [x] **自助改密** `POST /auth/change-password`：验旧密码 → `validate_password` 新密码 → 更新 + `password_changed_at` → 审计；前端 `/settings` 页 + Sidebar「修改密码」入口
- [x] `config.py`/`.env.example` 加 `LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCK_MINUTES`；`scripts/create_admin.py` 同步用 `validate_password`
- [x] 前端 `lib/api.ts` `handle` 支持 204 No Content（改密返回 null）

**阶段 7（JWT 双 token + 撤销，M0 步骤5，代码完成）**
- [x] `sql/13_tokens.sql`：`refresh_tokens`（id UUID PK, user_id FK CASCADE, jti TEXT UNIQUE, expires_at, revoked_at, created_at, user_agent, ip）+ `token_revocations`（jti TEXT PK, user_id FK CASCADE, expires_at, reason, created_at）；挂进 `00_init.sql`
- [x] `config.py`：`jwt_expire_hours` → 拆成 `jwt_access_expire_minutes=15` + `jwt_refresh_expire_days=7`
- [x] `services/auth.py`：access 15min 带 `jti`+`type:access`；`create_refresh_token` 7d 落 `refresh_tokens` 表；`_is_revoked(jti)` 查黑名单（`get_current_user` 解码后校验）；`verify_refresh` 校验签名/类型/撤销/用户活跃返回 (uid,jti)；`revoke_refresh`/`revoke_access`(写黑名单)/`revoke_all_user_tokens`/`revoke_access_token(token,*,reason)` 公开 helper
- [x] `routers/auth.py`：`LoginResponse` 加 `refresh_token`；`POST /auth/refresh`（验 refresh → 读库取 role → 发新 access，refresh 不轮换）；`POST /auth/logout`（撤销 refresh + 拉黑当前 access，审计）；`change_password`/停用/改密调 `revoke_all_user_tokens`
- [x] 前端 `lib/api.ts`：双 token 由后端写 httpOnly Cookie；401 单飞 refresh + 重试一次，refresh 失败跳登录；SSE 同样走 Cookie
- [x] `components/AuthProvider.tsx`：login/logout/bootstrap 全走 Cookie 会话，不把 Web token 存入 localStorage
- [x] `mobile/lib/api.ts` + `mobile/contexts/AuthProvider.tsx`：同双 token + 401 自动刷新（expo-secure-store 两个 key + 内存缓存 + 单飞）
- [x] 验证：后端 `py_compile` 全过；前端 `tsc --noEmit` + `npm run build`（14 路由）全过；mobile `tsc --noEmit` 全过

## 后端 · 审计日志（M0 步骤3）

- [x] `sql/11_audit.sql`：`audit_log`（id BIGSERIAL, user_id UUID 无 FK, action, target_type, target_id, detail JSONB, ip, user_agent, created_at）+ 3 索引；挂进 `00_init.sql`。user_id 不设 FK：用户硬删后审计记录仍需保留（合规追溯）
- [x] `services/audit.py` `log(action, *, request, user_id, target_type, target_id, detail)`：DB 落表 + 结构化日志（fuxi.audit）双写；IP 取 `X-Forwarded-For` 首段；**写失败绝不阻塞业务**（try/except，仅 log.error）
- [x] 埋点：login_success / login_failed / user_create / user_update / user_deactivate / user_reset_password / ingest_url / ingest_file / note_delete / wiki_compile

## 后端 · 历史

- [x] `GET /search/history`（随检索功能完成）
- [x] `GET /qa/history`（随问答功能完成）

## 前端（`frontend/`）

- [x] 初始化 Next.js 16 + Tailwind v4 + TypeScript 工程
- [x] 接入 house style（色板 / 字体，见 CLAUDE.md §6）
- [x] 整体框架：侧边导航 Sidebar + 根布局 + /api 代理 + api 封装/类型
- [x] 入库页 ingest（链接/文件入库 + 队列进度轮询）
- [x] 检索页 search（搜索框 + 模式切换 + 标签云 + 结果卡片 + 高亮片段）
- [x] 笔记详情页 note（标题/来源/标签/摘要/要点/实体/正文，实体可跳图谱并自动选中该实体）
- [x] 问答页 qa（对话式 + 来源 chips + **SSE 逐字流式** + 思考态 + 建议问题）
- [x] 知识图谱页 graph（自写力导向布局 + 类别着色 + 实体侧栏 + 支持 `?entity=` 深链自动选中）
- [x] 主题页 wiki（列表 + 详情：章节/引用角标/观点矛盾/来源）
- [x] 历史页 history（问答历史 + 搜索历史）
- [x] **笔记列表页 `/notes`**（M1：分页 + 类型/标签筛选 + 关键词）
- [x] **问答风格切换**（M1：default/executive/technical/eli5 分段控件 + 非 default 徽标）
- [x] **笔记 Q&A 区块**（M1：admin 触发生成 + 展示已沉淀问答 + 3s 延迟重载）
- [x] **标签治理页 `/admin/tags`**（M1：受控词表 + 归并 + 标签云点击填充）
- [x] **MCP 管理页 `/admin/mcp`**（M1：token 列表 + 创建一次性明文 + 启停/删除）
- [x] **用量看板升级 `/admin/usage`**（M1：组织今日合计 + 手绘 SVG 趋势折线 + ≥80% 告警 + 每用户进度条）
- [x] **空间切换 `SpaceSwitcher`**（M2：TopBar 下拉，仅可见空间 >1 时显示，链接 /spaces）
- [x] **空间管理页 `/spaces`**（M2：空间列表 + 角色徽标 + 建空间 + 成员面板 + AddMember 防抖 email 搜索）
- [x] **入库带 space_id**（M2：链接 body / 文件 query param，默认 active space）
- [x] **MCP 管理页带空间选择**（M2：创建表单空间下拉 + token 列表项内联变更空间）
- [x] **SpacesProvider**（M2：拉 /spaces + active space 存 localStorage + `useSpaces()`/`canAct()`/`activeSpaceForIngest()`）；Sidebar 加「空间」导航项

## 数据迁移 / 运维

- [x] `scripts/seed_demo.py` 灌入 6 篇示例笔记 + 9 实体 + 1 Wiki 主题页（无密钥也能演示检索/图谱/Wiki）
- [ ] `scripts/migrate_from_mywiki.py` 把 my-wiki 笔记导入（仅注释占位）
- [x] **定时备份**：`deploy/backup/pg_dump.sh`（pg_dump 全库 `--no-owner` + tar 打包 raw 文件，gzip，保留 14 天）+ `fuxi-backup.service`/`.timer`（systemd 每日 03:00 触发）；恢复步骤见 `docs/backup-restore.md`（含 ES reindex 回填）。本批仅服务器本地落盘，异地同步后续接
- [x] **独立持久化 worker**：`workers/job_runner.py` 用 `FOR UPDATE SKIP LOCKED` 领取 jobs，启动时恢复遗留 running 任务；ingest/compile/qa_gen 均不依赖 API 进程内 BackgroundTasks
- [x] **M2 迁移与验收**：`scripts/migrate_m2_spaces.py` 回填空间并重建 ES；`scripts/verify_m0_m2.py` 自动验证鉴权、worker、ACL、图谱、标签、删除约束与 MCP
- [x] **M3 定时维护入口**：`scripts/enqueue_m3_maintenance.py` + `fuxi-maintenance.timer`，到期来源刷新与每日空间巡检只负责入队，由独立 worker 消费
- [x] **M4 增量同步与自动规划**：同一 maintenance timer 每小时入队 active 连接器，并对有开放治理问题的空间每日生成 Agent 提案

## 部署（linux-server）

- [x] PostgreSQL 18 + pgvector 0.8.3，建库 fuxi + 角色 fuxi，灌 schema（见 docs/deploy.md）
- [x] Redis 已就绪（127.0.0.1:6379）
- [x] 后端 + 前端部署在 linux-server（/opt/fuxi）：后端 127.0.0.1:8000，前端 0.0.0.0:19000 → http://118.25.93.30:19000
- [x] 入库链路真库端到端验证（抓取→提取→stage/progress→jobs→/api 代理→错误处理，全过）
- [x] 进程改 systemd：`fuxi-backend` / `fuxi-frontend` / `fuxi-worker`（enabled，开机自启 + Restart=always）
- [x] `fuxi-backup.timer` 已启用，每日 03:00；部署前备份已实际生成并通过 gzip 完整性检查
- [x] 填入 API_KEY 跑通完整入库（`/etc/profile` 注入 + systemd `bash -lc` 包裹使 key 对进程可见）
- [x] 装 Elasticsearch + ik 分词插件（Docker ES 8.17.6 + ik，绑 127.0.0.1:9200，容器 `fuxi-es`；部署文件见 `deploy/es/`）
---

## 文档

- [x] `README.md` 项目介绍
- [x] `DESIGN.md`（沿用 my-wiki 思路，待补 fuxi 版）— ⬜ fuxi 专属设计文档
- [x] `docs/api-contract.md` 接口契约
- [x] `docs/auth-design.md` 鉴权设计（含 M2 空间双层角色）
- [x] `docs/spaces-design.md` 空间 + 权限感知设计（M2）
- [x] `CLAUDE.md` 工作规则与规范
- [x] `PROGRESS.md` 本文件

---

## 更新日志

- **2026-07-02** — 修复问答流事件已到达但 React 页面不更新：移除依赖可变数组下标的 `streamingIdx`，为用户/助手消息分配唯一 ID，`plan/sources/token/done/error/verification` 全部按 ID 做函数式状态更新，避免并发渲染下事件写入错误消息位置。
- **2026-07-02** — 修复登录用户问答流返回空响应：chunk 语义检索 SQL 的绑定参数顺序错误，把第二个 embedding 向量传给了空间 `uuid[]` 占位符；现按 SQL 占位顺序绑定“向量→子查询空间→排序向量→外层过滤”，新增回归测试。前端同时在 SSE 未收到 `done` 时显示请求失败，不再永久停留“思考中”。
- **2026-07-02** — 修复问答页 SSE 一直停在「思考中」：前端流解析器原先只识别 `LF` 空行，无法解析生产 `sse-starlette` 输出的 `CRLF` 事件帧；现兼容 CRLF/LF/CR，并正确处理跨网络 chunk 的 CRLF。
- **2026-07-02** — **v0.8.0 部署上线**。迁移前数据库与 raw 备份通过完整性检查；SQL 25~33 单事务迁移成功，配置 `CONNECTOR_SECRET_KEY`，启用 `fuxi-maintenance.timer`。生产后端 16 项测试、前端 24 路由构建、M0~M2 回归及 M3/M4 生命周期/通知/连接器密文/Agent 冒烟全部通过。四个真实平台连接器仍待提供各平台凭据后联调。
- **2026-07-02** — 新增 `scripts/verify_m3_m4.py` 生产冒烟验收：覆盖笔记版本、软删除/回收站/恢复、订阅通知、连接器凭据密文边界和 Agent 持久化任务，并自动清理临时数据。
- **2026-07-02** — 修复生产回归脚本在 M3 schema 下的清理顺序：删除临时笔记后先清理 `source_documents`，再删除临时空间，兼容空间外键 `RESTRICT`。
- **2026-07-02** — 修复 M3/M4 maintenance systemd 单元未加载 `backend/.env`：补充 `EnvironmentFile`，确保定时入队使用生产数据库连接与应用配置。
- **2026-07-02** — **M4 v0.8.0 代码完成，待生产与真实平台验收**。新增 SQL 29~33、`docs/m4-design.md`；实现 Confluence/飞书全量快照比较、Google Drive changes token、SharePoint deltaLink 四类只读连接器，Fernet 加密凭据与持久化同步 worker；实现空间/标签/笔记订阅、站内通知、问答反馈；实现五类白名单治理提案、space_admin 审批和确定性执行器。新增连接器、通知、Agent 页面及通知未读数。后端编译/16 项单测、移动端类型检查、前端 24 路由生产构建通过。生产尚未配置 `CONNECTOR_SECRET_KEY`，也未写入任何平台凭据。

- **2026-07-02** — **M3 v0.7.0 代码完成，待生产迁移验收**。新增 SQL 25~28、`docs/m3-design.md`；实现来源身份、编辑/版本恢复、软删除/回收站、手动与定时刷新；五类治理巡检和闭环页面；智谱 rerank、authority 加权、PII 外发掩码；最多三路的有界 Agentic RAG 与引用校验。后端编译/12 项单测、前端类型检查与 21 路由生产构建通过。生产 schema/systemd 尚未变更。

- **2026-06-29** — **M0~M2 缺口修复、生产迁移与验收完成**。Web 鉴权改 httpOnly Cookie，移动端保留 SecureStore Bearer，严格隔离 access/refresh 并让改密立即失效旧 access；修复过期锁、跨空间详情/状态/标签/图谱/统计泄漏、MCP 空间与 RRF 过滤、空间删除约束、editor 入库与 wiki 权限。新增 `job_runner` 持久化消费 ingest/compile/qa_gen，上传原文件在 202 前落盘；新增 SQL 24 收紧 space_id 与 FK 删除策略。服务器已执行 SQL 11~24、M2 数据/ES 迁移，启用 worker 与备份 timer；后端单测、前端/移动端类型检查、生产构建及 `verify_m0_m2.py` 端到端验收通过。

- **2026-06-29** — **HTTPS 退出项目范围**。按当前部署决策，从 README、roadmap、鉴权设计、部署说明、移动端设计、MCP 说明和 PROGRESS 的现行目标/待办中移除 HTTPS 与自签反代；M0 安全核心重新编号为 5 步。保留历史更新日志中的原始实施记录，不删除 `deploy/nginx/` 现有文件。

- **2026-06-28** — **M2「权限与多空间」全量交付：Spaces + ACL + 细化角色**（roadmap M2，P0 核心）。多团队内容隔离：笔记 / wiki / MCP token 各归属空间，读写按空间 ACL 过滤，写操作从「sysadmin only」放宽到空间角色。新增 SQL 18、20-23（18 新表；19 已被 M1 的 mcp_tokens 占用，故 notes/wiki/mcp_token/membership 顺延为 20/21/22/23 避免冲突）。设计见新增 `docs/spaces-design.md`，版本号升到 **v0.6.0**。
  1. **SQL 18 + 20-23 + 迁移**（步骤1）：`18_spaces` spaces + space_members（viewer/editor/space_admin + default 种子）；`20_notes_space` notes 加 space_id + created_by；`21_wiki_space` wiki_pages 加 space_id；`22_mcp_token_space` mcp_tokens 加 space_id；`23_default_membership` 现有用户全加为 default editor。迁移策略：全归入 default 空间，向后兼容。挂进 00_init（按 18→19→20→21→22→23 顺序，19_mcp_tokens(M1) 与 20_notes_space(M2) 无表依赖冲突）。
  2. **services/spaces.py + ACL 注入**（步骤2）：`visible_space_ids(conn, user)`（sysadmin→None 全可见，普通→成员空间列表）+ `space_filter_from(sids, alias)`（生成 SQL 片段，None→空片段）+ `role_in_space`/`assert_space_role`/`assert_note_role`。每请求查一次 space_members，透传 sids 给所有读路径。
  3. **写路径角色校验**（步骤3）：ingest POST 注入 CurrentUser + 校验目标空间 editor + 透传 space_id/actor_id；DELETE /notes/{id}、generate-qa 从 require_admin 改 assert_note_role；wiki compile 改 _resolve_compile_space（来源同空间 + space_admin）；compile_worker 取 wiki 行 space_id 只取同空间笔记。
  4. **读路径收敛**（步骤4）：search（PG `space_filter_from` + ES `visible_space_strs` terms filter）/ qa `_retrieve(question, space_ids)`（收 space_ids 不收 user，MCP 复用）/ notes 详情·列表 全部按空间过滤。
  5. **图谱丢视图改 JOIN**（步骤5）：get_graph/get_entity 改 `note_entities ne JOIN notes n` + `space_filter_from(sids, alias="n")`，替代无法接受运行时 space 参数的 `entity_note_counts`/`entity_cooccurrence` 全局视图（旧视图保留向后兼容）。修了 alias 不一致 bug（关联笔记查询 alias="notes"，子查询 alias="n"）。
  6. **Wiki 权限感知**（步骤6）：compile_status/list_wiki/get_wiki 加 space 过滤（404 无权）；CompileRequest/WikiSummary/WikiDetail 加 space_id。
  7. **MCP 绑空间**（步骤7）：`space_filter_from` 去 user 参数（admin 决策已编码进 None，MCP 可复用）；`verify_token` 返回 `(token_id, space_id)`；mcp_server 加 `_mcp_space_ids` ContextVar + `_space_filter()` helper，8 工具按 token 空间过滤；ask 复用 `qa_mod._retrieve(question, _space_ids())`；图谱工具用内联 JOIN。token 未绑(NULL)=全库仅向后兼容，新 token 永远绑 default。mcp_admin token CRUD 带 space_id/space_name。
  8. **空间管理 API**（步骤8）：`routers/spaces.py`（新）挂 `/api` 下登录依赖。空间 CRUD + 成员管理 + 用户搜索（`GET /spaces/{id}/members/search`，space_admin 用，因 `/auth/users` 是 sysadmin only）。空间管理员不能改/移除自己（防自锁）；default 不可删；全写操作审计。
  9. **前端**（步骤9）：`SpacesProvider.tsx`（拉 /spaces + active space 存 localStorage + useSpaces/canAct/activeSpaceForIngest）；`SpaceSwitcher.tsx`（TopBar 下拉，>1 空间才显示）；`/spaces` 页（列表+角色徽标+建空间+成员面板+AddMember 防抖 email 搜索）；入库页带 space_id；MCP 管理页加空间选择 + 列表项内联变更；Sidebar 加「空间」导航。**前端 active space 仅用于入库目标**，读可见性服务端推导（不收客户端 space_id）避免切空间认知错位。
  10. **文档收尾**（步骤10）：新增 `docs/spaces-design.md`（双层角色 + ACL 注入 + 各模块改动 + 迁移 + 决策记录）；更新 `docs/api-contract.md`（§11 空间 + 枚举 space_member.role + ingest/wiki/MCP token 带 space_id + 权限标注改空间角色）；`docs/auth-design.md` 加空间双层角色小节；PROGRESS 总览/各模块/前端/文档；README v0.6；`config.app_version` 0.5→0.6。
  - **关键决策**：① 隔离粒度选空间而非 owner（保留空间内共享语料检索，避免全链路按 user 过滤逆架构）；② 双层角色正交（sysadmin 天然全空间 space_admin 不写 membership 行）；③ `space_filter_from` 去 user 参数（解耦后 MCP 无需构造 CurrentUser 即可复用）；④ 图谱丢视图改 JOIN（视图无法接受运行时 space 参数）；⑤ MCP 用 ContextVar 而非 FastMCP Context（现有工具用模块级 pool 调用无 Context 注入，改动最小）；⑥ 前端 active space 不收窄读结果（避免认知错位，仅用于入库目标）。
  - **编号说明**：M2 的 spaces 相关迁移从 18 起编，但 19 已被 M1 的 `19_mcp_tokens.sql` 占用，故 notes_space/wiki_space/mcp_token_space/default_membership 顺延为 20/21/22/23，避免编号冲突。`00_init.sql` 按 18→19→20→21→22→23 顺序执行，19_mcp_tokens(M1) 与 20_notes_space(M2) 无表依赖冲突，先后无影响。
  - 验证：后端 `python3 -m compileall`（services/spaces + routers/{search,qa,notes,graph,wiki,ingest,spaces,mcp_admin} + mcp_server + workers/{ingest,compile}_worker 全过）；前端 `tsc --noEmit` 全过。本地无 backend venv（fastapi/psycopg/mcp 未装），运行时验证待真库部署。**待真库验证**：灌 18-22、建空间+加成员测不同角色可见性、MCP token 绑空间后只返该空间内容、ingest 写对 space_id。

- **2026-06-28** — **M1 全量交付：5 块增强 + MCP Server**（roadmap M1）。每块独立验证（py_compile / tsc / build 全过），新增 SQL 14-19（除 18 跳号）。
  1. **笔记列表/浏览页（J）**：`sql/14_notes_list` 加 authority 占位列 + views_count；`routers/notes.py` `GET /notes`（分页 + 类型/标签/关键词过滤，仅 done）；`GET /notes/{id}` 打开即 views_count+1；前端 `/notes` 列表页（分页 + 筛选条）。`14` 是列迁移，无新表。
  2. **标签治理（D②）**：`sql/15_tags` 受控词表；`routers/tags.py`（从 search.py 迁出 `GET /tags` + 新增 vocab/CRUD/merge）；归并走 `array_replace` 物理回写 + ES 同步 + 词表标 merged；前端 `/admin/tags`。`status` 权重进排序留 M3。
  3. **文档→Q&A 生成 + 回灌（D①）**：`sql/16_generated_qa`（note_id FK CASCADE + question+answer+embedding HNSW）+ `17_jobs_qa_gen`（jobs.job_type 加 'qa_gen'，ALTER DROP/ADD CHECK 绕过 CHECK 重建）；`qa_gen_worker`（enqueue + run，记 qa_gen 用量）；`POST /notes/{id}/generate-qa` + `GET /notes/{id}/qa`；`qa._retrieve` 增 `_retrieve_generated_qa` 取 top-2，`_build_context` 前置「已沉淀问答」。
  4. **角色化输出风格（D③）**：`QaStyle = default/executive/technical/eli5`，`build_qa_system(style)` 组合 QA_SYSTEM + 风格提示（不动事实约束）；`qa`/`qa_stream` 入参 style，非法回退 default；前端分段控件 + 徽标，SSE body 带 style。
  5. **成本看板升级（H）**：`compile_worker.run(slug, *, actor_id=None)` 包 usage.collect + record_usage("compile")，wiki.py 透传 admin.id；`GET /auth/usage?days=1..90` 增 org_today + org_trend（补齐缺日）+ alerts（≥80%）；前端 `/admin/usage` 重写：组织今日卡 + 手绘 SVG 趋势折线 + 告警段 + 每用户进度条（80% 琥珀/超额红）。
  6. **MCP Server（K-A）**：`backend/mcp_server.py` FastMCP（stateless_http + json_response）+ 8 个只读工具（search/ask/get_note/list_notes/get_graph/get_entity/list_wiki/get_wiki，全返 JSON 字符串）+ `_auth_wrapper` 裸 ASGI Bearer 中间件 + `is_available()`；`routers/mcp_admin.py` token CRUD + `verify_token`（bcrypt 线性扫 + 更新 last_used_at）；`sql/19_mcp_tokens`；`main.py` 挂 `/mcp`（不挂全局 _auth，自行 Bearer 校验，lifespan 内 session_manager.run）；前端 `/admin/mcp`（一次性明文 + 复制 + 启停/删）；`docs/mcp.md`（工具一览 + Claude Desktop 接入 + 鉴权）。`mcp` 包未装时 `/mcp` 不挂载，其余接口不受影响。
  - **MCP 鉴权决策**：SDK 自带 TokenVerifier 走 OAuth 2.1（AS 端点 + client 注册 + PKCE）过重，改裸 ASGI 包装 Bearer 校验，与 fuxi 既有 JWT/Bearer 一致。MCP token 与登录 JWT 分开：不挂全局登录依赖、不归属用户、不计入 token_usage 配额。
  - **跳号说明**：SQL 编号 14-17、19 连续使用（generated_qa=16、jobs_qa_gen=17、mcp_tokens=19），18 未用（无 18_usage_compile.sql：token_usage.operation 无 CHECK 约束，compile 直接写入即可，无需迁移）。
  - 验证：后端 `py_compile`（main/mcp_server/mcp_admin/notes/tags/qa/auth/wiki/qa_gen_worker/compile_worker 等）全过；前端 `tsc --noEmit` + `npm run build`（18 路由，含 /notes、/admin/tags、/admin/mcp、/admin/usage）全过。**待真库验证**：灌 14-17/19、装 `mcp>=1.28`、测 MCP `initialize`→`tools/list`→`tools/call` 全链路。
  - 文档收尾：`docs/api-contract.md`（notes 列表 + generate-qa + qa 样式 + tags 治理 + usage 趋势/告警 + §10 MCP）、`docs/auth-design.md`（权限表 + MCP token 小节）、新增 `docs/mcp.md`、PROGRESS 总览/各模块、README 版本 v0.5。

- **2026-06-28** — **前端接入 SSE 流式问答 + 笔记实体可点进图谱详情 + qa_stream 不阻塞 event loop**（3 项已实现但未接上的功能补齐）。
  1. **前端接 SSE**：后端 `POST /qa/stream` 早已实现但前端一直走同步 `POST /qa`（整段返回、无逐字效果，SSE 闲置）。新增 `frontend/lib/sse.ts`（浏览器 `EventSource` 只支持 GET，故用 `fetch` POST + `ReadableStream` 手动解析 SSE 帧：`event:`/`data:` 按空行切块，`parseEvent` 还原事件名与多行 data），`streamQa()` 驱动 `onSources`/`onToken`/`onDone` 三个回调；`app/qa/page.tsx` 重写 `ask`：用户问题 + 空 assistant 占位先入列，sources 到时填入、token 到时逐字拼到占位末尾、done 标 `generated`；流式期占位无内容时显示「思考中…」，滚动跟随 token 增长。验证：tsc + build 通过（13 路由）。对齐 CLAUDE.md §5「问答优先走 SSE 流式」规范。
  2. **笔记实体 → 图谱详情**：`app/notes/[id]` 实体链接原本固定跳 `/graph`（没带 id，进不去具体实体详情，后端 `GET /graph/entities/{id}` 闲置）。改为跳 `/graph?entity=<id>`；`app/graph/page.tsx` 读该参数，节点数据就绪且目标实体在当前过滤结果内时自动 `pickEntity` 选中并展开侧栏。`useSearchParams` 按需包 `Suspense` 边界（Next 16 要求）。
  3. **qa_stream 不阻塞 event loop**：`routers/qa.py` 的 `qa_stream` 是 async 路由，但内部 `_retrieve()` 含同步阻塞的 embedding 调用（`embedder.embed()` 走同步 OpenAI client），会卡住 event loop。改用 `asyncio.to_thread(_retrieve, question)` 放进线程池跑。顺带修降级 bug：缺密钥/调用失败时降级文案只 `append` 未作 `token` 事件 `yield`，前端会收到空回答——现在 fallback 也 `yield` 一个 `token` 事件。
  - 验证：后端 `py_compile`（main/config/auth/logging/middleware/es/ingest_worker/compile_worker）全过；纯 logging 冒烟（JSON 格式 + extra 透传 + 异常堆栈入 exc 字段）通过。本地无 backend venv，FastAPI 中间件运行时冒烟待真库部署验证。

- **2026-06-28** — **M0 安全核心 · 步骤1：结构化日志 + 全局异常处理**（roadmap M0 第一项）。后续所有 M0 改动受益于统一日志，故先做。
  - `services/logging.py`：`setup_logging(level, fmt)` 配 `fuxi` 根 logger + uvicorn/access 复用同一 handler；JSON 单行 formatter（`ts/level/logger/msg` + 业务 `extra` 透传 + 异常堆栈入 `exc`）；`LOG_FORMAT=text` 本地开发切纯文本；幂等。
  - `services/middleware.py` `CatchErrorsMiddleware`（`BaseHTTPMiddleware`）：兜底未捕获异常 → 结构化记录（path/method/user_id/ip）→ 返回 500 `{"detail":"服务器内部错误"}`，不泄露堆栈。HTTPException 走 FastAPI 默认处理不受影响。
  - `services/auth.py` `get_current_user` 注入 `Request`，解析出的 user 写 `request.state.user`，供中间件/日志取 user_id。
  - es/compile/ingest 统一改用 `get_logger`；ingest_worker 补 start/done/failed 关键埋点（此前完全无日志，失败只写 DB）。
  - `config.py` + `.env.example` 加 `LOG_LEVEL`/`LOG_FORMAT`。
  - **范围说明**：本批只做日志+异常兜底。M0 其余 5 项（备份/HTTPS自签反代/审计日志/账号安全/JWT双token）按计划逐步做；独立 worker 后置到 M0.5。

- **2026-06-28** — **M0 安全核心 · 步骤2：备份/灾备脚本**（纯运维脚本 + 文档，零后端代码改动）。`deploy/backup/pg_dump.sh`：`pg_dump --no-owner` 全库 gzip + tar 打包 `STORAGE_LOCAL_ROOT` 原始文件 gzip，输出 `/opt/fuxi/backups/db-*.sql.gz` 与 `raw-*.tar.gz`，保留 14 天自动清理；`BACKUP_DIR`/`KEEP_DAYS`/`PG_CONN`/`RAW_ROOT` 环境变量可覆盖。`fuxi-backup.service`（oneshot）+ `.timer`（每日 03:00，`Persistent=true` 错过补跑）。`docs/backup-restore.md`：恢复步骤（gunzip 灌库 + raw 解压 + ES `reindex_es.py` 回填 + 验证）。验证：`bash -n` 语法过，dry-run 流程正确（mac 无 pg_dump 在连接步失败，符合预期）。**限制**：仅服务器本地落盘，单机单点；异地同步（rsync/R2）后续接。

- **2026-06-28** — **M0 安全核心 · 步骤3：HTTPS + nginx 反代（自签证书验证链路）**。`deploy/nginx/fuxi.conf`：nginx 监听 19443 ssl，`/api/` → 后端 `127.0.0.1:8000`、`/` → 前端 `127.0.0.1:19000`；SSE 路禁 `proxy_buffering` + 300s 超时 + HTTP/1.1（流式问答不被缓冲打断）；`X-Forwarded-Proto/Host/X-Real-IP` 转发；`client_max_body_size 50m`（入库上传）。`deploy/nginx/gen-selfsigned.sh`：openssl 自签 RSA2048 825 天，CN=fuxi，SAN 含服务器 IP + localhost（浏览器仍警告需手动信任，自签阶段预期）。后端 CORS 从硬编码 `["*"]` 收紧为 `CORS_ORIGINS` env 驱动（默认本地 + 前端源）；`config.py`/`.env.example` 加 `cors_origins`。`docs/deploy.md` 补「反向代理 + HTTPS（自签阶段）」段（架构图 + 部署 + 验证 + 限制）。验证：`py_compile` + `bash -n` + openssl 实际生成证书验 SAN 含 IP/DNS 全过。**范围说明**：用户选定「先做自签/IP 验证」，故不引入 Caddy；正式域名+Let's Encrypt（Caddy vs nginx+certbot）待有域名后再定。**限制**：浏览器自签警告、移动端 RN 不信任自签（暂走 HTTP）。

- **2026-06-28** — **M0 安全核心 · 步骤4：审计日志**。`sql/11_audit.sql` `audit_log` 表（user_id 无 FK 保留合规追溯、action/target_type/target_id/detail JSONB/ip/user_agent/created_at + 3 索引），挂进 `00_init`。`services/audit.py` `log()` DB 落表 + 结构化日志双写，**写失败不阻塞业务**（try/except 仅 log.error），IP 取 `X-Forwarded-For` 首段。埋点 10 处：login_success/login_failed（含 inactive）/user_create/user_update/user_deactivate/user_reset_password/ingest_url/ingest_file/note_delete/wiki_compile，含 admin 触发者 user_id + 对象 target。验证：`py_compile`（audit/auth/notes/wiki/ingest）全过。真库运行时冒烟（登录后查 `SELECT * FROM audit_log`）待部署。

- **2026-06-28** — **M0 安全核心 · 步骤6：JWT 双 token + 撤销（access 15min + refresh 7d）**（M0 安全核心收官）。后端 + Web + 移动端三端全改。
  - **数据**：`sql/13_tokens.sql` `refresh_tokens`（user_id FK CASCADE, jti UNIQUE, expires_at, revoked_at, user_agent, ip）+ `token_revocations`（jti PK 黑名单, expires_at, reason）；挂进 00_init。access 黑名单行随 access 自然过期失效；refresh 一次 revoked_at 置位不可再用。
  - **后端**：`config.py` `jwt_expire_hours` → `jwt_access_expire_minutes=15`+`jwt_refresh_expire_days=7`；`services/auth.py` access 带 `jti`+`type:access`，`create_refresh_token` 7d 落表，`_is_revoked` 查黑名单（`get_current_user` 解码后校验，被撤销 access 立即失效），`verify_refresh` 校验签名/类型/撤销/活跃，`revoke_refresh`/`revoke_access`/`revoke_all_user_tokens`/`revoke_access_token(token,*,reason)`；`routers/auth.py` LoginResponse 加 `refresh_token`、新增 `POST /auth/refresh`（refresh 不轮换，role 读库不信任旧 token）、`POST /auth/logout`（撤销 refresh + 拉黑当前 access + 审计），`change_password`/停用/改密调 `revoke_all_user_tokens` 强制重登。
  - **Web**：`frontend/lib/api.ts` 双 token（`fuxi_access`+`fuxi_refresh`），401 → 单飞 `refreshAccess()` 换新 access + 重试原请求一次（retry 置空防递归），refresh 失败清双 token 跳 `/login`；`getToken` 别名保留供 `sse.ts`。`AuthProvider` login 存双 token、logout 先调后端 `/auth/logout`（失败不阻塞前端登出）、bootstrap 用 access 拉 `/auth/me`。
  - **移动**：`mobile/lib/api.ts` + `contexts/AuthProvider.tsx` 同构（expo-secure-store 两个 key + 内存缓存 `loadTokens` 预载 + 单飞 refresh + 401 回调跳登录）。
  - 验证：后端 `py_compile` 全过；前端 `tsc --noEmit` + `npm run build`（14 路由）全过；mobile `tsc --noEmit` 全过。**待真库验证**：灌 `13_tokens.sql`、测 login 双 token / refresh 换 access / logout 撤销后旧 token 失效 / 改密强制重登。
  - **决策**：用户选「双 token + 撤销，仍走 Bearer」。refresh 不轮换（简单稳定，检测重放风险后再考虑轮换）；改密/登出把当前 access 入黑名单立即失效（不等 15min 自然过期）。至此 M0 安全核心 6 步全部代码完成。

- **2026-06-28** — **M0 安全核心 · 步骤5：账号安全（密码策略/失败锁定/自助改密）**。`sql/12_account_security.sql`：users 加 `failed_login_attempts`/`locked_until`/`last_login_at`/`password_changed_at`（幂等迁移）。`services/auth.py` `validate_password`（≥8 位 + 字母 + 数字，替代旧 `min_length=6`）。`POST /auth/login` 失败递增计数，达 5 次锁 15 分钟（423），成功清零 + 记 `last_login_at`（同事务）。`POST /auth/change-password` 自助改密（验旧密码 + 校验新密码强度 + 刷 `password_changed_at` + 审计）。前端 `/settings` 页 + Sidebar「修改密码」入口；`lib/api.ts` `handle` 支持 204。`scripts/create_admin.py` 同步用 `validate_password`。`config.py`/`.env.example` 加 `LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCK_MINUTES`。验证：`py_compile` + `tsc --noEmit` 全过。**注**：改密后旧 access token 仍有效（JWT 无状态），步骤6 双 token 后会撤销强制重登。

- **2026-06-28** — **入库 token 入账 + 文档残留清理**（review 收尾）。
  1. **入库计费**：之前 `qa`/`qa_stream`/`search` 调用前后已 check/record token 用量，但 **ingest 链路漏记**——`routers/ingest.py` 的两个 POST 路由虽挂了 admin 依赖，却没把触发者 user_id 传进 worker，`ingest_worker` 也没接 `usage.collect()`，导致 analyze(glm-5.2)/embed(embedding-3) 的 token 不进 `token_usage` 账本、用量看板看不到入库消耗。补齐：路由注入 `CurrentUser`，把 `actor_id=admin.id` 经 `background.add_task(...)` 透传；worker `run(note_id, *, actor_id=None, **fetch_kwargs)` 在 fetch→refine→embed 段包 `with usage.collect() as u:`，结束后 `if actor_id is not None: quota.record_usage(actor_id, "ingest", u)`。BackgroundTasks 跑 FastAPI 线程池，ContextVar 在同线程 set/read 一致，故 `usage.collect()` 在线程池内有效；脚本/迁移入口 `actor_id=None` 跳过（`token_usage.user_id` 有 FK 约束）。
  2. **文档残留清理**：① `services/auth.py`、`sql/08_auth.sql`、`docs/auth-design.md`、PROGRESS 阶段1条目里 `passlib[bcrypt]` / "passlib 弃用" 字样统一改成 `bcrypt` 直连（passlib 1.7.4 与 bcrypt≥4.1 不兼容自检抛 ValueError，真库验证时已踩坑弃用）；② `main.py`/`routers/search.py` docstring 更新到当前状态（ES+ik、system/status 等）；③ `docs/api-contract.md` 把 "后端缺口/待补/建议支持流式" 等过时标注改成 "已实现/流式已实现"。
  - 验证：后端 `py_compile`（main/config/db/routers/services/workers/providers 全过）；前端 `tsc --noEmit` 过（本批仅改后端+文档+SQL 注释，前端零改动）。真库真 API 验证待部署。

- **2026-06-28** — **修复：点击标签云不会自动检索（已部署）**。原因有二：前端 `toggleTag` 仅在「已有结果」时才重搜、`runSearch` 在查询词为空时直接返回；后端 `/search` 在 `q` 为空时也直接返回空。修复：前端点标签即触发检索（`runSearch` 改为「查询词与标签都为空才跳过」，否则照常）；后端新增「按标签浏览」路径——`q` 空但 `tags` 非空时用 `_tag_search` 按标签+时间过滤返回（不打分/不调 LLM/不计费），`mode` 返回 `"tag"`；前端「已降级」提示改为仅在真降级（resp.mode=keyword 且请求非 keyword）时显示，避免 tag 模式误报。真库验证：空词 + 标签 Elasticsearch 返回 2 篇、mode=tag；前端 build+重启。
- **2026-06-28** — **用户名 username：建号填 用户名/显示名/邮箱，登录用 用户名或邮箱 皆可（已部署）**。`sql/10_user_username.sql`（users 加 `username` + 部分唯一索引，幂等，挂进 00_init）；后端 `CurrentUser`/`UserOut` 加 username，`POST /auth/login` 改收 `identifier`（`WHERE username=%s OR email=%s`），`POST /auth/users` username 必填 + 用户名/邮箱查重 409，`PATCH` 支持改 username（唯一冲突 409），`create_admin.py` 加 `--username`；前端登录页字段改「用户名或邮箱」、`AuthProvider.login(identifier,…)`、用户管理建号表单加用户名输入并在列表显示 `@username`。真库验证：迁移成功、给现有 admin 设 username=raymond、用户名/邮箱两种方式登录均 200、建号返回 username、重名 409、新成员用户名登录 200（测试用户已清理）；前端 build+重启、/login 200。
- **2026-06-28** — **顶栏检索 + 左下角系统情况 + 版本号（已部署）**。后端：`config.app_version="0.4.0"`（单一来源，main.py FastAPI version 引用）+ `routers/system.py` `GET /api/system/status`（版本/存储后端/PG·pgvector 版本/笔记·实体·主题数/数据库占用/磁盘容量，登录可见）。前端：全局 `TopBar`（检索全部知识 ⌘K，回车跳 `/search?q=` 自动执行；「新建入库」仅管理员）+ `SystemStatus` 面板（存储后端·版本、知识库规模、数据库占用、磁盘容量条强调剩余可用）；`AppShell` 加顶栏，`Sidebar` 品牌处显示 `v0.4.0` 并在底部挂系统情况；`search` 页支持 `?q=` 初始查询（Suspense 包裹 useSearchParams）。版本号项目整体升到 **0.4.0**。真库验证：`/api/system/status` 返回真实数据（local/PG18.0/pgvector0.8.3/14 笔记/盘余 ~112GB），前端 build + 重启、`/`·`/search`·`/login`·`/admin/ingest` 均 200。
- **2026-06-28** — **鉴权阶段 1-5 部署上线 linux-server 并真库验证通过**。rsync 新代码到 /opt/fuxi（删服务器残留 app/ingest）；灌 `08_auth.sql`+`09_history_user.sql`（踩坑：PG15+ 默认收回 public.CREATE → `GRANT CREATE ON SCHEMA public TO fuxi`；历史表属主是 postgres，09 的 ALTER 改用 `sudo -u postgres` 跑）；装依赖时 **passlib 1.7.4 与 bcrypt>=4.1 不兼容**（自检抛 ValueError），改 `services/auth.py` 直接用 `bcrypt` 库 + 弃 passlib；`.env` 注入随机 `JWT_SECRET` 重启 backend；`create_admin.py` 建管理员（raymond814@icloud.com）；前端 `npm run build` 重建 + 重启。验证全过：unauth 401 / login 200 取 JWT / authed me·search·usage 200 / ingest admin / 前端 /login·/admin 200 / 错误密码 401。**剩 HTTPS+反代未做（明文传 JWT，最高优先收尾）**。
- **2026-06-28** — **鉴权阶段 2-5：配额 429 + 历史隔离 + 前端登录 + 管理后台（代码完成，待真库验证）**。
  - 阶段2 配额：新增 `services/usage.py`（ContextVar 用量累加器，与 provider 解耦）+ `services/quota.py`（按 USAGE_TZ 当日聚合，超额抛 429）；`glm.py` 六处 API 调用后 `record_call`，流式加 `include_usage`；`qa`/`qa_stream`/`search`(semantic/hybrid) 调用前 check、调用后 record。
  - 阶段3 历史隔离：`sql/09_history_user.sql` 给两张历史表加 `user_id`（幂等迁移，挂进 00_init）；写入带 user_id，`/search/history`·`/qa/history` 默认只看自己，admin `?scope=all` 看全部。
  - 阶段4 前端登录：`lib/api.ts` 带 Bearer + 401 跳登录 + 429 归类；`AuthProvider`/`AppShell`/`/login`，`Sidebar` 按角色显示导航 + 登出。
  - 阶段5 管理后台：`/admin`（守卫）下入库（自 `/ingest` 迁入并删旧页）/用户管理/用量看板；后端加 `GET /auth/usage`。
  - 验证：前端 `npm run build` 通过（13 路由），后端 `py_compile` 全过。**待 linux-server 真库验证 + HTTPS 反代**。
- **2026-06-28** — **鉴权阶段 1：登录 + 全路由锁 + admin 网关（代码完成，待真库验证）**。新增 `sql/08_auth.sql`（`users` + `token_usage` 账本）并把 07/08 补进 `00_init.sql`；`services/auth.py`（bcrypt + JWT HS256 + `get_current_user`/`require_admin` 依赖）；`routers/auth.py`（login/me + admin 用户管理）；`main.py` 业务路由统一挂登录依赖、ingest 整组 admin、notes DELETE 与 wiki compile 单路由 admin；`config.py`/`.env.example` 加 `JWT_SECRET`/`JWT_EXPIRE_HOURS`/`DEFAULT_DAILY_TOKEN_LIMIT`/`USAGE_TZ`；`requirements.txt` 加 `pyjwt`+`passlib[bcrypt]`+`email-validator`；`scripts/create_admin.py` 引导首个管理员。契约新增「8. 鉴权 Auth」章节 + 全局鉴权约定。设计见新增 `docs/auth-design.md`。本地 `py_compile` 全过；**待 linux-server 真库验证 + HTTPS 反代（阶段 0）**。决策：仅管理员建号、超额硬性 429。
- **2026-06-28** — **5 个增强项全部实现并在 linux-server 真库真 API 验证通过**（整体 ~90% → ~95%，剩余仅反代+HTTPS 运维收尾）：
  1. **R2 落盘**：`services/storage.py` 抽象 `LocalStore`/`R2Store` + 工厂（`STORAGE_BACKEND` 切换，默认 `local` 零依赖），`ingest_worker._save` 上传 raw_bytes 并写 `raw_path`。真库验证：摄取 docx 后原文件落到 `/opt/fuxi/raw/`，`raw_path` 正确入库。**暂用 local 兜底**，未来切 R2 只改 `.env` 不改代码。
  2. **文档分块**：新增 `sql/07_chunks.sql`（`note_chunks` 表 + HNSW）+ `services/chunker.py`（langchain `RecursiveCharacterTextSplitter`，中文分隔符，800/120/80）+ `06_jobs.sql` stage 加 `chunk` 值；`ingest_worker` 插 chunk 阶段逐块向量化写 `note_chunks`；`search._semantic_search` 切 chunk 级（`GROUP BY c.note_id` + `MAX` 取最优块聚合回笔记），`notes.embedding` 留作文档级回退。真库验证：长文档切 2 块、各块嵌入、语义检索按最优块打分（0.7281）去重返回。修 3 个 bug：psycopg3 `executemany` 仅在 Cursor（改 per-row `conn.execute()`）、chunk 级查询 `id` 列歧义（全限定 `notes.` 前缀）、同篇多块重复（GROUP BY + MAX）。
  3. **ES 中文分词**：`deploy/es/`（Docker Compose ES 8.17.6 + ik 插件，绑 127.0.0.1:9200，`xpack.security=false`）+ `services/es.py`（httpx 单例，单索引 `notes_v1`，ik_max_word 索引/ik_smart 检索，`ensure_index`/`index_note`/`search`/`delete_note`，ES 不可达静默降级）+ `search._keyword_search`（ES→回查 PG 保序保分→ES 不可达回退 ILIKE）+ ingest/notes 增删同步索引 + `scripts/reindex_es.py` 回填。真库验证：ik 分词正确（ik_max_word 细粒度 / ik_smart 粗粒度）、关键词「中文分词」返回排序结果（score 12.0）、入库自动索引（7→8）、删除同步（8→7）、reindex 回填 8 篇。
  4. **SSE 流式**：`base.answer_stream` 抽象 + `glm.answer_stream`（`AsyncOpenAI` 单例 + `stream=True` + `thinking on`）+ `llm.answer_stream` 门面转发 + `POST /qa/stream`（`sse-starlette EventSourceResponse`，事件序 `sources`→`token`→`done`，累积答案写 history）。真库验证：36 个 token 事件流出连贯 RAG 回答带 [1] 引用、sources 首发/done 收尾、history 正确保存；同步 `/qa` 仍可用。
  5. **Wiki 编译 worker**：`base.compile_wiki` 抽象 + `WIKI_COMPILE_SYSTEM` 提示（JSON schema）+ `WikiSection/Paragraph/Conflict` 模型 + `glm.compile_wiki`（`response_format=json` + `reasoning_effort=max`）+ `workers/compile_worker.py`（`enqueue_compile` upsert wiki_pages + 建 compile job，`run` 流程 fetch→compile→embedding→done）+ `POST /wiki/compile` + `GET /wiki/{slug}/status`。真库验证：4 个来源编译出 4 个结构化章节（含标题/段落/引用）、conflict=None、compiled_at 已置、embedding 已生成、job 进度 10→40→80→100。
  - **配置侧**：`.env.example` 新增 `STORAGE_BACKEND`/`STORAGE_LOCAL_ROOT`/`R2_*`、`CHUNK_SIZE`/`CHUNK_OVERLAP`/`CHUNK_MIN_SIZE`、`ES_URL`/`ES_TIMEOUT`；`config.py` 对应读取。
- **2026-06-28** — **智谱 GLM 全链路真 API 验证通过**（API_KEY 已配通并经 systemd 对进程可见）。linux-server 实测四条路径：① 语义检索 `mode:"semantic"` 不降级、`embedding-3` 1536 维入库 + `<=>` 余弦相似命中（score 0.61）；② 问答 `generated:true`、glm-5.2 thinking on ~8s 返回连贯回答；③ URL 摄取跑通 fetch→refine(glm-5.2 结构化 JSON)→embedding-3→store，状态达 `done`，标题/摘要/标签均 GLM 生成；④ glm-4.6v 视觉 `describe_image` 正确描述测试图。**顺带修通一个预存 bug**：embedder 返回纯 `list[float]`，而 pgvector 官方 dumper 只覆盖 `numpy.ndarray`/`Vector`，纯 list 被当成 `double precision[]`，导致 `<=>` 算子与 `embedding=%s` 入库均报类型错（6 篇旧 done 笔记 0 个有向量，语义检索从未真正可用）。改用 `%s::vector` 显式转型（`search._semantic_search` 两处 + `ingest_worker._save` 一处）修通，不引入全局 list dumper 以免误伤 `text[]`/`uuid[]`。同步清理 qa/ingest/fetcher/worker/base 中残留的「Claude」字样（保留策略层未来扩展提及的 Anthropic）。完成度 ~85% → ~90%。
- **2026-06-28** — AI 接入重构为 **providers 策略层 + 接入智谱 GLM**：新增 `services/providers/`（`base.py` 抽象 LLMProvider/EmbeddingProvider + 共享数据模型、`glm.py` 智谱实现、`__init__.py` 工厂）；`services/claude.py` → `services/llm.py`、`services/embedder.py` 改为薄门面委托；3 处 import 同步更新（ingest_worker/qa/fetcher）。智谱 `/api/paas/v4/` 兼容 OpenAI 协议复用 `openai` SDK，**不新增依赖**；移除零引用的 `anthropic`。配置收敛成一套 `API_KEY`/`AI_BASE_URL`/`CHAT_MODEL=glm-5.2`/`VISION_MODEL=glm-4.6v`/`EMBED_MODEL=embedding-3`，聊天/视觉/向量共用一个 Key；`embedding-3` 设 `dimensions=1536` 对齐 SQL，**真库零迁移**。linux-server 真验证：py_compile 全过、后端重启健康、空配置三链路（搜索降级关键词/问答降级返回来源/入库止于 refine 报「未配置 API_KEY」）行为同重构前。真 API 调用待填 `API_KEY`。
- **2026-06-28** — 功能 6/7「Wiki 主题页 + 历史页」打通：后端 `GET /api/wiki`、`GET /api/wiki/{slug}`（结构化 sections/conflict + 来源解析）；前端 Wiki 列表/详情（引用角标 + 观点矛盾框）、历史页（问答+搜索历史）。seed 增 1 个 RAG 主题页。**至此 7 个页面前后端全部打通并部署上线**。
- **2026-06-28** — 功能 5「问答 RAG」骨架打通：后端 `POST /api/qa`（检索来源 + Claude 生成，无密钥降级返回来源+提示）、`services/claude.answer()`、`GET /api/qa/history`，检索用中文 2-gram + 英文词兜底；前端对话式问答页（来源 chips + 思考态 + 建议问题）。真库验证：「混合检索/pgvector 亿级/长上下文取代 RAG」均召回到正确来源，生成待密钥。
- **2026-06-28** — 功能 4「知识图谱」前后端打通：后端 `GET /api/graph`（共现视图 + 类别筛选）+ `GET /api/graph/entities/{id}`（实体详情+相关笔记）；前端自写轻量力导向布局（无 d3）+ SVG 图谱 + 实体侧栏。真库验证：9 节点 8 边、按类别筛选、实体相关笔记均正确。
- **2026-06-28** — 功能 3「笔记详情」前后端打通：后端 `GET /api/notes/{id}`（实体/要点/正文分段）+ `DELETE`；前端 `/notes/[id]` 详情页（实体可跳图谱）。顺手把进程迁到 **systemd**（fuxi-backend / fuxi-frontend，开机自启 + 自动重启），解决 ssh 后台启动不稳的问题。真库验证：检索→点结果→看全文整链路通。
- **2026-06-28** — 功能 2「检索」前后端打通：后端 `POST /api/search`（关键词/语义/hybrid + RRF + 片段高亮 + 写历史）、`GET /api/tags`、`GET /api/search/history`；前端检索页（搜索框/模式切换/标签云/结果卡片）。写 `scripts/seed_demo.py` 灌 6 篇示例笔记+9 实体并部署到 linux-server，真库验证：搜 RAG/pgvector 正确返回、标签云正常、无密钥时 hybrid 降级关键词。（部署踩坑：rsync `--delete` 误删 .venv 已修复并加 exclude。）
- **2026-06-28** — 前后端部署到 linux-server：装 Node 20，rsync 代码到 /opt/fuxi，后端 venv+依赖+空密钥 .env 跑在 8000，前端 build 后跑在 19000（http://118.25.93.30:19000）。客户端改懒加载（空密钥不崩）。真库端到端测试入库 example.com：抓取/提取标题/进度/失败处理全通，止于 Claude 步（缺密钥）。
- **2026-06-28** — linux-server 起库：系统 PG18 装 pgvector 0.8.3，建 fuxi 库/角色，灌 schema 并验证（9 表 + 2 视图 + 2 HNSW，全过）；记录连接信息与端口段到 docs/deploy.md + backend/.env.example。
- **2026-06-28** — 功能 1「入库」前后端打通：搭 Next.js 16 + Tailwind v4 前端工程与整体框架（Sidebar 导航 + house style + /api 代理）；实现入库页（链接/文件入库 + 队列进度轮询）；后端 worker 写 jobs 表细粒度 stage/progress、新增 `GET /api/ingest/jobs`、路由统一挂 /api。两端本地编译通过，未在真库验证。
- **2026-06-28** — 建立 CLAUDE.md / PROGRESS.md；补齐 SQL schema 对齐接口契约（HNSW、图谱视图、jobs 进度字段、search hybrid、wiki 结构化列）。
- **2026-06-27** — 写 docs/api-contract.md（解包前端设计稿反推接口）。
- **2026-06-27** — 实现入库链路：fetcher / claude / embedder / ingest_worker / routers/ingest + main.py。
- **2026-06-27** — 建项目骨架与 SQL schema 初版。
