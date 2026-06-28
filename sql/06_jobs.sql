-- 异步任务队列（轻量替代方案，不需要 Celery 时直接用这张表 + pg LISTEN/NOTIFY）
-- 同时承担「入库页进度卡片」的数据源：GET /api/ingest/jobs 直接查这张表
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type    TEXT NOT NULL                       -- 'ingest' | 'compile' | 'graph_extract' | 'reindex'
                CHECK (job_type IN ('ingest', 'compile', 'graph_extract', 'reindex')),
    payload     JSONB NOT NULL DEFAULT '{}',        -- 任务参数，如 {url: "..."}
    -- 队列状态：worker 视角用 queued/running；API 层映射成前端的 pending/processing
    --   queued→pending, running→processing, done→done, failed→failed
    status      TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'failed')),

    -- ── 以下字段仅 ingest 任务填充，驱动入库页的进度卡片 ──
    note_id     UUID REFERENCES notes(id) ON DELETE CASCADE,  -- 关联笔记
    title       TEXT,                              -- 卡片标题（抓到标题前可先用文件名/链接）
    sub         TEXT,                              -- 副标题，如 "14.2 MB · 38 页"
    stage       TEXT                               -- 细粒度流水线阶段（API: stage）
                CHECK (stage IS NULL OR stage IN
                    ('queued','fetch','extract','refine','chunk','embedding','store','compile','done')),
    progress    INT NOT NULL DEFAULT 0             -- 0–100（API: progress）
                CHECK (progress BETWEEN 0 AND 100),

    retries     INT NOT NULL DEFAULT 0,
    error_msg   TEXT,
    queued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_jobs_status    ON jobs (status, queued_at);
CREATE INDEX idx_jobs_job_type  ON jobs (job_type);
CREATE INDEX idx_jobs_note_id   ON jobs (note_id);

-- 任务入队时通知 Worker（配合 pg LISTEN/NOTIFY 可替代 Redis）
CREATE OR REPLACE FUNCTION notify_job_queued()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_job', row_to_json(NEW)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER jobs_notify
    AFTER INSERT ON jobs
    FOR EACH ROW EXECUTE FUNCTION notify_job_queued();
