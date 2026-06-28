-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";          -- pgvector 语义搜索
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- 模糊匹配 / trigram 索引
