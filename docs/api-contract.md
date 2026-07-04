# fuxi 前后端接口契约

本文档以前端设计稿（`Fuxi 知识库 (standalone).html`）的真实数据模型为准，定义前后端接口。
设计稿是静态 demo（数据是组件里的 mock，无真实请求），下面的接口就是要把这些 mock 替换成真实后端。

## 页面 → 接口总览

| 前端页面 | 主要接口 |
|----------|----------|
| 检索 search / 结果 results | `POST /api/search`、`GET /api/tags` |
| 笔记列表 notes | `GET /api/notes` |
| 笔记详情 note | `GET /api/notes/{id}`、`POST /api/notes/{id}/generate-qa`（admin）、`GET /api/notes/{id}/qa` |
| 问答 qa | `POST /api/qa`、`POST /api/qa/stream`、`GET /api/qa/history` |
| 知识图谱 graph | `GET /api/graph`、`GET /api/graph/entities/{id}` |
| 主题页 wiki | `GET /api/wiki`、`GET /api/wiki/{slug}` |
| 入库 ingest | `POST /api/ingest/url`、`POST /api/ingest/file`、`GET /api/ingest/jobs` |
| 标签治理 admin/tags | `GET /api/tags/vocab`、`POST /api/tags`、`PATCH /api/tags/{name}`、`POST /api/tags/merge` |
| 历史 history | `GET /api/search/history`、`GET /api/qa/history` |
| MCP 管理 admin/mcp | `GET/POST/PATCH/DELETE /api/mcp-admin/tokens` |
| 空间管理 spaces | `GET/POST/PATCH/DELETE /api/spaces`、`/api/spaces/{id}/members` |
| Agent 接入 | `POST /mcp`（Bearer MCP token，非 JWT） |

---

## 通用约定

- **Base URL**：`/api`
- **鉴权**：Web 使用 httpOnly Cookie（`fuxi_access` / `fuxi_refresh`）；移动端使用 `Authorization: Bearer <access_token>` + SecureStore。除 `POST /api/auth/login`、`POST /api/auth/refresh` 外，所有 `/api` 接口都需有效 access token；refresh token 不能调用业务接口。缺失/过期/无效/已撤销返回 `401`，权限不足返回 `403`，超每日额度返回 `429`。access 有效期 15min，过期后自动用 refresh（7d）换新 access 并重试。
- **格式**：请求/响应均为 JSON（文件上传用 `multipart/form-data`）
- **时间**：存储用 ISO 8601（`2026-06-20T09:14:00Z`）；前端展示的「2 分钟前 / 昨天」由前端格式化，但接口同时返回 `created_at`（绝对时间）和 `relative`（相对文案）两个字段，前端可直接用 `relative`
- **分页**：`?page=1&size=20`，响应带 `{ total, page, size }`
- **错误**：

```json
{ "error": { "code": "not_found", "message": "笔记不存在" } }
```

- **异步任务**：入库 / Wiki 编译 / Q&A 生成只写 `jobs` 队列并立即返回 202；独立 worker 用 `FOR UPDATE SKIP LOCKED` 消费，服务重启后会重新排队未完成任务。前端轮询 job 状态。

---

## 枚举字典

集中定义所有枚举，前后端共用。

| 枚举 | 取值 | 说明 |
|------|------|------|
| `user.role` | `member` `admin` | 系统角色；admin=sysadmin 管用户/MCP token/全局看板，member 只能被加进空间 |
| `space_member.role` | `viewer` `editor` `space_admin` | 空间内角色（M2）：viewer 只读 / editor +入库编辑生成Q&A / space_admin +管成员编译wiki删笔记。sysadmin 对全部空间天然是 space_admin |
| `note.type` | `link` `pdf` `word` `excel` `image` | 来源类型；前端据此显示角标（LINK/PDF/WORD/XLSX/IMG·OCR） |
| `search.mode` | `hybrid` `keyword` `semantic` | 混合 / 关键词 / 语义检索 |
| `time_filter` | `all` `today` `week` `month` `year` | 时间筛选 |
| `entity.cat` | `concept` `product` `company` | 实体类别；前端据此着色（绿/赭/蓝） |
| `ingest.status` | `pending` `processing` `done` `failed` | 入库任务总状态 |
| `ingest.stage` | `queued` `fetch` `extract` `refine` `embedding` `store` `done` | 入库流水线阶段（细粒度，驱动进度条） |

> 注：前端 mock 里实体类别用了缩写 `cat`、笔记要点用 `keypoints`、来源用 `source`。本契约统一采用下面的字段名，前端对接时按「字段映射」小节调整。

---

## 1. 笔记 Notes

### `GET /api/notes/{id}` — 笔记详情

驱动「笔记详情」页。对应 mock 里 `notes[]` 的单条。

**响应：**

```json
{
  "id": "n2",
  "type": "pdf",
  "title": "RAG 分块策略实战：从固定窗口到语义切分",
  "source": "report.pdf · 24页",
  "url": "https://...",
  "date": "2026-05-14",
  "tags": ["RAG", "检索", "Embedding", "分块"],
  "entities": [
    { "id": "e_rag", "name": "RAG", "cat": "concept" },
    { "id": "e_emb", "name": "Embedding", "cat": "concept" }
  ],
  "summary": "系统对比固定长度、滑动窗口、递归字符与语义切分四类分块策略……",
  "keypoints": [
    "固定窗口实现简单但易切断语义单元，召回波动大",
    "递归字符切分按结构层级回退，是工程上的稳健默认"
  ],
  "original": [
    "分块（chunking）是 RAG 流水线里最被低估的一环……",
    "固定长度切分是最简单的基线……"
  ],
  "related_note_ids": ["n6", "n3"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | enum | 见枚举字典 |
| `source` | string | 来源展示文案（域名 / 文件名+页数） |
| `entities` | object[] | 实体对象（带 id，前端可点击跳图谱），mock 里原本是纯字符串数组 |
| `keypoints` | string[] | 要点 |
| `original` | string[] | 正文，按段落切分的数组 |
| `related_note_ids` | string[] | 关联笔记（related 字段） |

### `GET /api/notes` — 笔记列表

`?page=1&size=20&type=&tag=&q=`，按创建时间倒序，仅返回 `ingest_status='done'`。响应：

```json
{
  "items": [
    { "id": "...", "type": "pdf", "title": "...", "source": "report.pdf · 24页",
      "date": "2026-05-14", "tags": ["RAG","检索"], "summary": "……" }
  ],
  "total": 14, "page": 1, "size": 20
}
```

`type` 取值 `link/pdf/word/excel/image`；`tag` 单标签精确过滤（`%s = ANY(tags)`）；`q` 标题/摘要模糊匹配。

### `POST /api/notes/{id}/generate-qa` — 触发文档→Q&A 生成（admin）

把一篇笔记变成多组问答对沉淀进 `generated_qa` 表（带 question 向量），供问答时回灌检索。返回 `202 {"note_id":"...","status":"pending"}`，后台跑 `qa_gen_worker`。

### `GET /api/notes/{id}/qa` — 该笔记已生成的问答对

```json
{ "items": [ { "question": "什么是递归字符切分？", "answer": "按结构层级回退的切分策略……" } ] }
```

---

## 2. 入库 Ingest

### `POST /api/ingest/url` — 链接入库

```json
// 请求（space_id 可选，缺省走当前 active space；M2 空间隔离）
{ "url": "https://mp.weixin.qq.com/s/xxx", "space_id": "uuid-of-space" }
// 响应 202
{ "note_id": "n7", "status": "pending" }
```

> M2 后入库需对目标空间有 `editor` 角色（不再是 sysadmin only）；笔记写入 `notes.space_id` / `notes.created_by`。

### `POST /api/ingest/file` — 文件入库

`multipart/form-data`，字段 `file` + 可选 `space_id`（query param）。支持 pdf/docx/xlsx/图片。响应同上。

### `GET /api/ingest/jobs` — 入库队列

驱动「入库」页的任务列表。返回**进行中 + 最近完成**的任务。

```json
{
  "items": [
    {
      "id": "i2",
      "note_id": "n8",
      "type": "pdf",
      "title": "2026-Q2-AI-infra-report.pdf",
      "sub": "14.2 MB · 38 页",
      "stage": "embedding",
      "progress": 62,
      "status": "processing"
    },
    {
      "id": "i4",
      "note_id": "n9",
      "type": "image",
      "title": "whiteboard-photo.jpg",
      "sub": "OCR 待处理 · 2.1 MB",
      "stage": "queued",
      "progress": 0,
      "status": "pending"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `stage` | 细粒度阶段，驱动进度条文案：抓取→解析→提炼→向量化→写库 |
| `progress` | 0–100 |
| `sub` | 副标题（文件大小/页数/来源） |

> 前端 demo 里用 `setInterval` 模拟阶段推进。真实接口前端改为**轮询 `GET /api/ingest/jobs`（每 1–2s）**，或后续升级为 SSE/WebSocket 推送。
>
> `ingest_worker.py` 在各步骤间更新 `jobs` 表的细粒度 `stage`（queued→fetch→extract→refine→chunk→embedding→store→done）与 `progress`（0–100）；独立 `job_runner` 消费队列，长文档逐块向量化写入 `note_chunks`。

### `GET /api/ingest/jobs/{id}` — 单个任务状态

单条轮询用，响应同 `items` 里的单个对象，外加 `error_msg`（失败时）。

---

## 3. 检索 Search

### `POST /api/search`

关键词、语义与混合检索返回的是最多 100 条候选组成的有界排序窗口，`total`
表示该窗口内实际可分页的结果数；标签浏览模式使用数据库精确 `COUNT(*)`。

驱动「检索 / 结果」页。同时**写入搜索历史**。

```json
// 请求
{
  "q": "RAG 分块策略",
  "mode": "hybrid",
  "tags": ["RAG", "检索"],
  "time_filter": "all",
  "page": 1,
  "size": 20
}
// 响应
{
  "query": "RAG 分块策略",
  "mode": "hybrid",
  "took_ms": 42,
  "total": 6,
  "results": [
    {
      "id": "n2",
      "type": "pdf",
      "title": "RAG 分块策略实战：从固定窗口到语义切分",
      "source": "report.pdf · 24页",
      "date": "2026-05-14",
      "tags": ["RAG", "检索", "Embedding", "分块"],
      "summary": "系统对比固定长度、滑动窗口……",
      "score": 0.92,
      "snippet": "……<em>分块</em>策略直接影响召回，递归字符切分是稳健的默认……"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `score` | 融合后排序分（hybrid 用 RRF/加权；前端可选展示） |
| `snippet` | 命中片段，关键词用 `<em>` 高亮 |
| `took_ms` | 耗时，对应搜索历史里的展示 |

> **混合检索**：`mode=hybrid` 时后端并行跑关键词（Elasticsearch/PG 全文）和语义（pgvector），用 RRF 融合。这正是 demo 里反复强调的逻辑。
>
> **按标签浏览**：`q` 为空但 `tags` 非空时，后端按标签（+时间）过滤返回笔记（按时间倒序，不打分、不调 LLM、不计费），响应 `mode` 返回 `"tag"`。前端点击标签云即触发此路径（无需先输入关键词）。`q` 与 `tags` 都为空才返回空结果。

### `GET /api/tags` — 标签云

驱动检索页的标签筛选 chips。

```json
{ "items": [ { "name": "RAG", "count": 4 }, { "name": "检索", "count": 3 } ] }
```

> 词表别名会在此处归并：某标签若是受控词表里某规范名的别名，回显为规范名并并入计数。

### 标签治理（admin）—— 受控词表 + 归并

| 接口 | 说明 |
|------|------|
| `GET /api/tags/vocab` | 受控词表全量：`name / aliases / description / status(active/merged/deprecated) / merged_into` |
| `POST /api/tags` | 新建规范标签或补别名；name 与现有规范名/别名冲突 `409` |
| `PATCH /api/tags/{name}` | 改 aliases / description / status / merged_into |
| `POST /api/tags/merge` | 归并：物理回写所有 `notes.tags`（`from_tag`→`to_tag`，`array_replace`）+ 同步 ES 索引；词表标 `from_tag` 为 `merged`，返回 `{affected_notes, from, to}` |

> 设计：`notes.tags` 仍是自由 `TEXT[]`；受控词表（`tags` 表）只管规范名 + 别名 + 状态。归并走物理回写而非读时映射（查询路径多，读时映射易漏）。`status` 的权重排序进检索留到 M3。

### `GET /api/search/suggestions?q=长上下文` — 联想（可选）

对应 demo 里的 `suggestChips`，返回 `{ items: ["长上下文会取代 RAG 吗", "..."] }`。

---

## 4. 问答 QA（RAG）

### `POST /api/qa`

驱动「问答」页。基于知识库检索 + LLM 生成带来源的回答。

```json
// 请求（history 传多轮上下文；style 选输出风格）
{
  "question": "混合检索比单路能提升多少召回？",
  "history": [
    { "role": "user", "text": "什么是混合检索？" },
    { "role": "assistant", "text": "……" }
  ],
  "style": "default"
}
// 响应
{
  "answer": "综合知识库里的 3 条来源……混合检索通常比单路提升 **15–25% 的召回**……",
  "sources": [
    { "id": "n6", "title": "语义检索 vs 关键词检索", "type": "link" },
    { "id": "n5", "title": "Elasticsearch 中文分词 ik 插件实践", "type": "word" }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `style` | `default`（默认）/ `executive`（高管摘要）/ `technical`（技术深度）/ `eli5`（讲给外行）；非法值回退 `default`。仅改输出措辞，不改事实约束 |
| `answer` | Markdown，前端按 `\n\n` 分段、渲染 `**加粗**` |
| `sources` | 引用来源，前端显示「N 条来源」并可点击跳笔记 |

> **流式已实现**：`POST /api/qa/stream` 走 SSE，事件序 `sources`（检索结果）→ `token`（逐块回答）→ `done`（含是否真生成）；前端 `lib/sse.ts` 用 fetch POST + ReadableStream 手动解析 SSE 帧逐字渲染，对应 demo 里的 `thinking` 状态。流式同样支持 `style` 字段。普通模式 `POST /api/qa` 仍保留一次性返回。
>
> **Q&A 回灌检索**：问答时除了检索笔记，还会从 `generated_qa` 表按 question 向量取最相似的 2 条历史问答对，拼进上下文作为「已沉淀问答」，让模型复用同义问题的既有答案（`POST /notes/{id}/generate-qa` 生成）。

### `GET /api/qa/history` — 问答历史

```json
{
  "items": [
    {
      "id": "q1",
      "question": "混合检索比单路能提升多少召回？",
      "answer_preview": "综合 3 条来源，hybrid 检索通常比单路提升 15–25% 召回…",
      "source_count": 3,
      "created_at": "2026-06-27T09:55:00Z",
      "relative": "5 分钟前"
    }
  ]
}
```

对应 mock 的 `qaHistory[{q,a,srcN,when}]`：`q→question`、`a→answer_preview`、`srcN→source_count`、`when→relative`。

---

## 5. 知识图谱 Graph

### `GET /api/graph?filter=all`

驱动「知识图谱」页。`filter` 可选 `all` / `concept` / `product` / `company`。

```json
{
  "nodes": [
    { "id": "e_rag", "name": "RAG", "cat": "concept", "count": 4 },
    { "id": "e_emb", "name": "Embedding", "cat": "concept", "count": 3 },
    { "id": "e_anthropic", "name": "Anthropic", "cat": "company", "count": 1 }
  ],
  "edges": [
    ["e_rag", "e_emb"],
    ["e_rag", "e_pgv"]
  ]
}
```

| 字段 | 说明 |
|------|------|
| `count` | 实体被多少篇笔记提及；前端据此算节点半径 `r` |
| `edges` | 实体共现关系，二元组 `[from_id, to_id]` |

> **坐标不由后端给**：mock 里的 `x/y/r` 是写死的布局。真实接口只返回 `nodes + edges + count`，**节点坐标由前端用力导向布局（D3 force / 类似）实时计算**，半径由 `count` 映射。后端只负责「谁和谁有关系、被提及多少次」。

### `GET /api/graph/entities/{id}` — 实体详情

点击节点时调用，返回该实体 + 相关笔记。对应 mock 的 `entityNotes`。

```json
{
  "entity": { "id": "e_rag", "name": "RAG", "cat": "concept", "count": 4, "aliases": ["检索增强生成"] },
  "notes": [
    { "id": "n2", "title": "RAG 分块策略实战", "type": "pdf", "date": "2026-05-14" },
    { "id": "n6", "title": "语义检索 vs 关键词检索", "type": "link", "date": "2026-05-28" }
  ]
}
```

---

## 6. 主题页 Wiki

### `GET /api/wiki` — 主题列表

```json
{ "items": [ { "slug": "rag", "title": "检索增强生成（RAG）", "updated": "2026-06-20", "source_count": 5 } ] }
```

### `GET /api/wiki/{slug}` — 主题详情

驱动「主题页」。对应 mock 的 `wiki` 对象。

```json
{
  "slug": "rag",
  "title": "检索增强生成（RAG）",
  "updated": "2026-06-20",
  "source_ids": ["n2", "n6", "n3", "n5", "n1"],
  "sections": [
    {
      "heading": "什么是 RAG",
      "paragraphs": [
        { "text": "检索增强生成把外部知识库的检索结果作为上下文……", "cites": ["n6"] }
      ]
    },
    {
      "heading": "检索：关键词 vs 语义 vs 混合",
      "paragraphs": [
        { "text": "关键词检索精确但脆弱，语义检索鲁棒但可能漂移……", "cites": ["n6", "n5"] }
      ]
    }
  ],
  "conflict": {
    "topic": "长上下文是否会取代 RAG？",
    "sides": [
      { "note_id": "n1", "claim": "Claude Opus 4.8 的 1M 上下文窗口让「单文档问答无需 chunking」……" },
      { "note_id": "n6", "claim": "对大规模、动态更新的语料，检索仍不可替代……" }
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| `sections[].paragraphs[].cites` | 该段落引用的笔记 id，前端渲染成可点击的来源角标 |
| `conflict` | 编译时 LLM 标出的观点矛盾（mock 里是 `a/b` 两方，这里统一成 `sides[]` 数组，便于扩展到多方） |

---

## 7. 历史 History

### `GET /api/search/history`

```json
{
  "items": [
    {
      "id": "s1",
      "q": "RAG 分块策略",
      "mode": "hybrid",
      "hits": 6,
      "created_at": "2026-06-27T09:58:00Z",
      "relative": "2 分钟前"
    }
  ]
}
```

对应 mock 的 `searchHistory[{q,mode,hits,when}]`，点击可重跑检索（前端再调 `POST /api/search`）。

### `GET /api/qa/history`

见「问答 QA」章节。

---

## 8. 鉴权 Auth

> 系统不开放自助注册，账号由管理员创建（首个管理员用 `scripts/fuxi.py admin` 引导）。
> 权限模型见 [architecture.md](architecture.md)。

### `POST /api/auth/login` — 登录（公开）

`identifier` 可填**用户名或邮箱**，二者皆可登录。返回双 token：access（15min，业务请求带）+ refresh（7d，仅用于换 access）。

```json
// 请求
{ "identifier": "zhangsan | user@example.com", "password": "******" }
// 响应
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "user": { "id": "...", "username": "zhangsan", "email": "user@example.com",
            "display_name": "张三", "role": "member",
            "daily_token_limit": 100000, "is_active": true }
}
```

`daily_token_limit` 返回**有效额度**：admin 返回 `null`（不限）；member 返回 `users.daily_token_limit`，未设则返回 `DEFAULT_DAILY_TOKEN_LIMIT`。`GET /auth/me` 同此。

账号或密码错误一律
`401 {"error":{"code":"unauthorized","message":"账号或密码错误"}}`
（不区分账号是否存在）；账号停用返回 `403`。连续失败达阈值（默认 5 次）后锁定，
密码正确时返回
`423 {"error":{"code":"locked","message":"账号已锁定，请稍后再试"}}`。
锁定期默认 15 分钟；密码错误时仍统一返回 `401`，不通过状态码泄露账号是否存在或是否被锁。

### `POST /api/auth/refresh` — 刷新 access token（公开）

access 过期后，前端用 refresh 换新 access（refresh 本身不轮换，7 天内可复用）。前端在任意请求收到 401 时自动触发，单飞（并发 401 只换一次）并重试原请求。

```json
// 请求
{ "refresh_token": "<jwt>" }
// 响应
{ "access_token": "<jwt>", "token_type": "bearer" }
```

refresh 无效/被撤销/已过期 `401`；用户被停用 `401`。此时前端清双 token 跳登录页。

### `POST /api/auth/logout` — 登出（需登录）

撤销 refresh token（`refresh_tokens.revoked_at` 置位）+ 把当前 access 的 `jti` 写入 `token_revocations` 黑名单，真正登出（而非仅清前端）。

```json
// 请求
{ "refresh_token": "<jwt>" }
// 响应：204 No Content
```

access 黑名单行在其自然过期后失效（无需清理）；refresh 一次撤销后不可再用。

### `POST /api/auth/change-password` — 自助改密（需登录）

```json
// 请求
{ "old_password": "******", "new_password": "******" }
// 响应：204 No Content
```

旧密码错误 `401`；新密码与旧密码相同 `400`；新密码不满足强度（≥8 位 + 含字母 + 含数字）`400`。
改密后刷新 `password_changed_at` 写审计，并**撤销该用户所有 refresh token + 拉黑当前 access**（强制重登，新密码生效）。

### `GET /api/auth/me` — 当前用户（需登录）

返回 `UserOut`（同上 `user` 对象）。

### `GET /api/auth/users` — 用户列表（admin）

`{ "items": [UserOut, ...] }`。

### `GET /api/auth/usage` — 今日用量总览 + 趋势 + 告警（admin）

驱动管理员「用量看板」。`?days=7`（1–90）控制趋势窗口。返回各用户当日 token 消耗与有效额度，外加组织今日合计、近 N 天趋势、≥80% 额度告警。

```json
{
  "tz": "Asia/Shanghai",
  "items": [
    { "id": "...", "email": "u@x.com", "display_name": "李四",
      "role": "member", "limit": 100000, "used_today": 32140 }
  ],
  "org_today": 32140,
  "org_trend": [ { "day": "2026-06-22", "total": 0 }, { "day": "2026-06-28", "total": 32140 } ],
  "alerts": [ { "id": "...", "email": "u@x.com", "display_name": "李四",
                "used_today": 82140, "limit": 100000, "pct": 82 } ]
}
```

`limit` 为 `null` 表示不限（admin）；`used_today` 按 `tz` 自然日聚合 `token_usage`（`operation` 含 `qa`/`search`/`ingest`/`compile`/`qa_gen`）。`org_trend` 补齐缺日（无消耗补 0）保证折线连续；`alerts` 仅含有限额且当日已达 80% 的用户。

### `POST /api/auth/users` — 建号（admin）

```json
// 请求
{ "username": "lisi", "email": "u@x.com", "password": "至少6位",
  "display_name": "李四", "role": "member", "daily_token_limit": null }
// 响应 201：UserOut
```

`username` 必填（≥2 位，唯一，登录可用）；`daily_token_limit` 为 `null` 表示用服务端默认（`DEFAULT_DAILY_TOKEN_LIMIT`）；邮箱或用户名重复 `409`。

### `PATCH /api/auth/users/{id}` — 改用户（admin）

可改 `username` / `display_name` / `role` / `daily_token_limit` / `is_active` / `password`（任意子集）。用户名/邮箱冲突 `409`。
管理员不能停用自己（`400`）。响应 `UserOut`。

### 权限标注（在各章节接口上生效）

> M2 后写操作的角色校验落在**空间维度**：空间管理员（`space_admin`）即可删本空间笔记、编译
> 本空间 wiki，不必是 sysadmin。读接口的可见范围由服务端按用户所属空间推导（不收客户端传的
> space_id）：sysadmin 全可见，普通用户只见其成员空间内的内容。

| 接口 | 权限 |
|------|------|
| `POST /ingest/url`、`POST /ingest/file`、`GET /ingest/jobs` | 目标空间 **editor+**（M2；原 admin only） |
| `DELETE /notes/{id}`、`POST /notes/{id}/generate-qa` | 该笔记所属空间：删除 **space_admin**、生成 Q&A **editor**（M2；原 admin only） |
| `POST /wiki/compile` | 所有来源笔记同空间 + 调用者该空间 **space_admin** |
| 检索 / 问答 / 图谱 / 笔记列表·详情 / wiki 读 | 登录即可，结果按用户可见空间过滤（M2） |
| `GET /search/history`、`GET /qa/history` | 登录；默认仅返回**当前用户**记录；admin 传 `?scope=all` 看全部 |

> **404 统一**：对单篇笔记或空间无权访问（异空间/非成员）的写操作一律返回 `404`，不返回 `403`，避免通过响应码泄露资源是否存在（与读接口一致）。
>
> **token 配额（已实装）**：`POST /qa`、`POST /qa/stream`、`POST /qa/agentic/stream`、`POST /search`（semantic/hybrid，纯 keyword 不计费）、`POST /notes/{id}/generate-qa`、`POST /wiki/compile` 会把本次 LLM/Embedding 的 token 计入当日用量（`token_usage.operation` = `qa` / `qa_stream` / `qa_agentic` / `search_semantic` / `qa_gen` / `compile` / `ingest`）。`POST /governance/scans` 与 `POST /agent/runs` 触发的后台 LLM 调用分别记 `governance_scan` / `agent_plan`，计费给触发者。请求前若当日累计已达 `daily_token_limit`（member 未设额度则用 `DEFAULT_DAILY_TOKEN_LIMIT`；admin 不限）返回 `429 {"error":{"code":"rate_limited","message":"今日 token 额度（N）已用完，次日 0 点重置"}}`。`/qa/stream`、`/qa/agentic/stream` 在开流前检查，超额以普通 `429` 返回（不进 SSE 流）。
>
> **MCP 不计入配额**：`/mcp` 走独立 Bearer API token（非 JWT），是系统级 Agent 调用，不归属某个用户、不计入 `token_usage`。

---

## 9. 系统状态 System

### `GET /api/system/status` — 系统情况（需登录）

驱动左下角「系统情况」面板与顶部版本号。只读聚合。

```json
{
  "version": "0.5.0",
  "storage_backend": "local",
  "pg_version": "18.0",
  "pgvector_version": "0.8.3",
  "notes": 14, "entities": 58, "wikis": 3,
  "db_size_bytes": 10237631,
  "disk": { "total_bytes": 232386519040, "used_bytes": 111764430848, "free_bytes": 120605310976 }
}
```

| 字段 | 说明 |
|------|------|
| `version` | 应用版本，单一来源 `config.app_version` |
| `storage_backend` | `local` / `r2`；前端容量条在 local 下取服务器盘，R2 时该数仅代表服务器盘 |
| `disk` | 存储根所在文件系统的总量/已用/可用，前端据此画容量条并强调「剩余可用」 |

---

## 10. MCP Server（Agent 接入）

把知识库的检索 / 问答 / 笔记 / 图谱 / 主题页暴露为 LLM Agent 可调用的只读工具。外部客户端（Claude Desktop / 自建 Agent）用 **Bearer API token**（非 JWT）访问 `POST /mcp`（streamable HTTP）。设计与边界见 [architecture.md](architecture.md)。

### `POST /mcp` — MCP streamable HTTP（独立鉴权，非 `/api`）

- **鉴权**：`Authorization: Bearer <mcp_token>`，与登录 JWT 分开的长期 API key；缺失/无效/已撤销返回 `401`。不挂全局登录依赖，也不计入用户配额。
- **协议**：MCP streamable HTTP（`stateless_http=True`），客户端按 MCP 规范发 `initialize` → `tools/list` → `tools/call`。
- **工具（全部只读）**：`search`、`ask`、`get_note`、`list_notes`、`get_graph`、`get_entity`、`list_wiki`、`get_wiki`。
- **可用性**：`mcp` 包未安装时 `/mcp` 不挂载（`is_available()` 返回 False），其余 `/api/*` 不受影响。

### token 管理（admin）—— `/api/mcp-admin/tokens`

| 接口 | 说明 |
|------|------|
| `GET /api/mcp-admin/tokens` | token 列表：`id / name / prefix / is_active / space_id / space_name / created_at / last_used_at`（不含明文） |
| `POST /api/mcp-admin/tokens` | 生成 token：`{name, space_id?}` → `201 {token, token_id, name, prefix, space_id}`，明文**仅本次返回一次**，库里存 bcrypt 哈希 + 前 8 位前缀；`space_id` 缺省绑 default 空间 |
| `PATCH /api/mcp-admin/tokens/{id}` | 改名 / 启停 / 换绑空间（`{name?, is_active?, space_id?}`） |
| `DELETE /api/mcp-admin/tokens/{id}` | 删除（`204`，立即失效） |

> `prefix` 是明文前 8 位，用于后台识别是哪个 token；校验时线性扫 active token 做 `bcrypt.checkpw`，命中更新 `last_used_at`。
>
> **M2 空间绑定**：每个 token 必须绑定一个 `space_id`，工具调用按该空间过滤（等价该空间 viewer）。删除空间会级联撤销其 MCP token，不存在 `NULL=全库` 后门。权限边界见 [architecture.md](architecture.md)。

---

## 11. 空间 Spaces（M2）

空间（Space）是多团队内容隔离边界：每篇笔记 / wiki / MCP token 归属一个空间，读写按空间 ACL
过滤。双层角色（系统级 `users.role` + 空间级 `space_members.role`）正交；sysadmin 对全部空间
天然是 `space_admin`。设计见 [architecture.md](architecture.md)。

### `GET /api/spaces` — 空间列表（需登录）

返回当前用户可见空间 + 在各空间的角色。普通用户 = 其成员空间；sysadmin = 全部空间。

```json
{
  "items": [
    { "id": "uuid", "slug": "default", "name": "默认空间", "description": null,
      "owner_id": "uuid", "is_default": true, "created_at": "...",
      "my_role": "editor" }
  ]
}
```

### `POST /api/spaces` — 建空间（需登录）

任意登录用户可建空间，创建者自动成为该空间 `space_admin`。

```json
// 请求
{ "slug": "team-eng", "name": "工程团队", "description": "..." }
// 响应 201
{ "id": "uuid", "slug": "team-eng", "name": "工程团队", "description": "...",
  "owner_id": "...", "is_default": false, "created_at": "..." }
```

### `GET /api/spaces/{id}` — 空间详情（viewer+）

### `PATCH /api/spaces/{id}` — 改空间（space_admin）

`{name?, description?}` 任意子集。响应 `SpaceOut`。

### `DELETE /api/spaces/{id}` — 删空间（space_admin）

`204`。default 空间不可删（`400`）；空间仍有笔记或 Wiki 时返回 `409`，必须先迁移或清理内容。删除成功会级联删除该空间的 MCP token。

### `GET /api/spaces/{id}/members` — 成员列表（viewer+）

```json
{
  "items": [
    { "user_id": "uuid", "email": "u@x.com", "display_name": "李四",
      "role": "editor", "created_at": "..." }
  ]
}
```

### `POST /api/spaces/{id}/members` — 加成员（space_admin）

```json
// 请求
{ "user_id": "uuid", "role": "viewer" }
// 响应 201：MemberOut
```

### `PATCH /api/spaces/{id}/members/{user_id}` — 改成员角色（space_admin）

`{role}` → `viewer`/`editor`/`space_admin`。响应 `MemberOut`。不能改自己的角色（`400`）。

### `DELETE /api/spaces/{id}/members/{user_id}` — 移除成员（space_admin）

`204`。不能移除自己（`400`，防自锁）。

### `GET /api/spaces/{id}/members/search?q=email` — 搜用户（space_admin）

按 email 模糊搜索用户，供加成员时找用户（`/auth/users` 是 sysadmin only，空间管理员未必是
sysadmin）。

```json
{ "items": [ { "id": "uuid", "email": "u@x.com", "display_name": "李四" } ] }
```

> 所有写操作写审计日志。空间管理员不能改/移除自己。

---

## 12. M3 · 内容生命周期、治理与深度问答

### 笔记生命周期

- `PATCH /api/notes/{id}`（editor+）：可修改 `title/content/tags/date/authority`，返回 `202`；
  仅当 `content` 或 `tags` 变化时创建持久化 `note_reindex` job（纯 title/date/authority 调整不重建索引）。
- `GET /api/notes/{id}/versions`（viewer+）：返回版本号、变更类型、操作者和时间。`change_type` 取值 `edit/refresh/restore/delete/undelete`。
- `POST /api/notes/{id}/versions/{version}/restore`（editor+）：保存当前版本后恢复目标快照并重建索引。
- `DELETE /api/notes/{id}`（space_admin）：软删除，返回 `204`。
- `POST /api/notes/{id}/restore`（editor+）：恢复软删除笔记，保存 `undelete` 版本快照后重建索引。
- `GET /api/notes/trash`（editor+）：列出当前用户可管理空间中的软删除笔记。
- `POST /api/notes/{id}/refresh`（editor+）：立即检查 URL 来源，返回 `202`。
- `PATCH /api/notes/{id}/source`（space_admin）：设置 `refresh_policy=manual|daily|weekly`。

所有现有 notes/search/qa/graph/wiki/tags/system/MCP 读取默认排除 `deleted_at IS NOT NULL`。

### 治理

- `GET /api/governance/issues?space_id=&status=&type=&page=&size=`：viewer+ 查看空间待办，响应带 `{items,total,page,size}`。
- `POST /api/governance/scans`：`{space_id}`，space_admin 创建 `governance_scan` job。响应 `status` 映射为前端轮询习惯的 `pending`（DB 行 `queued`）。
- `GET /api/governance/runs?space_id=&page=&size=`：查看扫描记录，响应带 `{items,total,page,size}`；`status` 映射：`queued→pending`、`running→processing`、`done→done`、`failed→failed`。
- `PATCH /api/governance/issues/{id}`：editor+，请求
  `{status:"resolved|ignored|open", resolution_note?}`。

issue 类型为 `stale/duplicate/conflict/broken_link/missing_tags`，严重度为 `low/medium/high`。

> 治理 run 与扫描 job 用独立状态词表 `queued/running/done/failed`（与 `ingest.status` 的 `pending/processing/done/failed` 不同，因为是独立子系统）；对外响应统一映射到 `pending/processing/done/failed` 便于前端复用轮询逻辑。`governance_scan` job 的 `jobs.stage` 在扫描期间推进 `queued → scan → done`。

### 深度问答

`POST /api/qa/agentic/stream` 请求体沿用 `QaRequest`。SSE 顺序：

1. `plan`：`{"queries":["..."]}`
2. `sources`：本次 ACL 范围内的来源
3. `token`：回答文本分块
4. `verification`：`{"status":"supported|warning","invalid_citations":[],"message":"..."}`
5. `done`：`{"generated":true,"mode":"agentic","pii_masked":false,"masked_answer":"..."}`

> `done` 事件的 `masked_answer` 是对完整答案做 PII 掩码后的版本（手机号/邮箱/身份证/银行卡替换为 `[PII已隐藏]`）；`pii_masked` 表示是否发生了掩码。前端在收到 `done` 后用 `masked_answer` 覆盖流式累积的文本，确保最终展示不含 PII。`/qa/stream` 的 `done` 事件同样带 `masked_answer`。

---

## 13. M4 · 企业连接器、通知、反馈与审批 Agent

### 连接器（space_admin）

- `GET /api/connectors?space_id=`：连接器列表。
- `POST /api/connectors`：创建，字段 `space_id/provider/name/config/credentials`；
  provider 为 `confluence/feishu/google_drive/sharepoint`。
- `PATCH /api/connectors/{id}`：更新非密配置、状态或替换凭据。
- `DELETE /api/connectors/{id}`：删除连接器配置，不删除已同步笔记。
- `POST /api/connectors/{id}/sync`：创建 `connector_sync` job。
- `GET /api/connectors/{id}/items`：远端对象同步状态。

### 订阅与通知

- `GET/POST /api/subscriptions`、`DELETE /api/subscriptions/{id}`：
  scope_type 为 `space/tag/note`。
- `GET /api/notifications?unread_only=`：当前用户站内通知。
- `POST /api/notifications/read`：`{ids?:[]}`；ids 缺省表示全部已读。

### 问答反馈

- `PUT /api/qa/history/{id}/feedback`：`{rating:"up|down",reason?}`。
- `GET /api/qa/feedback?rating=down`：sysadmin 查看反馈。

### 治理 Agent

- `POST /api/agent/runs`：`{space_id}`，space_admin 创建规划 job。
- `GET /api/agent/proposals?space_id=&status=`：提案列表。
- `POST /api/agent/proposals/{id}/approve`、`/reject`：审批。
- approve 只入队，执行结果通过 proposal 的 `executed/failed` 状态查看。

执行器白名单仍为五类：`add_tags`、`update_summary`、`refresh_source`、
`archive_duplicate`、`resolve_issue`。当前规划策略中，`stale` 与 `broken_link`
只有 URL 来源会生成 `refresh_source`；对 manual/连接器来源不靠重写旧摘要伪装成已更新，
而是留给人工或连接器增量同步。`archive_duplicate` 执行时重新校验 `other_note_id`
同空间且未删除。未经 `space_admin` 审批不会写入，审批后仍由确定性执行器再次校验并执行。

---

## 字段映射速查（mock → 接口）

前端 demo 用了一批缩写字段，对接真实接口时按此调整：

| mock 字段 | 接口字段 | 出现位置 |
|-----------|----------|----------|
| `cat` | `cat`（保留） | 实体类别 |
| `keypoints` | `keypoints`（保留） | 笔记要点 |
| `original` | `original`（保留） | 笔记正文段落 |
| `source` | `source`（保留） | 笔记来源文案 |
| `srcN` | `source_count` | 问答历史 |
| `srcIds` | `source_ids` | 主题页 |
| `when` | `relative` | 历史时间文案 |
| `wiki.conflict.a/b` | `conflict.sides[]` | 主题页矛盾点 |
| 实体 `x/y/r` | 不再返回（前端布局） | 知识图谱 |

---

## 实现状态

下列当初列出的差距现已全部实现：

1. **worker 写 jobs 表** — `ingest_worker.py` 在各步骤同步更新 `jobs` 行的 `stage`/`progress`；含「分块 chunking」步骤，逐块向量化写 `note_chunks`
2. **检索接口** — 关键词（ES+ik 中文分词，ES 不可达回退 PG ILIKE）+ 语义（pgvector，chunk 级）+ RRF 融合，写入 `search_history`
3. **图谱接口** — 查 `entity_note_counts` / `entity_cooccurrence` 视图、实体详情查 `note_entities`
4. **问答接口** — RAG 检索 + LLM 生成 + 来源引用，写入 `qa_history`；**SSE 流式已实现**（`POST /qa/stream`）且前端已接入逐字渲染
5. **API 字段映射** — `published_date→date`、`mode`（含 hybrid/tag）、jobs `queued/running→pending/processing`

> **SQL schema**：M0~M2 为 `sql/01~24`，M3 为 `sql/25~28`，M4 为 `sql/29~33`，生命周期修补为 `sql/34`。
> 详见 `sql/` 目录。
