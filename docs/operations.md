# fuxi · 部署与运维

本文档是 v0.8.0 的最终部署、备份、恢复和验收说明。系统当前以 HTTP 运行，不包含 HTTPS
或证书配置。

## 1. 生产环境

生产服务器通过 `ssh linux-server` 登录，项目目录为 `/opt/fuxi`。

| 服务 | 地址 | 说明 |
|------|------|------|
| Web | `http://118.25.93.30:19000` | Next.js，对外入口并反代 `/api` 与 `/mcp` |
| Backend | `127.0.0.1:8000` | FastAPI，仅本机 |
| PostgreSQL | `127.0.0.1:5432` | PostgreSQL 18 + pgvector 0.8.3 |
| Elasticsearch | `127.0.0.1:9200` | ES 8.17.6 + ik，Docker 单节点 |
| Redis | `127.0.0.1:6379` | 预留基础设施 |

systemd 服务：

- `fuxi-backend`
- `fuxi-frontend`
- `fuxi-worker`
- `fuxi-maintenance.timer`
- `fuxi-backup.timer`

## 2. 初始化与升级

全新数据库按 SQL 入口初始化：

```bash
cd /opt/fuxi
sudo -u postgres psql -v ON_ERROR_STOP=1 -d fuxi -f sql/00_init.sql
```

已有环境升级前必须先备份，再按尚未执行的 SQL 编号顺序运行迁移。不要在已有数据库上重跑
`00_init.sql`。SQL 01~33 已覆盖鉴权、审计、空间 ACL、生命周期、治理、连接器、通知和 Agent。

后端：

```bash
cd /opt/fuxi/backend
.venv/bin/pip install -r requirements.txt
sudo systemctl restart fuxi-backend fuxi-worker
```

前端：

```bash
cd /opt/fuxi/frontend
npm install
npm run build
sudo systemctl restart fuxi-frontend
```

检查：

```bash
systemctl is-active fuxi-backend fuxi-frontend fuxi-worker
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:19000/login >/dev/null
```

## 3. 统一运维脚本

所有 Python 运维命令统一从项目根目录执行：

```bash
cd /opt/fuxi
PYTHONPATH=backend backend/.venv/bin/python scripts/fuxi.py --help
```

| 子命令 | 用途 |
|--------|------|
| `admin` | 创建、重置并提升管理员 |
| `maintenance` | 将到期刷新、治理扫描、连接器同步和 Agent 规划加入任务队列 |
| `reindex` | 用 PostgreSQL 中的有效笔记重建 Elasticsearch 内容 |
| `seed-demo` | 幂等写入演示笔记、实体和 Wiki |
| `verify-core` | 验收 Cookie、refresh、worker、空间 ACL、图谱、标签和 MCP |
| `verify-advanced` | 验收生命周期、回收站、通知、连接器加密和 Agent 队列 |

创建首个管理员：

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/fuxi.py admin \
  --username admin --email admin@example.com --password '替换为强密码'
```

ES 索引重建：

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/fuxi.py reindex
```

## 4. 生产验收

验收命令会创建带随机前缀的临时数据，并在 `finally` 中清理：

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/fuxi.py verify-core
PYTHONPATH=backend backend/.venv/bin/python scripts/fuxi.py verify-advanced
```

连接器真实平台验收还需要 Confluence、飞书、Google Drive 和 SharePoint 的外部凭据。凭据只能
通过后台或生产环境配置，不得写入仓库。

## 5. 备份

`fuxi-backup.timer` 每日 03:00 执行 `deploy/backup/pg_dump.sh`，备份产物位于
`/opt/fuxi/backups/`：

| 文件 | 内容 |
|------|------|
| `db-YYYYmmdd-HHMMSS.sql.gz` | PostgreSQL schema 与数据 |
| `raw-YYYYmmdd-HHMMSS.tar.gz` | 原始文件目录 |

默认保留 14 天。检查：

```bash
systemctl status fuxi-backup.timer --no-pager
systemctl start fuxi-backup.service
journalctl -u fuxi-backup.service -n 30 --no-pager
ls -lh /opt/fuxi/backups/
```

当前备份只落在服务器本地，异地备份仍需另行配置。

## 6. 恢复

恢复前停止写入服务并保留当前数据副本：

```bash
sudo systemctl stop fuxi-backend fuxi-worker
```

恢复数据库：

```bash
gunzip -c /opt/fuxi/backups/db-YYYYmmdd-HHMMSS.sql.gz \
  | sudo -u postgres psql -v ON_ERROR_STOP=1 -d fuxi
```

恢复原始文件：

```bash
mkdir -p /opt/fuxi/raw
tar -xzf /opt/fuxi/backups/raw-YYYYmmdd-HHMMSS.tar.gz -C /opt/fuxi/raw
```

重建 ES 并恢复服务：

```bash
cd /opt/fuxi
PYTHONPATH=backend backend/.venv/bin/python scripts/fuxi.py reindex
sudo systemctl start fuxi-backend fuxi-worker
systemctl is-active fuxi-backend fuxi-worker
```

最后执行两组生产验收，并人工检查登录、检索、问答和入库页面。

## 7. 常用排查

```bash
journalctl -u fuxi-backend -n 100 --no-pager
journalctl -u fuxi-frontend -n 100 --no-pager
journalctl -u fuxi-worker -n 100 --no-pager
curl -fsS http://127.0.0.1:9200/_cluster/health
sudo -u postgres psql -d fuxi -c "SELECT status,count(*) FROM jobs GROUP BY status;"
```

后端、前端和 worker 必须保持独立服务。任务失败应修复根因后重新入队，不要直接修改业务结果
或绕过状态机。
