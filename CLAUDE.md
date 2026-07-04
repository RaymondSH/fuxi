# fuxi · 工作规则与工程规范

给在本仓库工作的 AI agent 和开发者看的总纲。**动手前先读这份文件。**

> 项目定位见 [README.md](README.md)，最终架构见 [docs/architecture.md](docs/architecture.md)，
> 接口契约见 [docs/api-contract.md](docs/api-contract.md)，运维见
> [docs/operations.md](docs/operations.md)，进度见 [PROGRESS.md](PROGRESS.md)。

---

## 0. 头等规矩（每次都要做）

1. **改完代码就更新 [PROGRESS.md](PROGRESS.md)** — 把对应条目的状态（⬜/🚧/✅）改对，并在文件底部「更新日志」追加一行。这是硬性要求，不是可选项。
2. **接口以 [docs/api-contract.md](docs/api-contract.md) 为准** — 前后端字段、枚举、路径都照契约来。要改接口，先改契约再改代码。
3. **动了表结构就同步 `sql/` 文件** — schema 的唯一真相在 `sql/01`~`33`，不要只在数据库里改。

---

## 1. 部署环境（重要）

- **本地没有 Docker**。不要假设 `docker` / `docker-compose` 可用，也不要让用户本地起容器。
- **有一台 Linux 服务器，`ssh linux-server` 直接登录**。PostgreSQL（含 pgvector）、Elasticsearch、Redis 等服务跑在这台服务器上；本地只跑后端/前端开发进程，连服务器上的依赖。
- 因此：需要数据库/中间件时，在 `linux-server` 上装与起；本地通过 SSH 端口转发或直连服务器地址访问。环境搭建脚本以「在 linux-server 上执行」为前提来写。
- 密钥、连接串放各自的 `.env`，**永不提交**。

---

## 2. 仓库结构

```
fuxi/
├── CLAUDE.md / README.md / PROGRESS.md     # 总纲 / 介绍 / 进度
├── docs/               architecture / api-contract / operations
├── Fuxi 知识库 (standalone).html            # 前端设计稿（house style 的来源）
├── sql/                01~34，schema 唯一真相
├── deploy/es/          ES8 + ik 中文分词 Docker 部署（绑 127.0.0.1:9200）
├── backend/            FastAPI
│   ├── config.py db.py main.py
│   ├── routers/        HTTP 接口（一个资源一个文件）
│   ├── workers/        异步任务（ingest / compile）
│   ├── services/       复用逻辑门面（llm / embedder / fetcher / es / storage / chunker）
│   │   └── providers/  策略层：base 抽象 + glm 智谱实现 + 工厂
│   └── models/         （预留）ORM / pydantic 数据模型
├── frontend/           Next.js Web
└── scripts/fuxi.py     唯一 Python 运维入口
```

---

## 3. 技术栈与边界

| 层 | 选型 | 约束 |
|----|------|------|
| 前端 | Next.js + Tailwind | 视觉照搬设计稿（见 §6 house style） |
| 后端 | Python FastAPI | 接口薄、逻辑进 services/workers |
| 关系库 + 向量 | PostgreSQL + pgvector（**需 ≥ 0.5**，HNSW） | 跑在 linux-server |
| 全文检索 | Elasticsearch 8 + ik 中文分词 | 跑在 linux-server（Docker，绑 127.0.0.1:9200）；中文关键词主路，ES 不可达自动回退 PG ILIKE |
| 文件存储 | Cloudflare R2 / S3（`services/storage.py` 抽象） | 原始文件；默认 `local` 兜底零依赖，配 R2 凭据即切云，**改 `.env` 不改代码** |
| 队列 | jobs 表 + pg LISTEN/NOTIFY（先），Redis（后） | 见 `sql/06_jobs.sql` |
| LLM | 智谱 GLM `glm-5.2`（兼容 OpenAI 协议） | **只经 `services/providers/` 策略层** |
| Embedding | 智谱 `embedding-3`（1536 维，可自定义维度） | **只经 `services/providers/` 策略层** |

---

## 4. 后端编码规范

**通用**
- Python 3.10+，4 空格缩进，类型注解齐全，命名 `snake_case`，类 `PascalCase`。
- 注释/文档可用中文，与现有代码保持一致；每个模块顶部写一句话职责。
- 不在业务代码里裸 `print`；要日志用 `logging`。

**分层职责**
- `routers/` 只做：解析请求 → 调 service/worker → 组装响应。**不写业务逻辑、不直接连外部 API**。
- `services/` 封装外部依赖与可复用逻辑。**外部 SDK 只在此 new**：LLM/Embedding 只在 `services/providers/`（策略层）、抓取只在 `fetcher.py`。`services/llm.py`、`services/embedder.py` 是薄门面，委托 `providers.get_llm()` / `providers.get_embedder()`。其他地方 `from services import ...`。
- `workers/` 跑慢任务（抓取、提炼、编译），可阻塞；通过 `BackgroundTasks` 或队列触发。
- `db.py` 提供连接池；worker 用同步连接，简单可靠。

**FastAPI 约定**
- 路由按资源分文件，`APIRouter(prefix=..., tags=[...])`，在 `main.py` 注册。
- 请求/响应用 Pydantic 模型显式声明，别返回裸 dict。
- 慢操作（入库等）一律异步：接口建占位行 → 立即 202 返回 id → 后台处理 → 前端轮询状态。
- 错误用 `HTTPException`，错误体形如 `{"error":{"code","message"}}`（见契约）。

**LLM 调用**（细节见 `services/providers/glm.py`）
- 默认智谱 `glm-5.2`（对话/提炼/问答）+ `glm-4.6v`（图片入库）；经 `providers.get_llm()` 取实例。
- 智谱 `/api/paas/v4/` 兼容 OpenAI 协议，复用 `openai` SDK + `base_url`，不新依赖。
- 结构化输出用 `response_format={"type":"json_object"}` + system 嵌 schema 提示 → `IngestResult.model_validate_json()`（智谱无 Anthropic 的 `messages.parse`）。
- `thinking={"type":"enabled"}` / `reasoning_effort` 通过 SDK 的 `extra_body` 透传。
- 模型名从 `config.chat_model` / `vision_model` 取，不硬编码。
- 换 provider（兼容 OpenAI 协议者）只改 `API_KEY`+`AI_BASE_URL`+模型名；接不兼容协议者新增 `providers/xxx.py` 实现 + 工厂分支。
- **流式**：`answer_stream`（异步生成器）用 `AsyncOpenAI` 单例 + `stream=True` + `thinking on`，`/qa/stream` 经 `sse-starlette` 推 `sources`→`token`→`done` 事件。
- **Wiki 编译**：`compile_wiki` 用 `response_format=json` + `reasoning_effort=max`，产出结构化 `WikiCompileResult`（sections/paragraphs/cites/conflict）。

**SQL / 数据**
- 表名/列名 `snake_case`；改 schema 改 `sql/` 文件，不写「数据库里手动改」的隐式步骤。
- DB 列 ↔ API 字段的映射在契约里有表（如 `published_date→date`、jobs `queued/running→pending/processing`）——加新字段时同步维护这张映射。
- 向量列固定 1536 维，与 `config.embed_dim` 和 embedding 模型一致；换模型要同时改三处。

---

## 5. 前端编码规范（待建项目时遵守）

- Next.js（App Router）+ TypeScript + Tailwind。
- **数据全走后端接口**，不内嵌 mock（设计稿里的 mock 仅作视觉参考）。
- 字段名照契约；设计稿用的缩写（`cat`/`srcN`/`when` 等）按契约「字段映射」小节对齐。
- 知识图谱：后端只给 `nodes + edges + count`，**坐标/半径在前端用力导向布局算**。
- 问答优先走 SSE 流式（先来源、后逐 token），对应设计稿的「思考中」态。

---

## 6. House Style（视觉规范，源自设计稿）

实现前端时严格沿用，保证和设计稿一致。

| 用途 | 色值 |
|------|------|
| 主背景 / 品牌色（terracotta） | `#B25B3C` |
| 奶白底 / 反白文字 | `#FBF1E9` |
| 面板/卡片底 | `#F4F0E8` |
| 正文文字 | `#2B2722` |
| 次要文字 | `#6F675B` / `#8C8273` |
| 强调/激活 | `#9A4A2F` |

实体类别色：concept 绿 `#6E8B5E`(软 `#E9EFE2`) · product 赭 `#B25B3C`(软 `#F5E7DE`) · company 蓝 `#5C7796`(软 `#E4EAF1`)。
来源角标：LINK 蓝 · PDF 赭 · WORD 蓝 · XLSX 绿 · IMG·OCR 黄（具体色值见设计稿 `typeMeta`）。
字体：标题衬线（Georgia 一类），标签/角标等宽。整体暖色编辑风，避免通用 AI 风格（紫渐变、Inter 等）。

---

## 7. Git 与协作

- 不在默认分支直接堆改动；按功能开分支。
- 提交信息写清「做了什么」；改了接口/表结构在提交信息里点明。
- 提交前确认没带进 `.env`、密钥、`__pycache__`。

---

## 8. 验证

- 后端改完至少 `python -m py_compile` 过；能跑就 `uvicorn main:app` 起来打一遍接口。
- 涉及数据库的改动，在 `linux-server` 上对真库跑一遍（本地无 Postgres）。
- 报告结果如实写：跑了什么、过没过、跳过了什么。
