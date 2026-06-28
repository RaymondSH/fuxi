# fuxi · 实现进度

> 单一进度真相。**每次改完代码都要更新本文件**：改对应条目状态，并在底部「更新日志」追加一行。
> 图例：✅ 已完成　🚧 进行中 / 部分完成　⬜ 未开始

**最后更新：2026-06-28**

## 总览

| 模块 | 进度 |
|------|------|
| 数据库 Schema | ✅ 完成（新增 note_chunks 分块表） |
| 后端 · 基础设施 | ✅ 完成（AI 接入已重构为 providers 策略层 + 智谱 GLM） |
| 后端 · 入库 | ✅ 完成（分块 + 原始文件落盘 + ES 同步索引） |
| 后端 · 检索 | ✅ 完成（ES+ik 中文分词关键词路 + chunk 级语义检索） |
| 后端 · 笔记详情 | ✅ 完成 |
| 后端 · 知识图谱 | ✅ 完成 |
| 后端 · 问答 RAG | ✅ 完成（同步 POST /qa + SSE 流式 POST /qa/stream） |
| 后端 · Wiki | ✅ 完成（读 + 编译 worker） |
| 前端 · 框架 | ✅ 完成（Next.js + Tailwind + house style + 导航） |
| 前端 · 全部 7 个页面 | ✅ 完成 |
| 后端 · 鉴权/配额/管理员 | 🚧 阶段1-5 代码完成（登录/配额429/历史隔离/前端登录/admin 界面），待真库验证 |
| 前端 · 登录 + 管理后台 | ✅ 代码完成（登录页 + 路由守卫 + /admin 入库·用户·用量，build 通过） |
| 数据迁移 | ⬜ 仅占位 |
| 部署（linux-server） | 🚧 已上线运行，ES8+ik 已部署，反代/HTTPS 待补（鉴权前置） |

粗略完成度：**5 个增强项（R2 落盘 / 文档分块 / ES 中文分词 / SSE 流式 / Wiki 编译 worker）全部实现并在 linux-server 真库真 API 验证通过，整体 ~95%**。
> 剩余主要是运维收尾：反代 + HTTPS。

---

## 数据库 Schema（`sql/`）

- [x] `01_extensions` 扩展（uuid / vector / pg_trgm）
- [x] `02_notes` 笔记主表 + HNSW + 全文索引（含 source / published_date / related_note_ids）
- [x] `03_graph` entities / relations / note_entities + 图谱视图（提及数 / 共现边）
- [x] `04_wiki` wiki_pages（含 sections / conflict jsonb）+ note_wiki
- [x] `05_history` search_history（含 hybrid）/ qa_history
- [x] `06_jobs` 任务队列（含 stage / progress / note_id）+ pg_notify
- [x] 在 linux-server 真库执行验证（PG18 + pgvector 0.8.3，9 表 + 2 视图 + 2 HNSW 索引，全过）

## 后端 · 基础设施（`backend/`）

- [x] `config.py` 环境配置（AI 服务收敛成一套：`API_KEY`/`AI_BASE_URL`/`CHAT_MODEL`/`VISION_MODEL`/`EMBED_MODEL`）
- [x] `db.py` psycopg 连接池 + pgvector 注册
- [x] `main.py` FastAPI 入口（挂载 ingest，/health）
- [x] `requirements.txt`
- [x] **AI 接入策略层** `services/providers/`：`base.py` 抽象 LLMProvider/EmbeddingProvider + 共享数据模型；`glm.py` 智谱实现（glm-5.2 对话 + glm-4.6v 视觉 + embedding-3 向量）；`__init__.py` 工厂。`services/llm.py`、`services/embedder.py` 改为薄门面委托。配置即策略，换兼容 OpenAI 协议的 provider 只改配置
- [ ] 统一日志配置
- [ ] 全局异常处理器（输出契约规定的错误体）

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
- [x] **SSE 流式**：`POST /qa/stream` 用 `sse-starlette EventSourceResponse`；`glm.answer_stream` 走 `AsyncOpenAI` + `stream=True` + `thinking on`，事件序 `sources`→`token`→`done`；同步 `POST /qa` 保留兼容

## 后端 · 知识图谱（graph）

- [x] `routers/graph.py` `GET /graph`（查 entity_cooccurrence / entity_note_counts 视图，按类别筛选）
- [x] `GET /graph/entities/{id}` 实体详情 + 相关笔记
- [ ] （可选）typed relations 提取写入 relations 表

## 后端 · 笔记 / Wiki

- [x] `routers/notes.py` `GET /notes/{id}`（含实体/要点/正文分段）、`DELETE /notes/{id}`
- [ ] `GET /notes` 列表（分页 / 标签过滤）
- [x] `routers/wiki.py` `GET /wiki`、`GET /wiki/{slug}`（结构化 sections + conflict + 来源解析）
- [x] `POST /wiki/compile` 触发编译（`CompileRequest` + `BackgroundTasks`）+ `GET /wiki/{slug}/status` 读编译任务进度
- [x] `workers/compile_worker.py` 多笔记 → LLM 综合 → 写 wiki_pages（结构化 sections / conflict / summary / content / embedding / compiled_at）；`compile_wiki` 用 `response_format=json` + `reasoning_effort=max`

## 后端 · 鉴权 / 配额 / 管理员（`docs/auth-design.md`）

分阶段：0 HTTPS 前置 · **1 登录+全路由锁+admin 网关** · 2 配额 429 · 3 历史隔离 · 4 前端登录 · 5 admin 界面。

**阶段 1（代码完成，待真库验证）**
- [x] `sql/08_auth.sql`：`users`（email/bcrypt/role/daily_token_limit/is_active）+ `token_usage` 账本；`00_init.sql` 补挂 07/08
- [x] `services/auth.py`：bcrypt 哈希 + JWT(HS256) 签发/解码 + `get_current_user` / `require_admin` 依赖
- [x] `routers/auth.py`：`POST /auth/login`、`GET /auth/me`、`GET/POST /auth/users`、`PATCH /auth/users/{id}`（admin）
- [x] `main.py`：业务路由统一挂登录依赖；ingest 整组 `require_admin`；notes DELETE、wiki compile 单路由 `require_admin`
- [x] `config.py` + `.env.example`：`JWT_SECRET`/`JWT_EXPIRE_HOURS`/`DEFAULT_DAILY_TOKEN_LIMIT`/`USAGE_TZ`
- [x] `requirements.txt`：`pyjwt` + `passlib[bcrypt]` + `email-validator`
- [x] `scripts/create_admin.py`：引导首个管理员（幂等 upsert）
- [x] 契约 `docs/api-contract.md` 新增「8. 鉴权 Auth」+ 全局鉴权约定 + 权限标注
- [ ] 真库验证：建库灌 08、装新依赖、create_admin、login 取 token、带/不带 token 打接口验 401/403
- [ ] **HTTPS + 反代（阶段 0，鉴权上线前必须）**

**阶段 2（token 配额 429，代码完成）**
- [x] `services/usage.py`：ContextVar 累加器（`collect()` 上下文 + `record_call()`），与 provider 解耦
- [x] `services/providers/glm.py`：analyze/answer/answer_stream/describe_image/compile_wiki/embed 六处调用后 `usage.record_call`；流式加 `stream_options={"include_usage":true}` 取末尾 usage
- [x] `services/quota.py`：`today()`(按 USAGE_TZ) / `used_today` / `check_quota`(超额 429) / `record_usage`
- [x] `routers/qa.py`、`routers/search.py`：注入当前用户，调用前 `check_quota`、调用后 `record_usage`（qa/qa_stream 计 qa；search 仅 semantic/hybrid 计费）

**阶段 3（历史 user_id 隔离，代码完成）**
- [x] `sql/09_history_user.sql`：给 search_history/qa_history 加 `user_id`（FK + 索引，幂等迁移），挂进 00_init
- [x] `_save_history` 写入 user_id；`/search/history`、`/qa/history` 默认按当前用户过滤，admin `?scope=all` 看全部

**阶段 4（前端登录 + 守卫，代码完成）**
- [x] `lib/api.ts`：Bearer token（localStorage）+ 401 清 token 跳登录 + 429 归类 `rate_limited` + `apiPatch`
- [x] `components/AuthProvider.tsx`（/auth/me 引导 + 未登录守卫 + login/logout）+ `AppShell.tsx`（登录页全屏、其余套侧栏）
- [x] `app/login/page.tsx` 登录页；`layout.tsx` 包 AuthProvider/AppShell；`Sidebar` 按角色显示导航 + 用户 + 登出

**阶段 5（管理后台，代码完成）**
- [x] `app/admin/layout.tsx` 管理员守卫；入库页迁到 `app/admin/ingest`（删旧 `app/ingest`，根路由改跳 /search）
- [x] `app/admin/users` 用户管理（建号/改角色/改密码/停用）；`app/admin/usage` 用量看板
- [x] 后端 `GET /auth/usage`（admin）今日各用户用量 + 额度
- [x] 前端 `npm run build` 通过（13 路由，含 /admin/*）；后端 `py_compile` 全过
- [x] **linux-server 真库验证 + 上线**（2026-06-28）：灌 08/09、装依赖、create_admin、login 取 token、unauth 401、ingest admin、authed search/me/usage 200、前端 /login·/admin 200、错误密码 401。passlib 弃用改 bcrypt 直连
- [ ] **HTTPS + 反代（阶段 0）仍未做** —— 当前登录/JWT 走明文 HTTP，凭据可被中间人窃听，属上线后最高优先收尾项

## 后端 · 历史

- [x] `GET /search/history`（随检索功能完成）
- [x] `GET /qa/history`（随问答功能完成）

## 前端（`frontend/`）

- [x] 初始化 Next.js 16 + Tailwind v4 + TypeScript 工程
- [x] 接入 house style（色板 / 字体，见 CLAUDE.md §6）
- [x] 整体框架：侧边导航 Sidebar + 根布局 + /api 代理 + api 封装/类型
- [x] 入库页 ingest（链接/文件入库 + 队列进度轮询）
- [x] 检索页 search（搜索框 + 模式切换 + 标签云 + 结果卡片 + 高亮片段）
- [x] 笔记详情页 note（标题/来源/标签/摘要/要点/实体/正文，实体可跳图谱）
- [x] 问答页 qa（对话式 + 来源 chips + 思考态 + 建议问题）
- [x] 知识图谱页 graph（自写力导向布局 + 类别着色 + 实体侧栏）
- [x] 主题页 wiki（列表 + 详情：章节/引用角标/观点矛盾/来源）
- [x] 历史页 history（问答历史 + 搜索历史）

## 数据迁移 / 运维

- [x] `scripts/seed_demo.py` 灌入 6 篇示例笔记 + 9 实体 + 1 Wiki 主题页（无密钥也能演示检索/图谱/Wiki）
- [ ] `scripts/migrate_from_mywiki.py` 把 my-wiki 笔记导入（仅注释占位）

## 部署（linux-server）

- [x] PostgreSQL 18 + pgvector 0.8.3，建库 fuxi + 角色 fuxi，灌 schema（见 docs/deploy.md）
- [x] Redis 已就绪（127.0.0.1:6379）
- [x] 后端 + 前端部署在 linux-server（/opt/fuxi）：后端 127.0.0.1:8000，前端 0.0.0.0:19000 → http://118.25.93.30:19000
- [x] 入库链路真库端到端验证（抓取→提取→stage/progress→jobs→/api 代理→错误处理，全过）
- [x] 进程改 systemd：`fuxi-backend` / `fuxi-frontend`（enabled，开机自启 + Restart=always）
- [x] 填入 API_KEY 跑通完整入库（`/etc/profile` 注入 + systemd `bash -lc` 包裹使 key 对进程可见）
- [x] 装 Elasticsearch + ik 分词插件（Docker ES 8.17.6 + ik，绑 127.0.0.1:9200，容器 `fuxi-es`；部署文件见 `deploy/es/`）
- [ ] 反向代理 + HTTPS

---

## 文档

- [x] `README.md` 项目介绍
- [x] `DESIGN.md`（沿用 my-wiki 思路，待补 fuxi 版）— ⬜ fuxi 专属设计文档
- [x] `docs/api-contract.md` 接口契约
- [x] `CLAUDE.md` 工作规则与规范
- [x] `PROGRESS.md` 本文件

---

## 更新日志

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
