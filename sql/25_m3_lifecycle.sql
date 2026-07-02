-- M3：来源身份、笔记版本、软删除与刷新状态。

CREATE TABLE IF NOT EXISTS source_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    space_id        UUID NOT NULL REFERENCES spaces(id) ON DELETE RESTRICT,
    source_type     TEXT NOT NULL,
    locator         TEXT NOT NULL,
    display_name    TEXT,
    content_hash    TEXT,
    etag            TEXT,
    last_modified   TEXT,
    refresh_policy  TEXT NOT NULL DEFAULT 'manual'
                    CHECK (refresh_policy IN ('manual','daily','weekly')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','broken','disabled')),
    last_checked_at TIMESTAMPTZ,
    next_refresh_at TIMESTAMPTZ,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (space_id, locator)
);

ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES source_documents(id) ON DELETE SET NULL;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS revision INT NOT NULL DEFAULT 1;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id) ON DELETE SET NULL;

INSERT INTO source_documents (id, space_id, source_type, locator, display_name, content_hash)
SELECT uuid_generate_v5(n.id, 'source-document'), n.space_id, n.source_type,
       COALESCE(NULLIF(n.url, ''), 'note://' || n.id::text),
       COALESCE(NULLIF(n.source, ''), n.title),
       md5(COALESCE(n.content, ''))
FROM notes n
WHERE n.source_document_id IS NULL
ON CONFLICT (space_id, locator) DO NOTHING;

UPDATE notes n
SET source_document_id = s.id
FROM source_documents s
WHERE n.source_document_id IS NULL
  AND s.space_id = n.space_id
  AND s.locator = COALESCE(NULLIF(n.url, ''), 'note://' || n.id::text);

CREATE TABLE IF NOT EXISTS note_versions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    note_id     UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    version_no  INT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('edit','refresh','restore','delete')),
    snapshot    JSONB NOT NULL,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (note_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_notes_active_space ON notes (space_id, updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_note_versions_note ON note_versions (note_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_source_refresh ON source_documents (next_refresh_at)
    WHERE status = 'active' AND refresh_policy <> 'manual';

