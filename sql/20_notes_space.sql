-- M2 步骤1：notes 加归属列 —— 空间 + 创建者。
--   space_id   笔记所属空间。此处兼容式加列，最终由 24_space_hardening 收紧为 NOT NULL + RESTRICT。
--              迁移前历史数据 space_id 为 NULL，此脚本回填到 default 空间。
--   created_by 入库者（FK users，ON DELETE SET NULL）。M1 前入库不记 user，历史留 NULL。
--
--   依赖：18_spaces.sql 先建 spaces 表 + default 空间。
--   幂等：ADD COLUMN IF NOT EXISTS + 回填 WHERE space_id IS NULL（重跑安全）。

ALTER TABLE notes ADD COLUMN IF NOT EXISTS space_id UUID REFERENCES spaces(id) ON DELETE SET NULL;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- 部分索引：只索引已入库完成的笔记的 space_id（检索主路径只看 done）
CREATE INDEX IF NOT EXISTS idx_notes_space ON notes (space_id) WHERE ingest_status = 'done';

-- 回填：现有笔记归入 default 空间
UPDATE notes
SET space_id = (SELECT id FROM spaces WHERE is_default)
WHERE space_id IS NULL;
