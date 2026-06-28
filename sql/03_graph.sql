-- 知识图谱：实体表（节点）
CREATE TABLE entities (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    type        TEXT NOT NULL                       -- 'company' | 'person' | 'concept' | 'product' | 'event' | 'place'
                CHECK (type IN ('company', 'person', 'concept', 'product', 'event', 'place')),
    aliases     TEXT[] NOT NULL DEFAULT '{}',       -- 别名，如"爱科赛博"和"AESC"指同一实体
    description TEXT,
    embedding   vector(1536),                       -- 实体向量，用于实体消歧
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, type)
);

CREATE INDEX idx_entities_type    ON entities (type);
CREATE INDEX idx_entities_aliases ON entities USING GIN (aliases);
CREATE INDEX idx_entities_name_trgm ON entities USING GIN (name gin_trgm_ops);

-- 知识图谱：关系表（边）
CREATE TABLE relations (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id   UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type  TEXT NOT NULL,                   -- 'competitor_of' | 'subsidiary_of' | 'invested_in' 等，开放枚举
    excerpt        TEXT,                            -- 关系来源原文片段
    note_id        UUID REFERENCES notes(id) ON DELETE SET NULL,
    confidence     REAL NOT NULL DEFAULT 1.0        -- AI 提取的置信度 0-1
                   CHECK (confidence BETWEEN 0 AND 1),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_relations_from   ON relations (from_entity_id);
CREATE INDEX idx_relations_to     ON relations (to_entity_id);
CREATE INDEX idx_relations_type   ON relations (relation_type);
CREATE INDEX idx_relations_note   ON relations (note_id);

-- 笔记与实体的多对多关联（一篇笔记里提到了哪些实体）
CREATE TABLE note_entities (
    note_id    UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    entity_id  UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    mention_count INT NOT NULL DEFAULT 1,
    PRIMARY KEY (note_id, entity_id)
);

CREATE INDEX idx_note_entities_entity ON note_entities (entity_id);

-- ── 图谱视图：直接服务 GET /api/graph，无需应用层现算 ──

-- 每个实体被多少篇笔记提及（API: node.count，前端据此算节点半径）
CREATE VIEW entity_note_counts AS
SELECT entity_id, COUNT(*)::int AS note_count
FROM note_entities
GROUP BY entity_id;

-- 实体共现边：两个实体出现在同一篇笔记里就连一条边（API: edges）
-- entity_id 升序去重，得到无向边 + 共现权重
CREATE VIEW entity_cooccurrence AS
SELECT a.entity_id AS from_id,
       b.entity_id AS to_id,
       COUNT(*)::int AS weight
FROM note_entities a
JOIN note_entities b
  ON a.note_id = b.note_id AND a.entity_id < b.entity_id
GROUP BY a.entity_id, b.entity_id;
