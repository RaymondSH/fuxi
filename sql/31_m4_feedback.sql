-- M4：问答反馈。
CREATE TABLE qa_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    qa_history_id UUID NOT NULL REFERENCES qa_history(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating TEXT NOT NULL CHECK (rating IN ('up','down')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (qa_history_id,user_id)
);

