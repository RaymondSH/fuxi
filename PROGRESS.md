# fuxi · 当前交付状态

> 当前状态的单一真相。每次代码变更都要同步状态，并在底部追加一条简短更新记录。
> 图例：✅ 完成　🚧 部分完成 / 待外部条件　⬜ 未开始

**最后更新：2026-07-04**

## 总览

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据库 | 🚧 | SQL 01~33 已部署；SQL 34 已纳入初始化入口，待生产迁移 |
| 后端基础设施 | ✅ | FastAPI、持久化 worker、结构化日志、全局异常处理 |
| 鉴权与权限 | ✅ | Cookie/Bearer 双端、refresh/撤销、配额、审计、空间 ACL |
| 入库 | ✅ | URL/PDF/Word/Excel/图片、分块、向量、原文件、ES 同步 |
| 检索 | ✅ | ES+ik、pgvector chunk 语义检索、RRF、rerank、ACL |
| 问答 | 🚧 | 后端 SSE 已验收；前端流状态 ID 修复已完成，本地检查通过，待重新部署确认 |
| 笔记与 Wiki | ✅ | 列表、详情、编辑、版本、软删除、恢复、编译 |
| 图谱与标签 | ✅ | 空间过滤图谱、标签词表和归并 |
| 治理与深度问答 | ✅ | 五类巡检、Agentic RAG、PII 掩码、引用校验 |
| MCP | ✅ | 八个只读工具，token 强制绑定空间 |
| M4 协作能力 | ✅ | 订阅、通知、问答反馈、审批式治理 Agent |
| M4 企业连接器 | 🚧 | 四类连接器框架已部署；真实平台凭据和实连验收待外部条件 |
| Web 前端 | 🚧 | 24 个路由已构建上线；空间登录同步、治理页空状态和侧栏分类折叠已完成，问答流显示问题待最终生产验收 |
| 移动端 | 🚧 | 脚手架和鉴权完成，不属于当前 Web 交付范围 |
| 生产部署 | ✅ | backend/frontend/worker、ES、备份与维护 timer 正常运行 |

## 已交付范围

- M0：安全、备份、审计、账号安全和双 token。
- M1：笔记列表、Q&A 沉淀、标签治理、用量后台、MCP。
- M2：空间、成员与全链路 ACL。
- M3：内容生命周期、治理巡检、rerank/护栏和深度问答。
- M4：连接器框架、分发协作、反馈和审批式治理 Agent。
- 最终文档：`README.md`、`docs/architecture.md`、`docs/api-contract.md`、
  `docs/operations.md`。
- 唯一 Python 运维入口：`scripts/fuxi.py`。

## 剩余事项

1. 生产执行 `sql/34_undelete_version.sql` 后再部署本轮后端与前端修复。
2. 部署并验收问答页按消息唯一 ID 与最终脱敏答案更新流状态。
3. 配置四个平台真实凭据，分别完成连接器全量、增量、删除/失权和限流验收。
4. 可选增强：搜索联想接口、typed relation 提取、异地备份。

## 验收基线

- 后端：Python 编译和完整 pytest 通过。
- 前端：TypeScript 检查和生产构建通过。
- 生产：`scripts/fuxi.py verify-core` 与 `verify-advanced` 通过。
- 数据：schema 真相为 SQL 01~34；生产当前 01~33，部署本轮代码前须执行 SQL 34。

## 更新记录

- **2026-07-04** — 修复二轮核查剩余问题：Wiki/MCP 空间 SQL 别名、锁号事务提交、
  SQL 34 初始化入口、标题 ES 同步、搜索 total 语义、治理 LLM 调用上限、SSE 最终
  脱敏展示、stale 治理动作、MCP 无来源生成与 token 前缀筛选、Agent 审批竞态、
  连接器 PATCH 校验和 Google Drive 全量分页、统一错误体；新增开发测试依赖与回归测试。
- **2026-07-04** — 第二轮修正：plan 容错 / 删笔记清理 / QA 回灌过滤 / content 判同（4 项）
- **2026-07-04** — M0~M4 全面核查与缺陷修复（28 项）：
  - **严重**：修复非 sysadmin 用户访问 `/api/wiki` 列表/详情 500（space_filter alias 错配 wiki_pages）；修复登录锁号在密码验证前抛 423 泄露账号存在；补注不存在账号不触发锁号的设计权衡。
  - **M1**：merge_tag 改为 PG 事务提交后再同步 ES（修复非原子）；搜索 total 改用真实 COUNT 不被 LIMIT 100 截断；UserOut.daily_token_limit 返回有效额度（member 未设用默认值）；MCP search 支持 q 空+tags 标签模式；wiki 列表/详情仅当全部来源软删才隐藏（原任一软删即隐藏）。
  - **M2**：assert_space_role/assert_note_role 无权改抛 404（不再泄露资源是否存在）。
  - **M3**：PATCH /notes 仅 content/tags 变化才重建索引；refresh_source 拆 try 块（LLM 失败不误标 broken）+ LLM 调用移出 DB 连接块；治理 conflict 检测加 LLM 调用上限（20 对）+ 失败记 warning；agentic 检索凑满 8 条后外层 break 省重排；治理 issues/runs 列表加分页；governance run 状态映射 queued/running→pending/processing；governance_scan job 推进 jobs.stage=scan/done；软删除恢复留 undelete 版本（新增 sql/34_undelete_version.sql）；流式问答 done 事件带 masked_answer（对最终答案做 PII 掩码）。
  - **M4**：agent planner 曾补 update_summary 生成路径（后续核查已改为 URL 来源重抓、manual 留待连接器/人工）+ 跳过连接器笔记的 broken_link；archive_duplicate 执行器校验 other_note_id 同空间未删除；连接器单条空文档不中断整轮同步（改为跳过+标 error）；Google Drive 首次同步过滤 trashed 文件；四类连接器 provider 加 429/5xx 指数退避重试；修复 provider HTML 清洗正则 `\\d`→`\d`（标题闭合标签丢失）。
  - **文档**：api-contract.md 同步更新 DELETE 角色、quota operation 枚举、治理分页与状态映射、流式 masked_answer、版本 change_type、Agent 五类提案说明。
- **2026-07-03** — 将侧栏导航整理为知识工作、协作与治理、内容管理、系统管理
  四组可折叠目录，当前页面所在分组自动展开。
- **2026-07-03** — 修复登录后空间列表不重载导致知识治理、企业连接和治理 Agent
  空白；补齐三页的加载、错误与空数据状态。
- **2026-07-03** — 清理阶段过程文档；合并为最终架构、接口和运维文档；八个零散
  Python 脚本收敛为 `scripts/fuxi.py` 六个子命令；同步 README、服务入口和引用。
