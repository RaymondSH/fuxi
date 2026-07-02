-- M1 步骤2：标签治理 —— 受控词表 + 归并。
--   tags 是受控词表（规范名），不是从 notes.tags 派生的统计。
--   notes.tags 仍是自由 TEXT[]；归并时物理回写 notes.tags（array_replace）+ 同步 ES。
--   merge_into 指向归并后的规范名（被归并的标签 status='merged'）。

CREATE TABLE IF NOT EXISTS tags (
    name         TEXT PRIMARY KEY,                       -- 规范名（小写归一由后端处理，此处原样存）
    aliases      TEXT[] NOT NULL DEFAULT '{}',           -- 别名/同义，命中即映射回规范名
    description  TEXT,
    status       TEXT NOT NULL DEFAULT 'active',         -- active | merged | deprecated
    merged_into  TEXT REFERENCES tags(name) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 按状态查、按归并目标查
CREATE INDEX IF NOT EXISTS idx_tags_status ON tags(status);
CREATE INDEX IF NOT EXISTS idx_tags_merged_into ON tags(merged_into) WHERE merged_into IS NOT NULL;
