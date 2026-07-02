#!/usr/bin/env bash
# fuxi 数据库 + 原始文件备份。
#
# 产物（写到 $BACKUP_DIR，默认 /opt/fuxi/backups）：
#   db-YYYYmmdd-HHMMSS.sql.gz      pg_dump 全库（schema + 数据）
#   raw-YYYYmmdd-HHMMSS.tar.gz     STORAGE_LOCAL_ROOT 下的原始文件（pdf/docx/图片…）
#
# 保留策略：$KEEP_DAYS 天前的备份自动删除（默认 14）。
# 设计为 systemd timer 每日 03:00 调用；失败时非零退出，stderr 进 journald。
#
# 用法：直接跑 / 部署到服务器后由 fuxi-backup.timer 触发。
#   可选环境变量覆盖：BACKUP_DIR / KEEP_DAYS / PG_CONN / RAW_ROOT
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/fuxi/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
PG_CONN="${PG_CONN:-postgresql://fuxi:fuxi@localhost:5432/fuxi}"
RAW_ROOT="${RAW_ROOT:-/opt/fuxi/raw}"

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] fuxi backup start → $BACKUP_DIR"

# ── 1. 数据库 ──
DB_OUT="$BACKUP_DIR/db-$STAMP.sql.gz"
# --no-owner: 恢复时不依赖原属主（直接灌进目标库即可，避免角色不存在报错）
if pg_dump --no-owner "$PG_CONN" | gzip -c > "$DB_OUT"; then
  echo "  db  → $DB_OUT ($(du -h "$DB_OUT" | cut -f1))"
else
  echo "  db  FAILED" >&2; exit 1
fi

# ── 2. 原始文件（摄取时落盘的源文件）──
# 原始文件可能很大；tar 走 gzip。若目录不存在或为空则跳过（不视为失败）。
if [ -d "$RAW_ROOT" ] && [ -n "$(ls -A "$RAW_ROOT" 2>/dev/null)" ]; then
  RAW_OUT="$BACKUP_DIR/raw-$STAMP.tar.gz"
  if tar -czf "$RAW_OUT" -C "$(dirname "$RAW_ROOT")" "$(basename "$RAW_ROOT")"; then
    echo "  raw → $RAW_OUT ($(du -h "$RAW_OUT" | cut -f1))"
  else
    echo "  raw FAILED" >&2; exit 1
  fi
else
  echo "  raw → 跳过（$RAW_ROOT 不存在或为空）"
fi

# ── 3. 清理过期备份 ──
echo "  清理 ${KEEP_DAYS} 天前的备份"
find "$BACKUP_DIR" -name 'db-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'raw-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "[$(date -Iseconds)] fuxi backup done"
