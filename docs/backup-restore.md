# 备份与恢复

## 备份

定时备份由 systemd timer `fuxi-backup.timer` 每日 03:00 触发 `fuxi-backup.service`，后者执行 [`deploy/backup/pg_dump.sh`](../deploy/backup/pg_dump.sh)。

产物落在 `/opt/fuxi/backups/`：

| 文件 | 内容 |
|------|------|
| `db-YYYYmmdd-HHMMSS.sql.gz` | `pg_dump` 全库（schema + 数据，`--no-owner`） |
| `raw-YYYYmmdd-HHMMSS.tar.gz` | `STORAGE_LOCAL_ROOT`（默认 `/opt/fuxi/raw`）下的原始文件 |

保留 **14 天**（`KEEP_DAYS`），过期自动删除。

### 部署备份

```bash
# 服务器上
chmod +x /opt/fuxi/deploy/backup/pg_dump.sh
cp /opt/fuxi/deploy/backup/fuxi-backup.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now fuxi-backup.timer

# 验证：手动跑一次，看是否产出文件
systemctl start fuxi-backup.service
journalctl -u fuxi-backup.service -n 20 --no-pager
ls -lh /opt/fuxi/backups/
```

### 调整

环境变量覆盖（改 `fuxi-backup.service` 的 `Environment=` 或临时跑）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `BACKUP_DIR` | `/opt/fuxi/backups` | 备份输出目录 |
| `KEEP_DAYS` | `14` | 保留天数 |
| `PG_CONN` | `postgresql://fuxi:fuxi@localhost:5432/fuxi` | 数据库连接串 |
| `RAW_ROOT` | `/opt/fuxi/raw` | 原始文件根目录 |

---

## 恢复

> ⚠️ 恢复会覆盖目标库现有数据。先在备用环境验证备份可读，再在生产操作。

### 1. 数据库

```bash
# 解压并灌入（--no-owner 备份可不依赖原属主，直接灌进目标库）
gunzip -c /opt/fuxi/backups/db-YYYYmmdd-HHMMSS.sql.gz | \
  psql -v ON_ERROR_STOP=1 postgresql://fuxi:fuxi@localhost:5432/fuxi

# 若目标库已有数据会冲突：先重建空库再灌
sudo -u postgres dropdb fuxi
sudo -u postgres createdb -O fuxi fuxi
gunzip -c /opt/fuxi/backups/db-YYYYmmdd-HHMMSS.sql.gz | \
  psql -v ON_ERROR_STOP=1 postgresql://fuxi:fuxi@localhost:5432/fuxi
```

灌完后 **重建 ES 索引**（备份数据不含 ES，ES 可从 PG 重新索引）：

```bash
cd /opt/fuxi/backend && . .venv/bin/activate
PYTHONPATH=. python3 scripts/reindex_es.py
```

### 2. 原始文件

```bash
# 解压回 STORAGE_LOCAL_ROOT（默认 /opt/fuxi/raw）
mkdir -p /opt/fuxi/raw
tar -xzf /opt/fuxi/backups/raw-YYYYmmdd-HHMMSS.tar.gz -C /opt/fuxi/
```

### 3. 验证

```bash
# 后端重启加载恢复的数据
systemctl restart fuxi-backend
# 抽查：笔记数、最近入库
psql postgresql://fuxi:fuxi@localhost:5432/fuxi -c \
  "SELECT count(*) FROM notes; SELECT title, created_at FROM notes ORDER BY created_at DESC LIMIT 5;"
```

---

## 异地备份（建议，后续）

本批只在服务器本地落盘。单机即单点：磁盘故障会同时丢数据和备份。后续可：

- 用 `rsync`/`rclone` 把 `/opt/fuxi/backups/` 同步到对象存储（R2/S3）或另一台机器。
- 或直接把 `pg_dump` 产物上传 R2（复用现有 `R2_*` 凭据）。

此项不在 M0 范围，列为后续收尾。
