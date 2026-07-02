# fuxi 空间（Spaces）+ 权限感知 —— 设计文档

> 状态：M2「权限与多空间」（Spaces + ACL + 细化角色）已部署并通过真库隔离验收。本文件是空间
> 相关改动的单一设计真相，接口细节同步进 [api-contract.md](api-contract.md)，进度同步进
> [../PROGRESS.md](../PROGRESS.md)，系统角色模型见 [auth-design.md](auth-design.md)。

## 背景

M1 之前 fuxi 是「共享语料」：notes / entities / graph / wiki 全局无 owner，所有登录用户
跨全库检索 / 问答。这套模型在单团队够用，但无法支撑多团队内容隔离 —— 一个团队入库的私有
资料会被另一团队搜到。M2 引入「空间（Space）」作为内容隔离边界：每篇笔记、每个 wiki 主题
页、每个 MCP token 都归属于一个空间，读写操作按空间 ACL 过滤。

设计取舍：**不把 notes 加 owner 改成多租户**（那要给 notes 加 owner、全链路按 user 过滤，
逆现有「全局共享语料」架构）。改用「空间隔离 + 空间内角色」：空间是内容边界，空间内再分
viewer/editor/space_admin 三档角色。这样既隔离了不同团队的内容，又保留了空间内「共享语料」
的检索体验（空间内所有人跨全库检索，不按 user 过滤）。

## 双层角色模型

fuxi 是双层角色，**系统级**与**空间级**正交：

| 层 | 表 | 角色 | 含义 |
|----|----|------|------|
| 系统级 | `users.role` | `member` / `admin` | admin = sysadmin，管用户 / MCP token / 全局看板；member 只能被加进空间 |
| 空间级 | `space_members.role` | `viewer` / `editor` / `space_admin` | 一用户在不同空间可有不同角色 |

**sysadmin 对全部空间天然有 `space_admin` 权限**（不写 `space_members` 行，避免冗余），逻辑在
`services/spaces.py` 里实现（`is_admin` 直接放行）。普通用户必须通过 `space_members` 加入某空间
才能看到该空间内容。

### 空间内角色权限

| 空间角色 | 可做 |
|----------|------|
| `viewer` | 检索 / 问答 / 浏览笔记 / 图谱 / wiki（只读空间内容） |
| `editor` | viewer 全部 + 入库 / 编辑笔记 / 生成 Q&A |
| `space_admin` | editor 全部 + 管空间成员（加 / 改角色 / 移除）+ 编译 wiki + 删笔记 |

> **写操作的角色校验落在空间维度**：M1 之前 `DELETE /notes/{id}`、`POST /wiki/compile` 走
> 全局 `require_admin`（只有 sysadmin 能做）。M2 后改成 `spaces.assert_note_role(user, note_id, "space_admin")`
> —— 任何空间管理员都能删本空间笔记、编译本空间 wiki，不必是 sysadmin。`/ingest/*` 同理
> 从「sysadmin only」放宽到「该空间 editor 以上」。

## 数据库（sql/18, 20 ~ 23）

| 脚本 | 内容 |
|------|------|
| `18_spaces.sql` | `spaces`（slug / name / description / owner_id / is_default）+ `space_members`（space_id + user_id + role，PK 双列）+ default 空间种子 |
| `20_notes_space.sql` | `notes` 加 `space_id` + `created_by`（FK users）+ 回填 default；最终约束由 `24_space_hardening.sql` 收紧 |
| `21_wiki_space.sql` | `wiki_pages` 加 `space_id` + 回填 default |
| `22_mcp_token_space.sql` | `mcp_tokens` 加 `space_id` + 回填 default |
| `23_default_membership.sql` | 把现有全部用户加为 default 空间 `editor`（保证迁移后仍能看到全部历史笔记） |

> 编号说明：M2 的 spaces 相关迁移从 18 起编，但 19 已被 M1 的 `19_mcp_tokens.sql` 占用，
> 故 notes/wiki/mcp_token/membership 顺延为 20/21/22/23，避免编号冲突。`00_init.sql` 按
> 18→19→20→21→22→23 顺序执行（19_mcp_tokens 与 20_notes_space 无表依赖冲突，先后无影响）。

`spaces` 表：

```sql
CREATE TABLE spaces (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug        TEXT NOT NULL UNIQUE,        -- URL 友好，如 'default' / 'team-eng'
    name        TEXT NOT NULL,
    description TEXT,
    owner_id    UUID REFERENCES users(id) ON DELETE SET NULL,  -- 创建者；删用户不级联
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

`space_members` 表：

```sql
CREATE TABLE space_members (
    space_id    UUID NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'space_admin')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (space_id, user_id)
);
```

- `notes.space_id` / `wiki_pages.space_id` 为 `NOT NULL + ON DELETE RESTRICT`：有内容时拒绝删除空间，
  不产生无归属内容。`mcp_tokens.space_id` 为 `NOT NULL + ON DELETE CASCADE`：空间删除后 token 立即失效。
  `space_members` 用 `CASCADE` 清理成员关系。
- 迁移策略：**全归入 default 空间**。18 建表 + default 种子 → 19/20/21 回填 space_id 到
  default → 22 把全部现有用户加为 default editor。迁移后所有人仍能看到全部历史笔记
  （向后兼容），新建空间后管理员再按需加成员。

## ACL 注入模式（核心）

权限感知检索的关键：把「用户可见空间集合」注入到每条查 notes 的 SQL（和 ES query）。本系统
提供两个收敛点，所有读路径都走它们：

```python
# services/spaces.py

def visible_space_ids(conn, user) -> list[UUID] | None:
    """sysadmin 返回 None（=全可见，SQL 不加过滤）；普通用户返回其 space_members 列表。"""

def space_filter_from(space_ids, alias="notes") -> tuple[str, list]:
    """把已查好的 space_ids 生成 SQL 片段。
    space_ids=None（仅 sysadmin 全可见）→ ("", [])。
    space_ids=[]（普通用户但无空间）→ 匹配不上任何笔记。
    space_ids=[...] → f" AND {alias}.space_id = ANY(%s::uuid[])"。
    """
```

**调用约定**：每个请求开头先 `sids = spaces.visible_space_ids(conn, user)` 拿到集合（一次查库），
再把 `sids` 透传进所有下游查询，每路查询调 `space_filter_from(sids, alias)` 生成片段。这样
`space_members` 每次请求只查一次，不在每路查询里重复查。

**为什么 `space_filter_from` 不收 `user` 参数**：admin 决策（None=全可见）已经编码进
`space_ids`，函数只看 `space_ids` 即可。解耦后 MCP 也能复用 —— MCP token 没有 `CurrentUser`
对象，但它有自己的 `space_ids`（来自 token 绑定的空间），直接传进 `space_filter_from`
就能和 HTTP 路径共用同一套过滤逻辑。

## 各模块 ACL 改动

### 写路径（步骤 3）

- **ingest**：`POST /ingest/url`、`POST /ingest/file` 注入 `CurrentUser`，校验目标空间的
  editor 角色（`assert_space_role`），把 `space_id` + `actor_id` 透传进 `ingest_worker.run`；
  worker `_save` 写 `notes.space_id` / `notes.created_by`。
- **notes 写操作**：`DELETE /notes/{id}` 从全局 `require_admin` 改成 `assert_note_role(user, note_id, "space_admin")`
  （空间管理员即可删本空间笔记）；`POST /notes/{id}/generate-qa` 同理改成 editor 校验。
- **wiki compile**：`POST /wiki/compile` 校验所有来源笔记同空间 + 调用者是该空间 space_admin；
  `compile_worker` 取 wiki 行的 space_id，只取同空间笔记（`AND space_id = %s`，防御性双重校验）。

### 读路径（步骤 4）

所有读接口先解析 `sids = visible_space_ids(conn, user)`，再透传进查询：

- **search**（`routers/search.py`）：`_semantic_search` / `_keyword_search` 都加 space 过滤。
  ES 侧用 `visible_space_strs`（字符串形式）作 terms filter；PG 侧用 `space_filter_from`。
- **qa**（`routers/qa.py`）：`_retrieve(question, space_ids)` 收 `space_ids`（不是 `user`，
  便于 MCP 复用），透传给 `_semantic_search` / `_retrieve_generated_qa` / `_token_search`。
  generated_qa 没 space_id 列，但 JOIN notes 拿其 space_id 过滤。
- **notes 详情**（`routers/notes.py`）：`GET /notes/{id}` 取笔记后校验 `role_in_space`，
  无权返回 404（不泄露存在性）；`GET /notes` 列表加 space 过滤。

### 图谱权限感知（步骤 5）

`routers/graph.py` 全量重写。原实现查 `entity_note_counts` / `entity_cooccurrence` 两个
全局视图 —— **视图是预先聚合的，无法接受运行时 space 参数**，故改用应用层 JOIN + 过滤：

```sql
-- 替代 entity_note_counts：实时按 space 过滤的实体提及数
SELECT ne.entity_id, COUNT(*) 
FROM note_entities ne JOIN notes n ON n.id = ne.note_id
WHERE 1=1 {space_filter}   -- space_filter_from(sids, alias="n")
GROUP BY ne.entity_id

-- 替代 entity_cooccurrence：实时按 space 过滤的共现边
SELECT a.entity_id, b.entity_id, COUNT(*)
FROM note_entities a JOIN note_entities b ON a.note_id = b.note_id AND a.entity_id < b.entity_id
JOIN notes n ON n.id = a.note_id
WHERE 1=1 {space_filter}
GROUP BY a.entity_id, b.entity_id
```

旧视图保留在 SQL 里（向后兼容），但新代码全部走内联 JOIN。子查询里用 `space_filter_from(sids, alias="n")`，
关联笔记查询用 `alias="notes"` —— 同一 `sids` 可在不同 alias 上复用。

### Wiki 权限感知（步骤 6）

`routers/wiki.py` 把全局 `require_admin` 换成空间作用域校验：

- `compile_status` / `list_wiki` / `get_wiki` 加 space 过滤（`space_filter_from(sids)`），无权返回 404。
- `_resolve_compile_space()`：编译前校验所有来源笔记同属一个空间，且调用者是该空间 space_admin。
- `CompileRequest` / `WikiSummary` / `WikiDetail` 模型加 `space_id` 字段。

### MCP 绑空间（步骤 7）

MCP token 从「全库只读」改成「绑定单空间」：

- `mcp_tokens` 加 `space_id`（`22_mcp_token_space.sql`）。`verify_token` 现在返回
  `(token_id, space_id)`（原来是 bool）。
- `mcp_admin.py`：`McpTokenOut` 带 `space_id` / `space_name`；`CreateTokenRequest` / `UpdateTokenRequest`
  带 `space_id`；`list_tokens` JOIN spaces；新建 token 未指定 space 默认绑 default。
- `mcp_server.py` 全量重写：加 `_mcp_space_ids` ContextVar，`_auth_wrapper` 从 `verify_token`
  结果设它；`_space_filter()` helper 读 ContextVar 返回 `(fragment, params)`；8 个工具全部按
  token 绑定空间过滤。
  - **`ask` 工具**复用 `qa_mod._retrieve(question, _space_ids())` —— 因为 `_retrieve` 已改成收
    `space_ids`（不收 `user`），MCP 无需构造 `CurrentUser` 就能调用。
  - **图谱工具**用和 `graph.py` 相同的内联 JOIN（替代视图）。
- **token 必须绑定空间**：历史空值由迁移回填 default 并设为 `NOT NULL`，不存在全库 token。
- 用 ContextVar（匹配 `usage.py` 模式）而非 FastMCP 的 Context 对象，因为现有工具用模块级
  `pool` 调用、无 Context 注入；ASGI 中间件设 ContextVar，工具内 `_space_filter()` 读，改动最小。

## 空间管理 API（步骤 8）

`routers/spaces.py`（新）挂在 `/api` 下，统一登录依赖。提供空间 CRUD + 成员管理：

| 接口 | 权限 | 说明 |
|------|------|------|
| `GET /spaces` | 登录 | 列出可见空间（普通用户=成员空间；sysadmin=全部）+ 当前用户在各空间的角色 |
| `POST /spaces` | 登录 | 建空间（任意登录用户可建，自己成为 space_admin） |
| `GET /spaces/{id}` | viewer+ | 空间详情 |
| `PATCH /spaces/{id}` | space_admin | 改 name / description |
| `DELETE /spaces/{id}` | space_admin | 删空间（default 不可删，`400`） |
| `GET /spaces/{id}/members` | viewer+ | 成员列表 |
| `POST /spaces/{id}/members` | space_admin | 加成员（按 user_id + role） |
| `PATCH /spaces/{id}/members/{user_id}` | space_admin | 改成员角色 |
| `DELETE /spaces/{id}/members/{user_id}` | space_admin | 移除成员（不能移除自己，`400`） |
| `GET /spaces/{id}/members/search` | space_admin | 按 email 搜用户（加成员用；`/auth/users` 是 sysadmin only，空间管理员未必是 sysadmin） |

所有写操作写审计日志（`audit_log`：`space_create` / `space_update` / `space_delete` /
`member_add` / `member_update` / `member_remove`）。空间管理员不能改/移除自己（防自锁）。

> **为什么 `/spaces` 不放 `/admin` 下**：空间管理是 per-user 的（任何用户可建空间、管自己
> 空间的成员），不需要 sysadmin 权限。放 `/spaces` 避开 sysadmin-only 的 `/admin/layout.tsx`
> 守卫。

## 前端（步骤 9）

- **`SpacesProvider.tsx`**（新）：Context provider，拉 `/spaces`，把 active space 存 localStorage
  （`fuxi_active_space`，`__all__` = 不指定具体空间）。`useSpaces()` 暴露 spaces / activeId /
  setActiveId / reload。导出 `canAct(role, min)` 和 `activeSpaceForIngest(activeId)`。
- **`SpaceSwitcher.tsx`**（新）：TopBar 里的下拉，仅当可见空间 >1 时显示，链接到 `/spaces`。
- **`/spaces` 页**（新）：空间列表 + 角色徽标；建空间表单；可展开成员面板（角色选择 / 移除）；
  AddMember 组件带防抖 email 搜索（调 `/spaces/{id}/members/search`）。
- **入库页**：`submitUrl` / `submitFile` 传 `space_id`（body / query param），默认用 active space。
- **MCP 管理页**：创建 token 表单加空间选择；token 列表项内联空间下拉（变更即调 `PATCH`）。
- **Sidebar**：加 `{ href: "/spaces", label: "空间" }` 导航项。

> **前端 active space 仅用于入库目标选择**。读 API 的可见性由服务端按用户推导（不收客户端
> 传的 space_id），所以切 active space 不会收窄检索结果 —— 这是有意的，避免「我以为切了空间
> 却还能搜到别的空间」的认知错位。

## 迁移与部署

1. 按 `00_init.sql` 顺序执行（18→19→20→21→22，已挂进 00_init）。
2. 迁移后：全部历史笔记 / wiki / MCP token 归入 default 空间，归属列改为非空；全部现有用户是 default editor。
3. 真库验证要点：建空间 → 加成员 → 不同角色看到的笔记集合不同 → MCP token 绑空间后只返该空间内容。

## 决策记录

- **隔离粒度选空间而非 owner**：保留「空间内共享语料」的检索体验，避免给 notes 加 owner 后
  全链路按 user 过滤（逆现有架构）。空间是内容边界，空间内跨全库检索。
- **双层角色正交**：系统级（sysadmin/member）管用户与全局；空间级（viewer/editor/space_admin）
  管内容。sysadmin 天然是所有空间的 space_admin（不写 membership 行）。
- **回填全归 default**：迁移零摩擦，迁移后所有人仍可见全部历史。新建空间后管理员按需收窄。
- **图谱丢视图改 JOIN**：预聚合视图无法接受运行时 space 参数，改应用层 JOIN + space 过滤。
  旧视图留作向后兼容，新代码不用。
- **MCP 用 ContextVar 而非 FastMCP Context**：现有工具用模块级 pool 调用无 Context 注入，
  ASGI 中间件设 ContextVar、工具内读，改动最小且与 `usage.py` 模式一致。
- **`space_filter_from` 去掉 user 参数**：admin 决策已编码进 space_ids（None=全可见），解耦后
  MCP 可复用（无需构造 CurrentUser）。
- **前端 active space 不收窄读结果**：读可见性由服务端推导，避免切空间后认知错位；active space
  仅用于入库目标。
