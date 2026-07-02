-- JWT 双 token 撤销机制：refresh_tokens（可撤销的长效 token）+ token_revocations（access 黑名单）。
--
-- 配合 services/auth.py：
-- - access token 短时（15min），claims 含 jti；登出/改密时把 jti 写 token_revocations（TTL=access 有效期）。
-- - refresh token 长时（7d），落 refresh_tokens 表；登出/改密/停用时撤销（revoked_at 置位）。
-- - 改密 / 停用账号 → revoke_all_user_tokens(uid)：撤销其所有 refresh + 把当前 access jti 入黑名单（强制重登）。
--
-- 幂等：CREATE TABLE IF NOT EXISTS。重跑安全。

-- refresh token 记录：每个签发的 refresh 一行，撤销时置 revoked_at。
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti         TEXT NOT NULL UNIQUE,        -- 与 JWT 的 jti claim 对应
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,                  -- NULL=有效；非空=已撤销
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_agent  TEXT,
    ip          TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens (user_id, revoked_at);
CREATE INDEX IF NOT EXISTS idx_refresh_expires ON refresh_tokens (expires_at);

-- access token 黑名单：登出时把 access jti 写入，get_current_user 校验是否在此表。
-- 行随 access 过期自动失效（可定期清理 expires_at < NOW() 的行）。
CREATE TABLE IF NOT EXISTS token_revocations (
    jti         TEXT PRIMARY KEY,            -- access token 的 jti
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,        -- = 对应 access 的 exp；过期后该行无意义
    reason      TEXT,                        -- logout / password_change / deactivate
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_revocations_expires ON token_revocations (expires_at);
