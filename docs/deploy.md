# 部署 / 运行环境

## linux-server（`ssh linux-server`）

Debian 12，root，sudo 免密，已有 Docker / nginx / Redis 等。**本地 Mac 无 Docker**，依赖都跑在这台服务器上。

### 已就绪的服务

| 服务 | 地址 | 说明 |
|------|------|------|
| PostgreSQL 18 | `127.0.0.1:5432` | 系统 apt 版（非 docker），已装 pgvector 0.8.3 |
| Redis | `127.0.0.1:6379` | 已在跑 |
| Elasticsearch 8.17.6 + ik | `127.0.0.1:9200` | Docker 容器 `fuxi-es`，单节点，关闭安全模块；中文关键词检索主路（见下「Elasticsearch」） |

> 服务器上另有 docker 版 postgres16/17/18（端口 13360/13370/13380）和 mysql。**fuxi 用的是系统 PG18 的 5432**，别混。

### fuxi 数据库

```
库：    fuxi
角色：  fuxi / 密码 fuxi（仅 localhost）
连接串：postgresql://fuxi:fuxi@localhost:5432/fuxi
```

schema（`sql/01~07`）已灌入并验证：10 张表（含 `note_chunks`）+ 2 视图（entity_note_counts / entity_cooccurrence）+ 3 个 HNSW 索引（notes.embedding / note_chunks.embedding / wiki_pages.embedding）。

重灌 schema（会保留已有数据，CREATE TABLE 若已存在会报错）：
```bash
scp sql/0*.sql linux-server:/tmp/
ssh linux-server 'for f in 01_extensions 02_notes 03_graph 04_wiki 05_history 06_jobs 07_chunks; do
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d fuxi -f /tmp/$f.sql; done'
```

> `07_chunks.sql` 新增 `note_chunks` 表并改了 `06_jobs.sql` 的 stage CHECK（加 `chunk` 和 `compile`）。重灌 `06_jobs.sql` 若已有旧 jobs 数据，ALTER 约束需手动执行（见该文件末注释）。

### 本地连服务器数据库（SSH 隧道）

Postgres 只绑 localhost，不对外暴露。本地开发时开隧道：
```bash
ssh -N -L 5432:127.0.0.1:5432 linux-server
# 之后本地 DATABASE_URL=postgresql://fuxi:fuxi@localhost:5432/fuxi 即可
```

## 当前运行实例（2026-06-28）

代码部署在 `/opt/fuxi`，前后端都跑在 linux-server 上。

| 服务 | 监听 | 访问 |
|------|------|------|
| 后端 FastAPI | `127.0.0.1:8000`（内部） | 由前端 `/api` 代理 |
| 前端 Next.js | `0.0.0.0:19000` | **http://118.25.93.30:19000** |

进程由 **systemd** 托管（开机自启 + `Restart=always`）：`fuxi-backend`、`fuxi-frontend`。
单元文件在 `/etc/systemd/system/fuxi-{backend,frontend}.service`。

- 后端 `.env` 的 `API_KEY` 已填入智谱密钥（经 `/etc/profile` 注入 + systemd `bash -lc` 包裹使对进程可见）→ 入库/检索/问答/Wiki 编译全链路可跑通。

### 常用运维

```bash
ssh linux-server 'systemctl status fuxi-backend fuxi-frontend'   # 状态
ssh linux-server 'systemctl restart fuxi-backend'                # 重启后端
ssh linux-server 'journalctl -u fuxi-backend -n 50 --no-pager'   # 看日志
```

### 更新代码后重新部署

```bash
# 本地：同步代码（务必 --exclude .venv，否则 --delete 会删坏服务器虚拟环境）
rsync -az --delete --exclude node_modules --exclude .next --exclude __pycache__ \
  --exclude .venv --exclude .env --exclude '*.pyc' --exclude '*.log' \
  backend frontend sql docs deploy scripts linux-server:/opt/fuxi/

# 服务器：后端依赖有变才需要 pip install，然后重启
ssh linux-server 'cd /opt/fuxi/backend && . .venv/bin/activate && pip install -q -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple; systemctl restart fuxi-backend'

# 服务器：前端改动要重新 build 再重启
ssh linux-server 'export PATH=/usr/local/bin:$PATH; cd /opt/fuxi/frontend && npm install --no-audit --no-fund && \
  BACKEND_ORIGIN=http://127.0.0.1:8000 npm run build && systemctl restart fuxi-frontend'
```

填密钥：编辑 `/opt/fuxi/backend/.env` 的 `API_KEY`（智谱密钥，聊天/视觉/向量共用），再 `ssh linux-server 'systemctl restart fuxi-backend'`。当前已填入并跑通。

## 后端环境变量（`.env`）

完整变量见 `backend/.env.example`，关键项：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PG 连接串（linux-server 上用 localhost） |
| `API_KEY` | 智谱密钥（聊天/视觉/向量共用） |
| `AI_BASE_URL` / `CHAT_MODEL` / `VISION_MODEL` / `EMBED_MODEL` / `EMBED_DIM` | 智谱 GLM 服务地址与模型（默认 `embedding-3` 1536 维） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `CHUNK_MIN_SIZE` | 文档分块参数（默认 800 / 120 / 80） |
| `STORAGE_BACKEND` | `local`（默认，落 `STORAGE_LOCAL_ROOT`）或 `r2`（Cloudflare R2，S3 兼容） |
| `STORAGE_LOCAL_ROOT` | local 后端落盘根目录（默认 `/opt/fuxi/raw`） |
| `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` / `R2_PUBLIC_BASE_URL` | R2 凭据（`STORAGE_BACKEND=r2` 时才用，留空自动回退 local） |
| `ES_URL` / `ES_TIMEOUT` | ES 地址与超时；留空则关键词路回退 PG ILIKE，填地址即走 ES |

## Elasticsearch（8 + ik 中文分词）

中文关键词检索主路，Docker 部署在 linux-server，仅绑 127.0.0.1（不对外）。

部署文件在 `deploy/es/`（`docker-compose.yml` + `Dockerfile.es`）：ES 8.17.6 单节点、`xpack.security.enabled=false`（开发单机用，免证书/免认证）、512m 堆、`fuxi-es` 容器、`es-data` 持久卷。ik 插件在镜像构建时由 `bin/elasticsearch-plugin install` 装入。

### 起服务

```bash
# 同步部署文件
rsync -az --exclude .env deploy/ linux-server:/opt/fuxi/deploy/

# 服务器构建并起容器（首次构建要拉 ES 镜像 + 装 ik，约几分钟）
ssh linux-server 'cd /opt/fuxi/deploy/es && docker compose up -d --build'

# 等 healthcheck 变 green
ssh linux-server 'docker inspect -f "{{.State.Health.Status}}" fuxi-es'
```

后端 `.env` 设 `ES_URL=http://127.0.0.1:9200`，重启 `fuxi-backend` 即生效。后端启动时 `es.ensure_index()` 自动建索引 `notes_v1`（ik_max_word 索引 / ik_smart 检索）。

### 验证 ik 分词

```bash
ssh linux-server 'curl -s "127.0.0.1:9200/notes_v1/_analyze" -H "Content-Type: application/json" \
  -d "{\"analyzer\":\"ik_max_word\",\"text\":\"自然语言处理\"}" | python3 -m json.tool'
# ik_max_word 细粒度：自然语言/自然/语言/处理
# ik_smart 粗粒度：自然语言/处理
```

### 回填已有笔记到 ES

新摄取的笔记会自动写 ES；存量笔记用 `scripts/reindex_es.py` 批量回填：

```bash
ssh linux-server 'cd /opt/fuxi/backend && . .venv/bin/activate && python scripts/reindex_es.py'
# 读所有 stage=done 的笔记，逐条 index_note，末尾 _refresh；打印写入数
```

### ES 不可达时

`services/es.py` 静默降级：所有 ES 调用失败不抛异常，关键词检索自动回退 PG ILIKE。所以即便 ES 挂了，检索/入库/问答仍可用（只是关键词命中变弱）。

## 云开放端口段：18200–19600

仅此范围对公网开放。

- **已占用**：18200/18300/18443（portainer）、18400/18600/18800（nginx）、18540（open-webui）。
- **计划占用**：`19000` 前端、`19100` 后端 API（可调整，避开已占用端口即可）。

数据库 / Redis 不在此列——它们只走 localhost + SSH 隧道，不开公网。
