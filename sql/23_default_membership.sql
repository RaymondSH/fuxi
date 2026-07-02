-- M2 步骤1：把现有全部用户加为 default 空间的 editor。
--   保证迁移后所有人仍能看到全部历史笔记（向后兼容）。
--   新建空间后，空间管理员再按需加成员。
--
--   依赖：18_spaces.sql（default 空间 + space_members 表）+ 08_auth.sql（users 表）。
--   幂等：ON CONFLICT (space_id, user_id) DO NOTHING（重跑不重复加）。

INSERT INTO space_members (space_id, user_id, role)
SELECT s.id, u.id, 'editor'
FROM spaces s
CROSS JOIN users u
WHERE s.is_default
ON CONFLICT (space_id, user_id) DO NOTHING;
