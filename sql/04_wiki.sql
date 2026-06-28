-- Wiki 主题页（多笔记编译成品）
CREATE TABLE wiki_pages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug            TEXT NOT NULL UNIQUE,           -- URL 路径，如 'aidc-power-supply'
    title           TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',       -- 编译后的正文 Markdown（纯文本 fallback）
    -- 结构化正文：前端按段落渲染、每段带引用来源（API: sections）
    --   [{ "heading": "...", "paragraphs": [{ "text": "...", "cites": ["n6"] }] }]
    sections        JSONB,
    -- 观点矛盾：编译时 Claude 标出的对立判断（API: conflict）
    --   { "topic": "...", "sides": [{ "note_id": "n1", "claim": "..." }] }
    conflict        JSONB,
    summary         TEXT,                           -- 一句话概括
    tags            TEXT[] NOT NULL DEFAULT '{}',
    source_note_ids UUID[] NOT NULL DEFAULT '{}',   -- 编译来源的 note id 列表
    embedding       vector(1536),
    compiled_at     TIMESTAMPTZ,                    -- 最近一次编译时间
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER wiki_pages_updated_at
    BEFORE UPDATE ON wiki_pages
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_wiki_tags      ON wiki_pages USING GIN (tags);
CREATE INDEX idx_wiki_embedding ON wiki_pages USING hnsw (embedding vector_cosine_ops);

-- 笔记反向引用 wiki 页（一篇笔记可以被多个 wiki 页引用）
CREATE TABLE note_wiki (
    note_id      UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    wiki_page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, wiki_page_id)
);
