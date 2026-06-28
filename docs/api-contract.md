# fuxi 前后端接口契约

本文档以前端设计稿（`Fuxi 知识库 (standalone).html`）的真实数据模型为准，定义前后端接口。
设计稿是静态 demo（数据是组件里的 mock，无真实请求），下面的接口就是要把这些 mock 替换成真实后端。

## 页面 → 接口总览

| 前端页面 | 主要接口 |
|----------|----------|
| 检索 search / 结果 results | `POST /api/search`、`GET /api/tags` |
| 笔记详情 note | `GET /api/notes/{id}` |
| 问答 qa | `POST /api/qa`、`GET /api/qa/history` |
| 知识图谱 graph | `GET /api/graph`、`GET /api/graph/entities/{id}` |
| 主题页 wiki | `GET /api/wiki`、`GET /api/wiki/{slug}` |
| 入库 ingest | `POST /api/ingest/url`、`POST /api/ingest/file`、`GET /api/ingest/jobs` |
| 历史 history | `GET /api/search/history`、`GET /api/qa/history` |

---

## 通用约定

- **Base URL**：`/api`
- **格式**：请求/响应均为 JSON（文件上传用 `multipart/form-data`）
- **时间**：存储用 ISO 8601（`2026-06-20T09:14:00Z`）；前端展示的「2 分钟前 / 昨天」由前端格式化，但接口同时返回 `created_at`（绝对时间）和 `relative`（相对文案）两个字段，前端可直接用 `relative`
- **分页**：`?page=1&size=20`，响应带 `{ total, page, size }`
- **错误**：

```json
{ "error": { "code": "not_found", "message": "笔记不存在" } }
```

- **异步入库**：入库接口立即返回 `note_id`（HTTP 202），真正处理在后台跑，前端轮询 job 状态（详见入库章节）

---

## 枚举字典

集中定义所有枚举，前后端共用。

| 枚举 | 取值 | 说明 |
|------|------|------|
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

### `GET /api/notes` — 笔记列表（可选）

`?page=&size=&type=&tag=`，响应 `{ items: [NoteSummary], total, page, size }`。
`NoteSummary` = 上面去掉 `original`，用于列表展示。

---

## 2. 入库 Ingest

### `POST /api/ingest/url` — 链接入库

```json
// 请求
{ "url": "https://mp.weixin.qq.com/s/xxx" }
// 响应 202
{ "note_id": "n7", "status": "pending" }
```

### `POST /api/ingest/file` — 文件入库

`multipart/form-data`，字段 `file`。支持 pdf/docx/xlsx/图片。响应同上。

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
> **后端缺口**：当前 `ingest_worker.py` 只有 `pending/processing/done/failed` 四态，没有细粒度 `stage` 和 `progress`。要支撑这个页面，需要在 worker 各步骤之间更新 `jobs` 表的 `stage`/`progress` 字段。另外前端流水线含「extract 解析 / refine 提炼」两步，且长文档有**分块（chunking）**环节——当前 worker 是整篇向量化，需补分块步骤。

### `GET /api/ingest/jobs/{id}` — 单个任务状态

单条轮询用，响应同 `items` 里的单个对象，外加 `error_msg`（失败时）。

---

## 3. 检索 Search

### `POST /api/search`

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

### `GET /api/tags` — 标签云

驱动检索页的标签筛选 chips。

```json
{ "items": [ { "name": "RAG", "count": 4 }, { "name": "检索", "count": 3 } ] }
```

### `GET /api/search/suggestions?q=长上下文` — 联想（可选）

对应 demo 里的 `suggestChips`，返回 `{ items: ["长上下文会取代 RAG 吗", "..."] }`。

---

## 4. 问答 QA（RAG）

### `POST /api/qa`

驱动「问答」页。基于知识库检索 + LLM 生成带来源的回答。

```json
// 请求（history 传多轮上下文）
{
  "question": "混合检索比单路能提升多少召回？",
  "history": [
    { "role": "user", "text": "什么是混合检索？" },
    { "role": "assistant", "text": "……" }
  ]
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
| `answer` | Markdown，前端按 `\n\n` 分段、渲染 `**加粗**` |
| `sources` | 引用来源，前端显示「N 条来源」并可点击跳笔记 |

> **建议支持流式**：`POST /api/qa?stream=true` 走 SSE，先推 `sources`（检索结果），再逐 token 推 `answer`。对应 demo 里的 `thinking` 状态（思考中动画）。普通模式则一次性返回。

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

## 与现有后端的差距（待补）

按本契约对齐，后端还需要做：

1. **worker 写 jobs 表** — schema 已就绪（`jobs` 含 `stage`/`progress`/`note_id`/`title`/`sub`），但 `ingest_worker.py` 目前只写 `notes`，需在各步骤同步更新 `jobs` 行；并补「分块 chunking」步骤
2. **检索接口** — 关键词（ES/PG 全文）+ 语义（pgvector）+ RRF 融合，写入 `search_history`
3. **图谱接口** — 直接查 `entity_note_counts` / `entity_cooccurrence` 两个视图（已建）、实体详情查 `note_entities`
4. **问答接口** — RAG 检索 + LLM 生成 + 来源引用，写入 `qa_history`，建议支持 SSE 流式
5. **API 字段映射** — DB 列 → API 字段：`published_date→date`、`mode`（含 hybrid）、jobs `queued/running→pending/processing`

> **SQL schema 已全部就位**（`sql/01`~`06`，含 notes/entities/relations/note_entities/wiki/history/jobs 及图谱视图），已对齐本契约的字段需求。详见 `sql/` 目录。
