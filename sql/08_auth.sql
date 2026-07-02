-- ============================================================
-- 用户体系 + token 用量账本
-- 列名与 backend/services/auth.py、routers/auth.py、services/quota.py 对齐
-- 设计见 docs/auth-design.md
-- ============================================================

-- 用户：管理员建号，不开放自助注册
CREATE TABLE users (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email             TEXT UNIQUE NOT NULL,
    password_hash     TEXT NOT NULL,                 -- bcrypt（直接用 bcrypt 库，弃 passlib）
    display_name      TEXT,
    role              TEXT NOT NULL DEFAULT 'member'  -- 'member'|'admin'
                      CHECK (role IN ('member', 'admin')),
    daily_token_limit INT,                           -- 每日 token 上限；NULL=用 config 默认值
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,  -- 停用即拒绝登录 / 鉴权
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- updated_at 自动维护（函数定义在 02_notes.sql）
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- token 用量明细账本：每次计费的 LLM/Embedding 调用记一行，便于审计 + admin 看板
-- 配额检查 = 按 (user_id, usage_day) 聚合 total_tokens 与 daily_token_limit 比较
CREATE TABLE token_usage (
    id                BIGSERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_day         DATE NOT NULL,                 -- 按 USAGE_TZ 算的自然日
    operation         TEXT NOT NULL,                 -- 'qa'|'qa_stream'|'search_semantic'|'ingest'（入库 refine/embed/describe_image 合计）
    prompt_tokens     INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens      INT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_token_usage_user_day ON token_usage (user_id, usage_day);
