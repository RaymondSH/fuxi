-- 审计日志表：记录关键安全/写操作事件（登录/登出/改密/建号/停用/入库/删除等）。
--
-- 设计：
-- - 与 token_usage（账本）区分：token_usage 记 LLM 用量计费，audit_log 记「谁在何时对什么做了什么」。
-- - user_id 可空（如登录失败时还不知道是谁、或匿名访问触发的事件）。
-- - detail 用 JSONB 存事件细节（如 target 用户 id、失败原因等），便于扩展不破坏 schema。
-- - 同时写结构化日志（services/audit.py），DB 表供查询/看板，日志供 journald 归档。
-- - 写审计失败绝不阻塞业务：services/audit.py 内部 try/except，失败只 log.error。
--
-- 幂等：CREATE TABLE IF NOT EXISTS。重跑安全。
-- user_id 不设 FK：审计记录需在用户被删除后仍保留（合规追溯），故不级联。

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    -- 触发者；登录失败/匿名事件可为 NULL（不设 FK，避免用户硬删时审计记录被级联丢失）
    user_id     UUID,
    action      TEXT NOT NULL,            -- login_success / login_failed / logout / refresh /
                                          -- change_password / user_create / user_update / user_deactivate /
                                          -- ingest / note_delete / wiki_compile ...
    target_type TEXT,                     -- 操作对象类型：user / note / wiki / job
    target_id   TEXT,                     -- 操作对象 id（字符串，兼容各种 id 类型）
    detail      JSONB NOT NULL DEFAULT '{}',  -- 事件细节，自由扩展
    ip          TEXT,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 常用查询：某用户的操作历史 / 某类事件的时间线
CREATE INDEX IF NOT EXISTS idx_audit_user_time ON audit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_log (action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log (created_at DESC);
