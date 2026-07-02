-- M4：企业连接器与远端对象幂等映射。
CREATE TABLE connector_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    space_id UUID NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('confluence','feishu','google_drive','sharepoint')),
    name TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    credentials BYTEA NOT NULL,
    sync_cursor TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','error')),
    error_msg TEXT,
    last_synced_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE connector_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connector_id UUID NOT NULL REFERENCES connector_accounts(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    note_id UUID REFERENCES notes(id) ON DELETE SET NULL,
    remote_version TEXT,
    remote_modified_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','error')),
    metadata JSONB NOT NULL DEFAULT '{}',
    error_msg TEXT,
    synced_at TIMESTAMPTZ,
    UNIQUE (connector_id, external_id)
);
CREATE INDEX idx_connector_accounts_space ON connector_accounts(space_id);
CREATE INDEX idx_connector_items_note ON connector_items(note_id);

ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS connector_id UUID
    REFERENCES connector_accounts(id) ON DELETE SET NULL;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS external_id TEXT;

