-- M3：治理扫描运行记录与幂等待办。

CREATE TABLE IF NOT EXISTS governance_runs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    space_id    UUID NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','done','failed')),
    stats       JSONB NOT NULL DEFAULT '{}',
    error_msg   TEXT,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS governance_issues (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    space_id        UUID NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    note_id         UUID REFERENCES notes(id) ON DELETE CASCADE,
    issue_type      TEXT NOT NULL
                    CHECK (issue_type IN ('stale','duplicate','conflict','broken_link','missing_tags')),
    severity        TEXT NOT NULL DEFAULT 'medium'
                    CHECK (severity IN ('low','medium','high')),
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','resolved','ignored')),
    fingerprint     TEXT NOT NULL,
    title           TEXT NOT NULL,
    evidence        JSONB NOT NULL DEFAULT '{}',
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    resolution_note TEXT,
    UNIQUE (space_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_governance_issues_queue
    ON governance_issues (space_id, status, severity, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_governance_runs_space
    ON governance_runs (space_id, created_at DESC);

