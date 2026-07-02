-- M1 步骤3：文档→Q&A 生成 + 回灌检索（D①）。
--   generated_qa 存「针对某篇笔记自动生成的问答对」。
--   生成时把问题向量化写进 embedding，问答检索时按余弦 top-2 回灌进 RAG 上下文，
--   让模型能复用历史沉淀的问答（同义问题不必每次重新推一遍）。
--
--   note_id 删除即级联清理（ON DELETE CASCADE）。
--   重跑生成时由 worker 先删旧问答再写新问答（同一笔记只保留最新一批）。

CREATE TABLE IF NOT EXISTS generated_qa (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    note_id     UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    embedding   vector(1536),                    -- 问题向量，回灌检索用（智谱 embedding-3，dimensions=1536）
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_qa_note     ON generated_qa (note_id);
-- 语义回灌：HNSW 余弦索引（embedding-3 已归一化，用 cosine），与 notes.embedding 同构
CREATE INDEX IF NOT EXISTS idx_generated_qa_embedding ON generated_qa USING hnsw (embedding vector_cosine_ops);
