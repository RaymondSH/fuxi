# fuxi 知识库

一个功能完备的在线 AI 知识库系统。用户登录后入库各类素材（链接、PDF、Word、Excel、图片），系统用智谱 GLM 自动提炼摘要、要点、标签和实体，支持全文 + 语义检索、知识图谱、RAG 问答、Wiki 编译；带用户鉴权、按用户隔离历史、每日 token 配额与管理后台。

> 前身是本地个人知识库 [my-wiki](../my-wiki)（纯 Markdown 文件），fuxi 把它升级为可支撑 GB 级数据、多用户检索的在线系统。当前版本 **v0.4.0**，已部署上线（见 [docs/deploy.md](docs/deploy.md)）。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **账户与权限** | 登录鉴权（用户名或邮箱皆可）；两角色 member / admin；账号由管理员创建 |
| **入库** | 链接抓取（网页 / 公众号）、本地文件（PDF / Word / Excel / 图片 OCR）；**仅管理员** |
| **AI 提炼** | 摘要、要点、标签、实体（公司 / 人名 / 概念等）自动生成；长文档分块 |
| **检索** | 关键词（ES + ik 中文分词）+ 语义（pgvector）+ RRF 混合 + 标签/时间筛选 |
| **知识图谱** | 实体 + 共现关系可视化，点击实体查看相关笔记 |
| **问答（RAG）** | 基于知识库提问，带来源回答，支持多轮；同步 + SSE 流式 |
| **Wiki 编译** | 同主题多篇笔记合并成主题页，标出观点矛盾 |
| **配额与历史** | 每日 token 配额（超额 429）；搜索/问答历史按用户隔离 |

---

## 架构

```
前端 (Next.js)        登录 / 检索 / 问答 / 图谱 / Wiki / 历史 / 管理后台
     │
后端 API (FastAPI)    /auth /ingest /search /qa /graph /notes /wiki /system
     │                （除 /auth/login 外都需 JWT；入库等写操作仅 admin）
AI Pipeline           Ingest Worker · RAG Engine · Graph Builder · Compile Worker
     │
存储                  PostgreSQL + pgvector · Elasticsearch(ik) · 本地盘/R2 · Redis
                      （笔记/实体/历史/向量/用户/用量）（中文全文）（原始文件）（队列）
```

**技术栈**

| 层 | 选型 | 理由 |
|----|------|------|
| 前端 | Next.js + Tailwind | SSR 对搜索友好 |
| 后端 | Python FastAPI | AI/NLP 生态最好 |
| 关系库 + 向量 | PostgreSQL + pgvector | 一个库搞定结构化数据 + 向量，少运维 |
| 全文搜索 | Elasticsearch 8 + ik | 中文分词好；不可达自动回退 PG ILIKE |
| 文件存储 | 本地盘默认 / Cloudflare R2（S3 兼容） | 改 `.env` 即切换，不改代码 |
| 任务队列 | jobs 表 + pg_notify（Redis 备） | 入库异步处理 |
| 鉴权 | JWT(HS256) + bcrypt | 自管账号，无第三方 |
| AI 生成 | 智谱 GLM (`glm-5.2` / `glm-4.6v`) | 摘要 / 问答 / 实体 / 编译 / 图片入库 |
| Embedding | 智谱 `embedding-3` (1536 维) | 语义向量，经 providers 策略层可换 |

---

## 目录结构

```
fuxi/
├── README.md / CLAUDE.md / PROGRESS.md     # 介绍 / 工作规范 / 进度
├── docs/                                    # api-contract / auth-design / deploy
├── sql/                                     # 数据库 schema（00 入口按序执行 01~10）
│   ├── 01_extensions … 06_jobs              # 扩展 / 笔记 / 图谱 / wiki / 历史 / 队列
│   ├── 07_chunks.sql                        # 文档分块表 note_chunks
│   ├── 08_auth.sql                          # users + token_usage 账本
│   ├── 09_history_user.sql                  # 历史表加 user_id（按用户隔离）
│   └── 10_user_username.sql                 # users 加 username（用户名登录）
│
├── backend/                                 # Python FastAPI
│   ├── main.py / config.py / db.py / requirements.txt
│   ├── routers/        auth · ingest · search · qa · graph · notes · wiki · system
│   ├── workers/        ingest_worker · compile_worker
│   └── services/       auth · quota · usage · llm · embedder · fetcher
│       │               · es · storage · chunker
│       └── providers/  策略层：base 抽象 + glm 智谱实现 + 工厂
│
├── frontend/                                # Next.js（App Router）
│   ├── app/            login · search · qa · graph · wiki · notes · history
│   │                   · admin/(ingest · users · usage)
│   ├── components/      AppShell · AuthProvider · Sidebar · TopBar · SystemStatus …
│   └── lib/            api · types · forceLayout
│
├── deploy/es/                               # ES8 + ik Docker 部署
└── scripts/            create_admin · seed_demo · reindex_es · migrate_from_mywiki
```

---

## 快速开始

> 依赖 PostgreSQL（带 pgvector ≥ 0.5）。Elasticsearch / R2 可选（不配则自动降级）。

### 1. 数据库

```bash
# PostgreSQL 16+ 且装好 pgvector 扩展
createdb fuxi
psql -d fuxi -f sql/00_init.sql      # 按序建 01~10 全部表/索引
```

### 2. 配置

在 `backend/` 下建 `.env`（完整项见 [backend/.env.example](backend/.env.example)）：

```bash
DATABASE_URL=postgresql://fuxi:fuxi@localhost:5432/fuxi
# AI 服务（智谱 GLM，聊天/视觉/向量共用一个 Key）
API_KEY=
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
CHAT_MODEL=glm-5.2
VISION_MODEL=glm-4.6v
EMBED_MODEL=embedding-3
EMBED_DIM=1536
# 鉴权（必填！随机长串：openssl rand -hex 32）
JWT_SECRET=
DEFAULT_DAILY_TOKEN_LIMIT=100000   # member 每日 token 上限；admin 不限
# 可选：JINA_READER_PREFIX / STORAGE_* / R2_* / ES_URL / CHUNK_* / USAGE_TZ
```

### 3. 启动后端 + 建管理员

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 首个管理员（系统不开放自助注册）
PYTHONPATH=. python ../scripts/create_admin.py \
  --username admin --email you@example.com --password '你的强密码'
```

打开 http://localhost:8000/docs 看交互式 API 文档。

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev        # 开发；生产用 npm run build && npm start
```

浏览器开前端地址 → 用刚建的账号登录。

---

## API

所有业务接口挂在 `/api` 下；**除 `POST /api/auth/login` 外都需带 `Authorization: Bearer <jwt>`**（入库、删除、Wiki 编译仅管理员）。完整契约见 [docs/api-contract.md](docs/api-contract.md)。

```bash
# 登录（用户名或邮箱皆可）→ 拿 token
curl -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin","password":"你的密码"}'
# → {"access_token":"<jwt>","user":{...}}

# 链接入库（管理员）
curl -X POST localhost:8000/api/ingest/url \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/article"}'
# → 202 {"note_id":"...","status":"pending"}

# 检索
curl -X POST localhost:8000/api/search \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"q":"RAG 分块策略","mode":"hybrid"}'
```

入库异步：接口立即返回 `note_id`（202），后台跑 `抓取 → GLM 提炼 → 分块 → 向量化 → 写库`，前端轮询状态（`pending → processing → done / failed`）。

---

## 开发进度

- [x] 数据库 schema（笔记 / 实体 / 关系 / wiki / 历史 / 队列 / 分块 / 用户 / 用量）
- [x] 入库链路（抓取 → 提炼 → 分块 → 向量化 → 写库 + 原始文件落盘）
- [x] 检索（ES+ik 关键词 + pgvector 语义 + RRF 混合）+ 搜索历史
- [x] RAG 问答（同步 + SSE 流式）+ 问答历史
- [x] 知识图谱（实体共现 → 可视化）
- [x] Wiki 编译
- [x] 前端 Web 界面（含登录页 + 管理后台）
- [x] 鉴权（JWT，用户名/邮箱登录）+ 角色（member/admin）
- [x] 每日 token 配额（429）+ 按用户隔离历史
- [x] 管理后台（入库 / 用户管理 / 用量看板）
- [ ] HTTPS + 反向代理（上线收尾，最高优先）
- [ ] my-wiki 数据迁移脚本（仅占位）

详细进度见 [PROGRESS.md](PROGRESS.md)。

---

## 设计原则

- **存储简单优先** — PostgreSQL + pgvector 一个库同时承载结构化数据和向量，能不引入新组件就不引入
- **机械活给脚本，语义活给 LLM** — 抓取、索引、打分用代码；摘要、实体、判断用 GLM
- **入库异步** — 慢操作不阻塞接口，前端轮询状态
- **依赖只在 services 层 new** — 换 LLM/Embedding 走 `providers/` 策略层，换存储/检索改 `.env`
- **共享语料 + 角色策展** — notes/图谱/wiki 全局共享，入库等策展操作收归管理员；预算靠每日配额护栏
