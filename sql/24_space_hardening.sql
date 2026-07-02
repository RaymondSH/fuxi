-- M0/M2 收口：空间归属非空 + 安全删除语义。
--
-- notes / wiki_pages：有内容时禁止删除空间（RESTRICT），避免产生无归属内容。
-- mcp_tokens：删除空间时级联删除 token，避免 space_id=NULL 被解释为全库权限。
-- 执行前先把历史 NULL 回填到 default 空间，再设 NOT NULL。

DO $$
DECLARE
    default_space UUID;
BEGIN
    SELECT id INTO default_space FROM spaces WHERE is_default LIMIT 1;
    IF default_space IS NULL THEN
        RAISE EXCEPTION 'default space missing';
    END IF;

    UPDATE notes SET space_id = default_space WHERE space_id IS NULL;
    UPDATE wiki_pages SET space_id = default_space WHERE space_id IS NULL;
    UPDATE mcp_tokens SET space_id = default_space WHERE space_id IS NULL;
END $$;

ALTER TABLE notes ALTER COLUMN space_id SET NOT NULL;
ALTER TABLE wiki_pages ALTER COLUMN space_id SET NOT NULL;
ALTER TABLE mcp_tokens ALTER COLUMN space_id SET NOT NULL;

ALTER TABLE notes DROP CONSTRAINT IF EXISTS notes_space_id_fkey;
ALTER TABLE notes
    ADD CONSTRAINT notes_space_id_fkey
    FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE RESTRICT;

ALTER TABLE wiki_pages DROP CONSTRAINT IF EXISTS wiki_pages_space_id_fkey;
ALTER TABLE wiki_pages
    ADD CONSTRAINT wiki_pages_space_id_fkey
    FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE RESTRICT;

ALTER TABLE mcp_tokens DROP CONSTRAINT IF EXISTS mcp_tokens_space_id_fkey;
ALTER TABLE mcp_tokens
    ADD CONSTRAINT mcp_tokens_space_id_fkey
    FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE CASCADE;
