-- 账号安全：给 users 加失败登录计数 + 锁定 + 最近登录 + 密码修改时间。
--
-- 配合 services/auth.py 的登录失败锁定逻辑与自助改密端点。
-- 幂等：所有 ADD COLUMN IF NOT EXISTS，重跑安全。
-- 已有数据的新列用默认值（0 / NULL），不影响存量用户。

ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;          -- NULL=未锁；锁定期内禁止登录
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;           -- 最近一次登录成功时间
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;    -- 最近一次改密时间（改密后刷新）

-- 存量用户给个 password_changed_at 兜底（=创建时间），避免「从未改密」歧义
UPDATE users SET password_changed_at = created_at WHERE password_changed_at IS NULL;
