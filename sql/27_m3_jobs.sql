-- M3：持久化任务扩展。

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_job_type_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check
    CHECK (job_type IN (
        'ingest','compile','graph_extract','reindex','qa_gen',
        'note_reindex','source_refresh','governance_scan'
    ));

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_stage_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_stage_check
    CHECK (stage IS NULL OR stage IN (
        'queued','fetch','extract','refine','chunk','embedding','store','compile',
        'scan','rerank','verify','done'
    ));

