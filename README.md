# fuxi 知识库

一个功能完备的在线 AI 知识库系统。用户登录后入库各类素材（链接、PDF、Word、Excel、图片），系统用智谱 GLM 自动提炼摘要、要点、标签和实体，支持全文 + 语义检索、知识图谱、RAG 问答、Wiki 编译；带用户鉴权、按用户隔离历史、每日 token 配额与管理后台，并按「空间」隔离多团队内容。

> 前身是本地个人知识库 [my-wiki](../my-wiki)（纯 Markdown 文件），fuxi 把它升级为可支撑 GB 级数据、多用户检索的在线系统。当前版本 **v0.8.0**，已部署上线（见 [docs/operations.md](docs/operations.md)）。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **账户与权限** | 登录鉴权（用户名或邮箱皆可）；系统角色 member/admin + 空间角色 viewer/editor/space_admin 双层正交；账号由管理员创建 |
| **空间隔离** | 多团队内容隔离：笔记 / wiki / MCP token 各归属空间，读写按空间 ACL 过滤；空间内共享语料跨全库检索 |
| **入库** | 链接抓取（网页 / 公众号）、本地文件（PDF / Word / Excel / 图片 OCR）；**仅管理员** |
| **AI 提炼** | 摘要、要点、标签、实体（公司 / 人名 / 概念等）自动生成；长文档分块 |
| **检索** | 关键词（ES + ik 中文分词）+ 语义（pgvector）+ RRF 混合 + 标签/时间筛选 |
| **知识图谱** | 实体 + 共现关系可视化，点击实体查看相关笔记 |
| **问答（RAG）** | 基于知识库提问，带来源回答，支持多轮；同步 + SSE 流式；**四种角色风格**（默认/高管摘要/技术深度/讲给外行） |
| **Q&A 沉淀回灌** | 把笔记生成问答对（带向量），问答时召回最相似的历史问答拼进上下文复用 |
| **标签治理** | 受控词表（规范名 + 别名 + 状态）+ 同义标签归并（物理回写 + ES 同步） |
| **Wiki 编译** | 同主题多篇笔记合并成主题页，标出观点矛盾 |
| **MCP Server** | 检索/问答/笔记/图谱/主题页暴露为 Agent 只读工具，Claude Desktop 等用 Bearer token 接入 |
| **配额与历史** | 每日 token 配额（超额 429）；搜索/问答历史按用户隔离；用量趋势 + 告警看板 |
| **内容生命周期（M3）** | 笔记编辑、版本恢复、软删除/回收站、来源身份与定时重抓 |
| **知识治理（M3）** | 过期、近重、冲突、坏链、缺标签巡检与闭环待办 |
| **深度问答（M3）** | 问题拆解、多路 ACL 检索、智谱 rerank、PII 掩码与引用校验 |
| **企业连接器（M4）** | Confluence、飞书、Google Drive、SharePoint 只读增量同步 |
| **分发与协作（M4）** | 空间/标签/笔记订阅、站内通知、问答赞踩反馈 |
| **治理 Agent（M4）** | 白名单治理提案，space_admin 审批后由确定性执行器落地 |

---

## 架构

```
前端 (Next.js)        登录 / 检索 / 问答 / 图谱 / Wiki / 历史 / 管理后台
     │
后端 API (FastAPI)    /auth /ingest /search /qa /graph /notes /wiki /spaces /system
     │                （除 /auth/login 外都需 JWT；入库等写操作按空间角色校验）
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
├── README.md / AGENTS.md / CLAUDE.md / PROGRESS.md
├── docs/                                    # api-contract / architecture / operations
├── sql/                                     # 数据库 schema（00 入口按序执行 01~34）
│   ├── 01_extensions … 06_jobs              # 扩展 / 笔记 / 图谱 / wiki / 历史 / 队列
│   ├── 07_chunks.sql                        # 文档分块表 note_chunks
│   ├── 08_auth.sql                          # users + token_usage 账本
│   ├── 09_history_user.sql                  # 历史表加 user_id（按用户隔离）
│   ├── 10_user_username.sql                 # users 加 username（用户名登录）
│   ├── 11~13                                # 审计日志 / 账号安全 / 双 token 撤销
│   ├── 14~19                                # M1：笔记列表列 / 标签词表 / Q&A 沉淀 / qa_gen job / MCP token
│   ├── 18, 20~24                            # M2：空间归属 / default 成员回填 / space_id 非空与删除约束
│   ├── 25~28                                # M3：生命周期 / 治理 / jobs / 深度问答轨迹
│   └── 29~33                                # M4：连接器 / 分发 / 反馈 / Agent / jobs
│
├── backend/                                 # Python FastAPI
│   ├── main.py / config.py / db.py / mcp_server.py / requirements.txt
│   ├── routers/        auth · ingest · search · qa · graph · notes · wiki
│   │                   · tags · spaces · governance · connectors · collaboration · agent
│   ├── workers/        job_runner · ingest_worker · compile_worker · qa_gen_worker
│   └── services/       auth · quota · usage · spaces · llm · embedder · fetcher
│       │               · es · storage · chunker
│       └── providers/  策略层：base 抽象 + glm 智谱实现 + 工厂
│
├── frontend/                                # Next.js（App Router）
│   ├── app/            login · search · qa · graph · wiki · notes · spaces · history
│   │                   · admin/(ingest · users · tags · usage · mcp)
│   ├── components/      AppShell · AuthProvider · SpacesProvider · Sidebar · TopBar · SpaceSwitcher · SystemStatus …
│   └── lib/            api · types · forceLayout · sse
│
├── deploy/                                  # ES、备份与 systemd 配置
└── scripts/fuxi.py                          # 唯一 Python 运维入口
```

---

## 快速开始

> 依赖 PostgreSQL（带 pgvector ≥ 0.5）。Elasticsearch / R2 可选（不配则自动降级）。

### 1. 数据库

```bash
# PostgreSQL 16+ 且装好 pgvector 扩展
createdb fuxi
psql -d fuxi -f sql/00_init.sql      # 按序执行 01~34，创建全部表/索引
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
PYTHONPATH=. python ../scripts/fuxi.py admin \
  --username admin --email you@example.com --password '你的强密码'
```

打开 http://localhost:8000/docs 看交互式 API 文档。

开发与回归测试使用独立依赖：

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev        # 开发；生产用 npm run build && npm start
```

浏览器开前端地址 → 用刚建的账号登录。

---

## API

所有业务接口挂在 `/api` 下；Web 使用 httpOnly Cookie，移动端使用
`Authorization: Bearer <access_token>`。除登录和刷新外均需鉴权；写操作按空间角色校验。
完整契约见 [docs/api-contract.md](docs/api-contract.md)。

```bash
# 登录（用户名或邮箱皆可）→ 拿 token
curl -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin","password":"你的密码","client":"mobile"}'
# → {"access_token":"<jwt>","refresh_token":"<jwt>","user":{...}}

# 链接入库（目标空间 editor+）
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

- [x] 数据库 schema（笔记 / 实体 / 关系 / wiki / 历史 / 队列 / 分块 / 用户 / 用量 / Q&A 沉淀 / 标签词表 / MCP token / 空间·成员）
- [x] 入库链路（抓取 → 提炼 → 分块 → 向量化 → 写库 + 原始文件落盘）
- [x] 检索（ES+ik 关键词 + pgvector 语义 + RRF 混合）+ 搜索历史
- [x] RAG 问答（同步 + SSE 流式 + 四种角色风格 + Q&A 回灌）+ 问答历史
- [x] 知识图谱（实体共现 → 可视化）
- [x] Wiki 编译
- [x] 笔记列表 / 浏览页（分页 + 筛选）
- [x] 标签治理（受控词表 + 归并）
- [x] MCP Server（8 个只读工具 + Bearer API token，按空间绑定）
- [x] 空间（Spaces）多团队隔离 + 双层角色（系统级 + 空间级 viewer/editor/space_admin）
- [x] 前端 Web 界面（含登录页 + 空间切换 / 管理 + 管理后台：入库 / 用户 / 标签 / 用量 / MCP）
- [x] 鉴权（JWT，用户名/邮箱登录）+ 双层角色 + 每日 token 配额（429）+ 按用户隔离历史 + 用量看板
- [x] 统一 Python 运维入口（管理员、维护、索引、演示数据、生产验收）

详细进度见 [PROGRESS.md](PROGRESS.md)。
最终架构见 [docs/architecture.md](docs/architecture.md)，部署与运维见
[docs/operations.md](docs/operations.md)。

---

## 设计原则

- **存储简单优先** — PostgreSQL + pgvector 一个库同时承载结构化数据和向量，能不引入新组件就不引入
- **机械活给脚本，语义活给 LLM** — 抓取、索引、打分用代码；摘要、实体、判断用 GLM
- **入库异步** — 慢操作不阻塞接口，前端轮询状态
- **依赖只在 services 层 new** — 换 LLM/Embedding 走 `providers/` 策略层，换存储/检索改 `.env`
- **共享语料 + 空间隔离 + 角色策展** — 空间内共享语料跨全库检索，不同空间内容隔离；入库等策展操作收归空间角色，预算靠每日配额护栏
