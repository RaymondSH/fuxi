-- M1 步骤3：jobs.job_type 放开 'qa_gen'（文档→Q&A 生成任务）。
--   原约束见 sql/06_jobs.sql：('ingest', 'compile', 'graph_extract', 'reindex')。
--   stage 复用 'refine'→'done'（已在原约束内），故不动 stage 约束。

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_job_type_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check
    CHECK (job_type IN ('ingest', 'compile', 'graph_extract', 'reindex', 'qa_gen'));
