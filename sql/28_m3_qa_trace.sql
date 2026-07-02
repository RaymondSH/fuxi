-- M3：记录标准/深度问答模式与可审计检索轨迹。

ALTER TABLE qa_history ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'standard'
    CHECK (mode IN ('standard','agentic'));
ALTER TABLE qa_history ADD COLUMN IF NOT EXISTS trace JSONB NOT NULL DEFAULT '{}';
ALTER TABLE qa_history ADD COLUMN IF NOT EXISTS verification JSONB NOT NULL DEFAULT '{}';

