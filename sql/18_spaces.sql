-- M2 步骤1：空间（Spaces）—— 多团队内容隔离的基础设施。
--   spaces        空间主表。default 空间用 is_default 标记，承载 M2 迁移前的历史笔记。
--   space_members 空间成员 + 空间内角色（viewer/editor/space_admin）。
--                 与 users.role（系统级 member/admin）正交：一个用户在 A 空间是 editor、
--                 在 B 空间是 viewer。admin 视为 sysadmin，对全部空间天然有 space_admin 权限，
--                 不写 membership 行（避免冗余），逻辑在 services/spaces.py 里实现。
--   角色含义：
--     viewer       只读空间内容（检索/问答/浏览笔记/图谱/wiki）
--     editor       可入库/编辑笔记/生成 Q&A
--     space_admin  管空间成员（加/改角色/移除）+ 编译 wiki + 删笔记
--
--   依赖：08_auth.sql 的 users 表（owner_id / space_members.user_id 都引用它）。
--   注意 spaces 必须在 20_notes_space / 21_wiki_space / 22_mcp_token_space 之前执行。

CREATE TABLE IF NOT EXISTS spaces (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug        TEXT NOT NULL UNIQUE,                 -- URL 友好标识，如 'default' / 'team-eng'
    name        TEXT NOT NULL,                        -- 展示名
    description TEXT,
    owner_id    UUID REFERENCES users(id) ON DELETE SET NULL,  -- 创建者；删用户不级联
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,       -- default 空间承载迁移前数据
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS space_members (
    space_id    UUID NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'space_admin')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (space_id, user_id)
);

-- 按「某用户在哪些空间」查（每次请求解析 ACL 时走这条）
CREATE INDEX IF NOT EXISTS idx_space_members_user ON space_members (user_id);

-- 种子：default 空间。迁移脚本把现有 notes/wiki 归入此空间，并把全部现有用户加为 editor。
INSERT INTO spaces (slug, name, is_default)
VALUES ('default', '默认空间', TRUE)
ON CONFLICT (slug) DO NOTHING;
