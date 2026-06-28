-- 笔记分块：把长文档切成 chunk 再各算向量，语义检索落到 chunk 级再聚合回 note。
-- 与 notes.embedding（文档级摘要向量）并存：notes.embedding 作概览/降级，note_chunks 作主召回路。
CREATE TABLE note_chunks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    note_id     UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,                -- 块序号，从 0 开始
    content     TEXT NOT NULL,                -- 该块纯文本
    embedding   vector(1536),                -- 智谱 embedding-3，dim 与 notes.embedding 对齐
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (note_id, chunk_index)
);

-- 语义检索：HNSW 余弦索引（需 pgvector ≥ 0.5；embedding-3 向量已归一化）
CREATE INDEX idx_note_chunks_embedding ON note_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_note_chunks_note_id  ON note_chunks (note_id);
