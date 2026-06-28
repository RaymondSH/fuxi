-- ============================================================
-- 用户名 username：登录可用 用户名 或 邮箱
-- 幂等迁移（既用于全新建库 00_init，也用于线上增量）
-- 依赖 08_auth.sql 的 users 表
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;

-- 部分唯一索引：username 唯一，但允许历史行为 NULL（NULL 不参与唯一约束）
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
    ON users (username) WHERE username IS NOT NULL;
