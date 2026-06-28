-- 搜索历史
CREATE TABLE search_history (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query       TEXT NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'hybrid'      -- 'hybrid'|'keyword'|'semantic'|'tag'（API: mode）
                CHECK (mode IN ('hybrid', 'keyword', 'semantic', 'tag')),
    time_filter TEXT NOT NULL DEFAULT 'all'         -- 'all'|'today'|'week'|'month'|'year'
                CHECK (time_filter IN ('all', 'today', 'week', 'month', 'year')),
    tags        TEXT[] NOT NULL DEFAULT '{}',       -- 检索时叠加的标签筛选
    result_ids  UUID[] NOT NULL DEFAULT '{}',       -- 返回的 note/wiki id 列表
    result_count INT NOT NULL DEFAULT 0,            -- 命中数（API: hits）
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_search_history_created ON search_history (created_at DESC);
-- trigram 索引支持历史记录里按关键词回查
CREATE INDEX idx_search_history_query   ON search_history USING GIN (query gin_trgm_ops);

-- 问答历史（RAG 对话）
CREATE TABLE qa_history (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id   UUID NOT NULL DEFAULT uuid_generate_v4(), -- 同一次多轮对话共享 session_id
    question     TEXT NOT NULL,
    answer       TEXT NOT NULL,
    source_ids   UUID[] NOT NULL DEFAULT '{}',      -- 回答引用的 note/wiki id
    source_excerpts JSONB,                          -- [{id, title, excerpt}, ...] 引用片段
    model        TEXT NOT NULL DEFAULT 'claude-opus-4-8',  -- 与 config.CLAUDE_MODEL 一致
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_qa_history_session   ON qa_history (session_id, created_at);
CREATE INDEX idx_qa_history_created   ON qa_history (created_at DESC);
