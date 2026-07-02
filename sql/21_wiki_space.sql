-- M2 步骤1：wiki_pages 加空间归属。
--   wiki 是同主题多篇笔记的编译产物，必然属于某空间（编译时只取同空间笔记）。
--   历史数据回填 default 空间。
--
--   依赖：18_spaces.sql 先建 spaces 表 + default 空间。
--   幂等：ADD COLUMN IF NOT EXISTS + 回填 WHERE space_id IS NULL。

-- 最终由 24_space_hardening 收紧为 NOT NULL + ON DELETE RESTRICT。
ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS space_id UUID REFERENCES spaces(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_wiki_pages_space ON wiki_pages (space_id);

UPDATE wiki_pages
SET space_id = (SELECT id FROM spaces WHERE is_default)
WHERE space_id IS NULL;
