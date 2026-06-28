-- ============================================================
-- 笔记主表：每条入库内容对应一行
-- 列名与 backend/workers/ingest_worker.py 的 INSERT/UPDATE 严格对齐
-- ============================================================
CREATE TABLE notes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    url             TEXT,                           -- 原始链接，本地文件用 file:// 前缀
    source          TEXT,                           -- 展示文案，如 "report.pdf · 24页" / 域名（API: source）
    source_type     TEXT NOT NULL DEFAULT 'manual'  -- 'url'|'pdf'|'docx'|'xlsx'|'image'|'manual'|'idea'
                    CHECK (source_type IN ('url', 'pdf', 'docx', 'xlsx', 'image', 'manual', 'idea')),
    raw_path        TEXT,                           -- 原始文件在 S3/R2 的路径
    published_date  DATE,                           -- 原文发布日期，可空（API: date）
    summary         TEXT,                           -- AI 生成摘要（2-3句）
    key_points      TEXT[] NOT NULL DEFAULT '{}',   -- AI 生成要点列表
    content         TEXT,                           -- 正文全文（API: original 按段落切分返回）
    tags            TEXT[] NOT NULL DEFAULT '{}',
    related_note_ids UUID[] NOT NULL DEFAULT '{}',  -- 关联笔记（API: related_note_ids）
    embedding       vector(1536),                   -- 语义向量（智谱 embedding-3，dimensions=1536 对齐）
    ingest_status   TEXT NOT NULL DEFAULT 'pending' -- 'pending'|'processing'|'done'|'failed'
                    CHECK (ingest_status IN ('pending', 'processing', 'done', 'failed')),
    error_msg       TEXT,                           -- 失败时记录原因
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 更新时间自动维护（jobs / wiki_pages 共用此函数）
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER notes_updated_at
    BEFORE UPDATE ON notes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── 索引 ──
CREATE INDEX idx_notes_created_at  ON notes (created_at DESC);
CREATE INDEX idx_notes_tags        ON notes USING GIN (tags);
CREATE INDEX idx_notes_source_type ON notes (source_type);
CREATE INDEX idx_notes_status      ON notes (ingest_status);

-- 语义检索：HNSW 余弦索引（需 pgvector ≥ 0.5；embedding-3 向量已归一化，用 cosine）
-- HNSW 相比 IVFFlat 无需训练、召回-延迟曲线更好（见 demo 笔记 n3）
CREATE INDEX idx_notes_embedding   ON notes USING hnsw (embedding vector_cosine_ops);

-- 关键词检索 fallback（中文主路走 Elasticsearch，PG 这里兜底）
--   tsvector：英文 / 代码 token 全文检索
--   pg_trgm ：标题模糊 / 子串匹配
CREATE INDEX idx_notes_fts ON notes USING GIN (
    to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(content,''))
);
CREATE INDEX idx_notes_title_trgm  ON notes USING GIN (title gin_trgm_ops);
