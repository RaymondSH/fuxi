# fuxi 知识库

一个功能完备的在线 AI 知识库系统。用户通过 Web 端入库各类素材（链接、PDF、Word、Excel、图片），系统用 Claude 自动提炼摘要、要点、标签和实体，支持全文 + 语义检索、知识图谱、问答历史。

> 前身是本地个人知识库 [my-wiki](../my-wiki)（纯 Markdown 文件），fuxi 把它升级为可支撑 GB 级数据、多人检索的在线系统。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **入库** | 链接抓取（网页 / 公众号）、本地文件（PDF / Word / Excel / 图片 OCR）、手动输入 |
| **AI 提炼** | 摘要、要点、标签、实体（公司 / 人名 / 概念等）自动生成 |
| **检索** | 关键词全文搜索 + 语义搜索 + 标签/时间筛选 + 搜索历史 |
| **知识图谱** | 实体 + 关系可视化，点击实体查看相关笔记 |
| **问答（RAG）** | 基于知识库提问，AI 给出带来源的回答，支持多轮 + 历史记录 |
| **编译** | 同主题多篇笔记合并成 wiki 主题页，标出观点矛盾 |

---

## 架构

```
前端 (Next.js)          搜索 / 问答 / 知识图谱 / 入库 / 阅读 / 历史
     │
后端 API (FastAPI)      /ingest  /search  /graph  /notes  /wiki
     │
AI Pipeline             Ingest Worker · RAG Engine · Graph Builder · Compile Worker
     │
存储                    PostgreSQL + pgvector · Elasticsearch · S3/R2 · Redis
                        （笔记/实体/历史）  （语义向量）  （全文）  （文件）（队列）
```

**技术栈**

| 层 | 选型 | 理由 |
|----|------|------|
| 前端 | Next.js + Tailwind | SSR 对搜索友好 |
| 后端 | Python FastAPI | AI/NLP 生态最好 |
| 关系库 | PostgreSQL + pgvector | 一个库搞定结构化数据 + 向量，少运维 |
| 全文搜索 | Elasticsearch | 中文分词好（ik 插件） |
| 文件存储 | Cloudflare R2 / S3 | 原始文件 |
| 任务队列 | Redis / pg_notify | 入库异步处理 |
| AI 生成 | 智谱 GLM (`glm-5.2`) | 摘要 / 问答 / 实体 / 编译 |
| Embedding | 智谱 `embedding-3` (1536 维) | 语义向量，经 providers 策略层可换 |

---

## 目录结构

```
fuxi/
├── README.md
├── sql/                          # 数据库 schema
│   ├── 00_init.sql               # 入口：按顺序执行下面所有脚本
│   ├── 01_extensions.sql         # uuid-ossp / vector / pg_trgm
│   ├── 02_notes.sql              # 笔记主表 + 向量索引
│   ├── 03_graph.sql              # 实体表 / 关系表 / 笔记-实体关联
│   ├── 04_wiki.sql               # 主题页 + 笔记反向引用
│   ├── 05_history.sql            # 搜索历史 + 问答历史
│   └── 06_jobs.sql               # 异步任务队列（含 pg_notify）
│
├── backend/                      # Python FastAPI
│   ├── main.py                   # 应用入口
│   ├── config.py                 # 环境变量配置
│   ├── db.py                     # psycopg 连接池 + pgvector 注册
│   ├── requirements.txt
│   ├── routers/                  # HTTP 接口
│   │   ├── ingest.py             # ✅ 入库
│   │   ├── search.py             # ⬜ 搜索 / 问答
│   │   ├── graph.py              # ⬜ 知识图谱
│   │   ├── notes.py              # ⬜ 笔记 CRUD
│   │   └── wiki.py               # ⬜ 主题页 / 编译
│   ├── workers/                  # 异步任务
│   │   ├── ingest_worker.py      # ✅ 抓取→提炼→向量化→写库
│   │   └── compile_worker.py     # ⬜ 多笔记 → wiki
│   └── services/                 # 复用逻辑
│       ├── llm.py                # ✅ LLM 门面（委托 providers）
│       ├── embedder.py           # ✅ 向量化门面
│       ├── fetcher.py            # ✅ URL/PDF/docx/xlsx/图片 抓取
│       └── providers/            # ✅ 策略层：base 抽象 + glm 智谱实现 + 工厂
│
├── frontend/                     # ⬜ Next.js
├── infra/                        # ⬜ docker-compose 等
└── scripts/
    └── migrate_from_mywiki.py    # ⬜ 把 my-wiki 笔记导入
```

✅ 已实现　⬜ 占位 / 待实现

---

## 快速开始

> 当前后端的入库链路已可端到端运行，依赖 PostgreSQL（带 pgvector 扩展）。

### 1. 数据库

```bash
# 需要 PostgreSQL 16+ 并安装 pgvector 扩展
createdb fuxi
psql -d fuxi -f sql/00_init.sql
```

### 2. 配置

在 `backend/` 下建 `.env`：

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fuxi
# AI 服务（智谱 GLM，聊天/视觉/向量共用一个 Key）
API_KEY=
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
CHAT_MODEL=glm-5.2
VISION_MODEL=glm-4.6v
EMBED_MODEL=embedding-3
EMBED_DIM=1536
# 可选
JINA_READER_PREFIX=https://r.jina.ai/
```

### 3. 安装依赖并启动

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

打开 http://localhost:8000/docs 看交互式 API 文档。

---

## API

### 入库

```bash
# 链接入库
curl -X POST localhost:8000/ingest/url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/article"}'
# → {"note_id":"...","status":"pending"}

# 文件入库（PDF/Word/Excel/图片）
curl -X POST localhost:8000/ingest/file \
  -F 'file=@report.pdf'

# 查入库状态
curl localhost:8000/ingest/<note_id>
# → {"ingest_status":"done","title":"...","summary":"...","tags":[...]}
```

入库是异步的：接口立即返回 `note_id`（HTTP 202），后台跑 `抓取 → Claude 提炼 → 向量化 → 写库`，前端拿 `note_id` 轮询状态（`pending → processing → done / failed`）。

---

## 开发进度

- [x] 数据库 schema（笔记 / 实体 / 关系 / wiki / 历史 / 任务队列）
- [x] 抓取层（URL / PDF / Word / Excel / 图片）
- [x] 入库 Worker（提炼 + 向量化 + 实体写入）
- [x] 入库 HTTP 接口（异步 + 状态查询）
- [ ] 搜索（关键词 + 语义）+ 搜索历史
- [ ] RAG 问答 + 问答历史
- [ ] 知识图谱（实体提取 → 可视化）
- [ ] wiki 编译
- [ ] 前端 Web 界面
- [ ] Docker 部署
- [ ] my-wiki 数据迁移脚本

---

## 设计原则

- **存储简单优先** — PostgreSQL + pgvector 一个库同时承载结构化数据和向量，能不引入新组件就不引入
- **机械活给脚本，语义活给 Claude** — 抓取、索引、打分用代码；摘要、实体、判断用 Claude
- **入库异步** — 慢操作不阻塞接口，前端轮询状态
- **Embedding 与 LLM 解耦** — 换向量模型只改 `embedder.py` 一处
