-- ============================================================
-- 历史按用户隔离：给 search_history / qa_history 加 user_id
-- 幂等（IF NOT EXISTS）：既用于全新建库（00_init），也用于线上增量迁移
-- 依赖 08_auth.sql 的 users 表，故排在其后执行
-- ============================================================

ALTER TABLE search_history
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE qa_history
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- 按用户回查历史
CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qa_history_user     ON qa_history (user_id, created_at DESC);

-- 历史遗留行（seed / 鉴权上线前）user_id 为 NULL：普通用户查不到，管理员可看全部。
