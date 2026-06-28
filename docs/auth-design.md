# fuxi 用户体系 / 配额 / 管理员 —— 设计文档

> 状态：阶段 1 实施中。本文件是鉴权相关改动的单一设计真相，接口细节同步进
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
| `GET /graph`、`/wiki`、`/notes/{id}`、`/tags` | ✅ | ✅ | `get_current_user` |
| `GET /search/history`、`/qa/history` | ✅ 仅自己 | ✅ 可看全部 | `get_current_user` |
| `POST /ingest/url`、`/ingest/file`、`GET /ingest/jobs` | ❌ | ✅ | `require_admin` |
| `DELETE /notes/{id}`、`POST /wiki/compile` | ❌ | ✅ | `require_admin` |
| `/auth/users*`（建号/改额度/停用） | ❌ | ✅ | `require_admin` |

普通用户账号**仅管理员建号**，不开放自助注册。

## 数据库（sql/08_auth.sql）

- `users`：email + bcrypt `password_hash` + `role`(member/admin) + `daily_token_limit`
  (NULL=用 config 默认) + `is_active`。
- `token_usage`：用量明细账本（user_id, usage_day, operation, prompt/completion/total_tokens）。
  `usage_day` 按 `USAGE_TZ` 算的自然日，便于按天聚合 + 索引稳定。
- 阶段 3 给 `search_history` / `qa_history` 加 `user_id`（本文件先登记，代码在阶段 3）。

配额查询：`SELECT COALESCE(SUM(total_tokens),0) FROM token_usage WHERE user_id=? AND usage_day=?`。

## 后端

- 依赖：`pyjwt`、`passlib[bcrypt]`。
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

- **前置：HTTPS + 反代**。明文 HTTP 下传密码/JWT 形同裸奔，须先上。
- `scripts/create_admin.py` 引导第一个管理员。
- 新增 env：`JWT_SECRET` / `JWT_EXPIRE_HOURS` / `DEFAULT_DAILY_TOKEN_LIMIT` / `USAGE_TZ`。

## 分阶段

| 阶段 | 内容 |
|--|--|
| 0 | HTTPS + 反代（运维前置） |
| **1** | schema + auth 后端 + 引导 admin + 全路由锁登录 ← 本次 |
| 2 | providers 透出 usage + 配额 429 |
| 3 | history 加 user_id 隔离 |
| 4 | 前端登录 + 守卫 + 401/429 |
| 5 | admin 界面（迁入库 + 用户/用量看板） |

## 决策记录

- 注册方式：仅管理员建号。
- 超额行为：硬性 429（次日 0 点按 USAGE_TZ 重置）。
- token 存放：**localStorage + Bearer 头**（前端纯 client 组件，最简可用）。权衡：易受 XSS 取走 token，已靠 React 默认转义 + 无第三方注入降低风险；公网务必配 HTTPS。若日后要更强隔离，可改 httpOnly cookie（需加 Next 路由处理器写 cookie）。
- 用量计费：member 的 qa/search 计费即可控预算；ingest 为 admin 不限，用量仍记账供看板展示（当前 ingest worker 在 BackgroundTasks 中跑、未串当前用户，故 ingest 的 token **暂未入账**，看板只反映 qa/search —— 后续如需 ingest 计量再把 admin user_id 透传进 worker）。
