-- M2 步骤1：mcp_tokens 绑空间。
--   MCP token 现在是全库只读（绕过空间 ACL）。M2 后每个 token 绑定一个空间，
--   工具调用时按该空间过滤（等价于该空间 viewer）。
--   本步骤先加列并回填；24_space_hardening 最终设 NOT NULL + ON DELETE CASCADE。
--
--   依赖：18_spaces.sql 先建 spaces 表 + default 空间。
--   幂等：ADD COLUMN IF NOT EXISTS + 回填 WHERE space_id IS NULL。

ALTER TABLE mcp_tokens ADD COLUMN IF NOT EXISTS space_id UUID REFERENCES spaces(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_mcp_tokens_space ON mcp_tokens (space_id) WHERE is_active;

UPDATE mcp_tokens
SET space_id = (SELECT id FROM spaces WHERE is_default)
WHERE space_id IS NULL;
