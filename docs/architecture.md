# fuxi · 最终架构

本文档描述 v0.8.0 的最终系统边界与关键设计。接口字段和路径以
[api-contract.md](api-contract.md) 为准，部署与运维见 [operations.md](operations.md)。

## 1. 系统组成

```text
Next.js Web / MCP Client
          │
          ▼
FastAPI API + MCP Server
          │
          ├── PostgreSQL 18 + pgvector：业务数据、向量、任务、审计
          ├── Elasticsearch 8 + ik：中文关键词检索
          ├── Local / R2：原始文件
          └── 智谱 GLM：提炼、问答、重排、编译、视觉理解
```

- 前端使用 Next.js App Router、TypeScript 和 Tailwind，所有数据来自后端。
- 后端路由只处理请求和响应，业务逻辑放在 `services/`，慢任务由持久化 `jobs` 队列和
  独立 worker 执行。
- PostgreSQL 是业务数据与向量数据的单一真相；Elasticsearch 不可用时关键词检索自动回退
  PostgreSQL ILIKE。
- LLM 和 Embedding 统一经 `services/providers/` 策略层调用。

## 2. 身份、权限与配额

Web 使用 httpOnly Cookie 保存 access/refresh token；移动客户端使用 Bearer access token。
access token 有效期 15 分钟，refresh token 有效期 7 天。登出、改密和账号停用会撤销现有会话。

权限分为两层：

| 层级 | 角色 | 范围 |
|------|------|------|
| 系统 | `member` / `admin` | 用户、全局配置和管理后台 |
| 空间 | `viewer` / `editor` / `space_admin` | 空间内容读取、编辑和管理 |

系统管理员天然拥有全部空间的 `space_admin` 权限。普通用户只能访问其成员空间；无权访问的资源
统一返回 404，避免泄露资源是否存在。检索、问答、图谱、Wiki、标签和 MCP 均使用同一套空间
ACL。每日 token 配额在模型调用前检查，超额返回 429。

## 3. 内容与检索

入库支持 URL、PDF、Word、Excel 和图片。处理流程为：

```text
抓取/解析 → GLM 提炼 → 中文友好分块 → Embedding → PostgreSQL → Elasticsearch
```

笔记按空间归属，原始文件写入 LocalStore 或 R2。内容更新前写入 `note_versions`；删除采用软删除，
恢复或正文更新后通过 `note_reindex` 任务重建分块、向量和 ES 索引。

检索由三路组成：

- 关键词：Elasticsearch + ik，失败时回退 PostgreSQL ILIKE；
- 语义：pgvector chunk 级召回；
- 混合：RRF 融合后可调用智谱 rerank，并叠加少量 authority 权重。

所有候选在发送给外部模型前已完成空间过滤；问题和上下文中的手机号、邮箱、身份证号和银行卡号
会被掩码。

## 4. 问答、Wiki 与治理

普通问答支持同步和 SSE 流式输出，事件顺序为 `sources → token* → done`。深度问答采用最多三路
的有界流程：

1. 拆解最多三个检索子问题；
2. 每路执行 ACL 混合检索与 rerank；
3. 去重后保留最多八个来源；
4. 基于来源生成回答；
5. 校验引用并返回 `supported` 或 `warning`。

Wiki 将同空间多篇笔记编译成结构化主题页，并保留引用和冲突观点。治理巡检覆盖过期、近重、
冲突、坏链和缺标签，问题以幂等 fingerprint 落入待办，可被处理、忽略或交给治理 Agent
生成白名单提案。

## 5. MCP、连接器与协作

MCP Server 暴露八个只读工具：`search`、`ask`、`get_note`、`list_notes`、`get_graph`、
`get_entity`、`list_wiki`、`get_wiki`。MCP token 与登录 JWT 分离，每个 token 必须绑定一个
空间，数据库只保存 bcrypt 哈希和显示前缀。

M4 连接器支持 Confluence、飞书、Google Drive 和 SharePoint 的只读增量同步。远端凭据使用
Fernet 加密，主密钥仅来自环境变量；远端删除或失权只标记 `missing`，不物理删除笔记。
当前真实平台凭据尚未配置，因此连接器框架已验收、平台实连仍待凭据。

订阅支持空间、标签和笔记三种范围，变更产生站内通知。问答可提交赞踩反馈。治理 Agent 只能
生成 `add_tags`、`update_summary`、`refresh_source`、`archive_duplicate`、`resolve_issue`
五类提案；未经 `space_admin` 审批不会写入，审批后仍由确定性执行器再次校验并执行。

## 6. 数据与代码边界

- SQL 01~34 是数据库 schema 的唯一真相。
- [api-contract.md](api-contract.md) 是前后端接口的唯一真相。
- `PROGRESS.md` 只记录当前交付状态，不保存阶段实施流水账。
- `scripts/fuxi.py` 是管理员、维护、索引、演示数据和生产验收的唯一 Python 运维入口。
- `.env`、密钥、token 和连接器凭据不得进入代码、日志或版本库。
