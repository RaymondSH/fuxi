# fuxi 用户体系 / 配额 / 管理员 —— 设计文档

> 状态：阶段 1-5 + M0 安全核心（步骤 1-5）已完成并上线；M1 增加 MCP API token（独立于 JWT，供 Agent 接入）；
> **M2 增加空间（Spaces）双层角色模型**（系统级 users.role + 空间级 space_members.role），内容按空间隔离，
> 详见 [spaces-design.md](spaces-design.md)。本文件是鉴权相关改动的单一设计真相，接口细节同步进
> [api-contract.md](api-contract.md)，进度同步进 [../PROGRESS.md](../PROGRESS.md)。

## 背景

线上 `118.25.93.30:19000` 此前零鉴权：任何人都能入库（烧 GLM token）、跑 RAG、
`DELETE /api/notes/{id}` 删笔记。本设计加用户登录、按用户隔离历史、按用户限每日
token，并把入库等策展操作收进管理员角色。

数据模型本质是**共享语料**：notes / entities / graph / wiki 全局无 owner，检索 / 问答
跨全库。只有 history 两张表按用户才有意义。因此走「管理员策展、普通用户消费」的
两角色模型，而非「每人私有笔记」的多租户（后者要给 notes 加 owner、全链路按 user
过滤，逆现有架构）。

## 角色与权限

| 接口 | member | admin | 依赖 |
|------|:--:|:--:|------|
| `POST /auth/login`、`GET /auth/me` | ✅ | ✅ | 公开 / 登录 |
| `POST /search`、`POST /qa`、`POST /qa/stream` | ✅ | ✅ | `get_current_user` |
| `GET /graph`、`/wiki`、`/notes`、`/notes/{id}`、`/tags` | ✅ | ✅ | `get_current_user` |
| `GET /notes/{id}/qa` | ✅ | ✅ | `get_current_user` |
| `GET /search/history`、`/qa/history` | ✅ 仅自己 | ✅ 可看全部 | `get_current_user` |
| `POST /ingest/url`、`/ingest/file`、`GET /ingest/jobs` | ❌ | ✅ | `require_admin` |
| `POST /notes/{id}/generate-qa` | ❌ | ✅ | `require_admin` |
| `DELETE /notes/{id}`、`POST /wiki/compile` | ❌ | ✅ | `require_admin` |
| `/tags/vocab`、`POST /tags`、`PATCH /tags/{name}`、`POST /tags/merge` | ❌ | ✅ | `require_admin` |
| `/auth/users*`（建号/改额度/停用） | ❌ | ✅ | `require_admin` |
| `/mcp-admin/tokens*`（颁发/停用/删 token） | ❌ | ✅ | `require_admin` |
| `POST /mcp`（MCP streamable HTTP） | — | — | Bearer MCP token（非 JWT，见下） |

普通用户账号**仅管理员建号**，不开放自助注册。

### M2 空间双层角色（见 [spaces-design.md](spaces-design.md)）

上面是**系统级**角色（`users.role`：member/admin）。M2 引入**空间级**角色正交于系统级：

- 系统级 `admin` = sysadmin，对全部空间天然有 `space_admin` 权限（不写 `space_members` 行）。
- 空间级 `space_members.role`：`viewer`（只读）/ `editor`（+入库/编辑/生成Q&A）/ `space_admin`（+管成员/编译wiki/删笔记）。一用户在不同空间可有不同角色。
- 写操作从「全局 `require_admin`」改成「空间作用域角色校验」（`spaces.assert_note_role`）：空间管理员即可删本空间笔记、编译本空间 wiki，不必是 sysadmin。
- 内容按空间隔离：笔记 / wiki / MCP token 都归属一个空间，读写按空间 ACL 过滤（`visible_space_ids` + `space_filter_from` 注入到每条查询）。

### MCP token（与登录 JWT 分开）

`/mcp` 端点给 LLM Agent 调用，不归属某个登录用户、不挂全局 `get_current_user`，也不计入 `token_usage` 配额。它走独立的 **MCP API token**：

- 管理员在 `/api/mcp-admin/tokens` 颁发，明文仅创建时返回一次，库里存 bcrypt 哈希 + 前 8 位前缀
- 客户端以 `Authorization: Bearer <mcp_token>` 调 `/mcp`，由 `mcp_server._auth_wrapper` 在 streamable_http_app 前校验
- 可随时启停（`is_active`）或删除，立即失效

设计动机：MCP SDK 自带的 TokenVerifier 走完整 OAuth 2.1（AS 端点 + client 注册 + PKCE），对「单进程、管理员手动发 token」过重；裸 ASGI 包装做 Bearer 校验与 fuxi 既有鉴权一致。详见 [mcp.md](mcp.md)。

## 数据库（sql/08_auth.sql）

- `users`：email + bcrypt `password_hash` + `role`(member/admin) + `daily_token_limit`
  (NULL=用 config 默认) + `is_active`。
- `token_usage`：用量明细账本（user_id, usage_day, operation, prompt/completion/total_tokens）。
  `usage_day` 按 `USAGE_TZ` 算的自然日，便于按天聚合 + 索引稳定。
- 阶段 3 给 `search_history` / `qa_history` 加 `user_id`（本文件先登记，代码在阶段 3）。

配额查询：`SELECT COALESCE(SUM(total_tokens),0) FROM token_usage WHERE user_id=? AND usage_day=?`。

## 后端

- 依赖：`pyjwt`、`bcrypt`（直接用 bcrypt 库，弃 passlib：后者已停更且与 bcrypt>=4.1 不兼容）。
- `config.py`：`JWT_SECRET`(必填) / `JWT_EXPIRE_HOURS` / `DEFAULT_DAILY_TOKEN_LIMIT` / `USAGE_TZ`。
- `services/auth.py`：bcrypt 哈希/校验、JWT 签发/解码、`get_current_user`、`require_admin` 依赖。
- `services/quota.py`（阶段 2）：`check_quota` 超限抛 429、`record_usage` 写账本。
- `routers/auth.py`：login / me / 用户管理（admin）。
- `main.py`：业务路由统一挂 `get_current_user`；入库整组挂 `require_admin`；
  notes DELETE、wiki compile 单路由挂 `require_admin`。

错误体沿用现有风格（`HTTPException(detail=...)`），与既有路由一致；统一错误体是另一项
独立待办（PROGRESS「全局异常处理器」）。

## 前端（阶段 4）

`/login` 页 + auth context + 根布局重定向；导航对 member 隐藏「入库」，admin 多 `/admin`
分区；`lib/api.ts` 带 token、拦 401 跳登录 / 429 提示额度用完。

## 部署

- `scripts/create_admin.py` 引导第一个管理员。
- 新增 env：`JWT_SECRET` / `JWT_EXPIRE_HOURS` / `DEFAULT_DAILY_TOKEN_LIMIT` / `USAGE_TZ`。

## 分阶段

| 阶段 | 内容 |
|--|--|
| **1** | schema + auth 后端 + 引导 admin + 全路由锁登录 ← 本次 |
| 2 | providers 透出 usage + 配额 429 |
| 3 | history 加 user_id 隔离 |
| 4 | 前端登录 + 守卫 + 401/429 |
| 5 | admin 界面（迁入库 + 用户/用量看板） |

### M0 安全核心（步骤 1-5）

| 步骤 | 内容 |
|--|--|
| 1 | 结构化 JSON 日志 + 全局异常中间件（`services/logging.py` + `CatchErrorsMiddleware`） |
| 2 | 备份/灾备脚本（pg_dump + 原始文件 tar，systemd timer 每日 03:00，14 天保留） |
| 3 | 审计日志（`audit_log` 表 + `services/audit.py` 双写 DB + 结构化日志，登录/建号/改密/入库/编译/删除埋点） |
| 4 | 账号安全（密码强度校验、失败 5 次锁定 15min、自助改密 `/auth/change-password`） |
| 5 | JWT 双 token + 撤销（access 15min + refresh 7d，登出/改密/停用撤销） |

## 决策记录

- 注册方式：仅管理员建号。
- 超额行为：硬性 429（次日 0 点按 USAGE_TZ 重置）。
- token 存放：Web 使用 **httpOnly + SameSite=Lax Cookie**，JS 不持久化 token；移动端使用 SecureStore + Bearer。后端严格区分 `type=access` 与 `type=refresh`，refresh 不能作为业务凭证。
- 用量计费：member 的 qa/search 计费即可控预算；ingest 为 admin 不限，用量仍记账供看板展示。HTTP 入库接口把触发者 `admin.id` 作为 `actor_id` 透传进 `ingest_worker.run`，worker 在 `usage.collect()` 块内跑完 fetch/analyze/embed（含图片入库的 `describe_image`）后 `quota.record_usage(actor_id, "ingest", u)` 落账；脚本/迁移同步入口不传 `actor_id`，不记账。
- 密码策略：≥8 位 + 必含字母 + 必含数字（`auth.validate_password`，建号/改密统一校验，不再用 Pydantic `min_length`）。
- 登录锁定：失败达 `LOGIN_MAX_ATTEMPTS`（默认 5）→ 锁 `LOGIN_LOCK_MINUTES`（默认 15），同一事务 SELECT+UPDATE 防并发；锁定期内不区分账号是否存在，统一 `423`，避免泄露账号存在性。
- **双 token + 撤销（步骤 5）**：access 15min（带 `jti`）+ refresh 7d（落 `refresh_tokens` 表）。Web 双 token 只进 httpOnly Cookie，移动端存 SecureStore 并走 Bearer。登出撤销 refresh + 拉黑当前 access；改密/停用撤销全部 refresh，`password_changed_at` 同时令此前签发的全部 access 失效。前端 401 时单飞 refresh + 重试一次。**不做 refresh 轮换**，若日后检测到重放风险再增加轮换。
