-- M1 步骤6：MCP server 用的 API token（与登录用的 JWT 分开）。
--   MCP 客户端（如 Claude Desktop / 自建 Agent）用 Bearer <token> 调 /mcp。
--   token 明文只在创建时返回一次；库里存哈希（与 users.password_hash 同样的 bcrypt）。
--   管理员在后台建号式生成 / 撤销 token，不在登录体系内。
--
--   name        人类可读的名字（如「Claude Desktop」），便于在管理页区分
--   token_hash  bcrypt 哈希；校验时用 bcrypt.checkpw
--   prefix      token 明文的前 8 位，明文丢弃后仅靠它做「看一眼认出是哪个 token」
--   is_active   撤销即 false，校验时拒绝

CREATE TABLE IF NOT EXISTS mcp_tokens (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL,                  -- bcrypt（明文仅创建时返回一次）
    prefix      TEXT NOT NULL,                  -- 明文前 8 位，便于后台识别
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_mcp_tokens_active ON mcp_tokens (is_active);
