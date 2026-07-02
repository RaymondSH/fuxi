# M3 · 治理、生命周期与深度问答设计

> 状态：已部署生产并通过端到端冒烟验收。接口以 [api-contract.md](api-contract.md) 为准，
> 数据库迁移为 `sql/25~28`。

## 1. 目标与边界

M3 解决四件事：知识可编辑/回滚/恢复；全库问题可发现和闭环；检索可重排且外发内容脱敏；
复杂问题可做有界的多步检索和引用校验。M3 不做企业连接器、通知和自治写入，这些仍属于 M4。

## 2. 内容生命周期

- `source_documents` 是来源身份，保存 locator、内容哈希、ETag、刷新周期和健康状态。
- `notes.source_document_id` 指向来源；存量笔记按 URL/文件/manual 回填来源。
- 每次编辑、刷新或恢复前，把当前笔记完整业务字段写入 `note_versions`。
- `PATCH /notes/{id}` 需 editor+；正文改变后创建 `note_reindex` job，重建 chunk、向量和 ES。
- `DELETE /notes/{id}` 改为软删除，需 space_admin；`POST /notes/{id}/restore` 恢复。
- 所有读取路径只看 `deleted_at IS NULL`。版本表保留，M3 不提供物理删除接口。
- URL 来源由维护任务按 `next_refresh_at` 重抓；内容哈希未变化只更新检查时间，变化则建版本并更新。

## 3. 治理巡检

`governance_runs` 记录一次空间扫描，`governance_issues` 是可闭环待办。问题类型：

| 类型 | 检测方式 |
|---|---|
| `stale` | `published_date/updated_at` 超过配置天数 |
| `duplicate` | 同空间向量余弦相似度达到阈值，按无序 note pair 去重 |
| `conflict` | 近似/共享标签候选对经 LLM 结构化判断 |
| `broken_link` | URL 来源刷新/探测失败 |
| `missing_tags` | 已完成且标签为空 |

fingerprint 在空间内唯一，同一问题重复扫描只更新证据和最后发现时间。状态为
`open/resolved/ignored`；editor+ 可处理，只有 space_admin 可触发全空间扫描。

## 4. 检索、重排与护栏

- ES/pgvector 召回和 RRF 不变，取前 20 条调用智谱 `/rerank`，失败时自动保留 RRF。
- 最终分数以相关性为主，并小幅叠加 `authority`；所有候选在调用重排前已通过空间 ACL。
- 发往外部模型的 query/context 统一经过 PII 掩码：大陆手机号、邮箱、身份证号、银行卡号。
- 无来源、低相关来源或引用校验失败时明确标记证据不足，不生成无依据确定性结论。

## 5. Agentic RAG

深度问答是有界流水线，不做无限自主循环：

1. LLM 把问题拆成最多 3 个检索子问题；
2. 每个子问题独立执行 ACL 混合召回与 rerank；
3. 按 note id 去重融合，最多保留 8 个来源；
4. 基于来源生成回答；
5. 校验回答中的引用编号，输出 `supported/warning` 结论。

`POST /qa/agentic/stream` 的 SSE 事件为 `plan → sources → token* → verification → done`。
每次运行把 plan、检索来源和校验结果写入 `qa_history.trace`，便于审计和后续评测。

## 6. 权限

viewer 可读内容和发起问答；editor 可编辑、恢复笔记和处理治理待办；space_admin 可软删除笔记、
触发空间巡检和管理刷新策略；sysadmin 对所有空间拥有最高权限。所有新查询继续以
`spaces.visible_space_ids` 或 token 绑定空间为唯一 ACL 输入。

## 7. 验收

- 编辑→版本→恢复闭环，软删除内容不出现在任何读取/MCP 路径。
- 刷新失败不覆盖当前内容；相同内容不产生新版本。
- 巡检幂等，跨空间不比较、不泄漏。
- rerank 不可用时检索可降级；PII 不进入 provider 请求。
- 深度问答最多 3 个子问题，引用只能指向本次 ACL 召回来源。
