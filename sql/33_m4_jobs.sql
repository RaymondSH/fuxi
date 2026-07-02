-- M4：连接器同步、Agent 规划和提案执行任务。
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_job_type_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check CHECK (job_type IN (
    'ingest','compile','graph_extract','reindex','qa_gen','note_reindex',
    'source_refresh','governance_scan','connector_sync','agent_plan','proposal_execute'
));
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_stage_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_stage_check CHECK (stage IS NULL OR stage IN (
    'queued','fetch','extract','refine','chunk','embedding','store','compile',
    'scan','rerank','verify','sync','plan','execute','done'
));

