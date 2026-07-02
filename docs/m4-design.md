# M4 · 企业接入、分发与审批 Agent 设计

> 状态：核心系统已部署并通过生产冒烟；真实平台凭据配置与连接验收待外部凭据。接口以
> [api-contract.md](api-contract.md) 为准，迁移为 `sql/29~33`。

## 1. 边界

M4 提供 Confluence Cloud、飞书云文档、Google Drive、SharePoint 四类只读连接器；连接器只把
远端内容同步进 fuxi，不向远端反写。通知首期为站内通知。自治 Agent 只产出白名单提案，
space_admin 审批后才由确定性执行器写入，不允许模型直接写库。

## 2. 连接器

所有 provider 实现统一接口：

- `list_changes(cursor) -> (items, next_cursor)`：全量首次同步和后续增量共用；
- `fetch_content(item) -> RemoteDocument`：返回 external_id/title/content/url/version/modified_at；
- 远端删除或失权只把 `connector_items.status` 标成 `missing` 并生成治理/通知，不物理删除笔记。

增量策略：Confluence REST v2 cursor；飞书文件夹递归并比较 revision/modified_time；Google
Drive changes page token；SharePoint driveItem deltaLink。当前部署没有 HTTPS，因此不使用入站
webhook。连接器凭据用 Fernet 加密入库，主密钥只从 `CONNECTOR_SECRET_KEY` 环境变量读取。

## 3. 同步与分发

`connector_sync` job 按连接器串行同步。每个远端对象由 `(connector_id, external_id)` 幂等定位；
版本没变不触发入库，版本变化先写 `note_versions`，再更新笔记并创建 `note_reindex` job。
每次新增、更新、删除/失权产生 `change_events`。订阅支持 `space/tag/note` 三种范围，匹配且仍有
空间权限的用户获得一条 `notifications`。

## 4. 回答反馈

`qa_feedback` 对 `(qa_history_id, user_id)` 唯一，支持 `up/down` 和可选原因。用户只能评价自己的
问答记录；sysadmin 可查看全局低评价列表。数据供 M5 评测体系使用。

## 5. 治理 Agent

`agent_run` 扫描开放治理问题并让 LLM提出白名单动作：

- `add_tags`
- `update_summary`
- `refresh_source`
- `archive_duplicate`
- `resolve_issue`

提案初始为 `pending`。space_admin 可 approve/reject；approve 只创建 `proposal_execute` job。
执行器重新校验动作和目标空间，保存版本、调用既有 lifecycle/service，再写审计与通知。

## 6. 权限与验收

连接器 CRUD/同步、订阅和提案审批均按空间角色：viewer 可订阅和读通知，editor 可提交反馈，
space_admin 管连接器和审批。验收要求 provider mock 覆盖全量/增量/删除/限流，远端版本幂等，
跨空间零泄漏，未审批提案零写入。
