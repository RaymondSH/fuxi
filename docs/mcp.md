# fuxi MCP Server —— 设计与接入

> 状态：M1 步骤 6（K-A）已完成。把知识库的检索 / 问答 / 笔记 / 图谱 / 主题页暴露为
> LLM Agent 可调用的只读工具，外部客户端（Claude Desktop / 自建 Agent）用 Bearer API
> token 访问 `/mcp` 端点。接口细节同步进 [api-contract.md](api-contract.md)，
> 鉴权设计同步进 [auth-design.md](auth-design.md)。

## 为什么需要 MCP

fuxi 的核心能力是「检索 → 问答 → 知识沉淀」。在 Web 端之外，越来越多场景由 LLM Agent
驱动：让 Agent 自己决定何时检索、检索什么、要不要追问。MCP（Model Context Protocol）
把这些能力标准化为「工具」，Agent 无需知道 fuxi 的 HTTP 细节，只要在配置里填一个端点 +
一个 token，就能像调用本地函数一样调 fuxi。

MCP server 与 fuxi 主 API 共用一个 FastAPI 进程：`/mcp` 挂的是
`mcp.streamable_http_app()`，外层包一层 Bearer 鉴权；token 管理走 `/api/mcp-admin/tokens`
（仅管理员）。`mcp` 包未安装时 `is_available()` 返回 False，`/mcp` 不挂载，其余接口不受影响。

## 工具一览

全部工具**只读**，无副作用，适合 Agent 自由调用：

| 工具 | 入参 | 说明 |
|------|------|------|
| `search` | `q`, `mode?="hybrid"`, `tags?`, `limit?=10` | 关键词 / 语义检索笔记，返回 `[{id,title,type,summary,score}]` |
| `ask` | `question` | RAG 问答，返回 `{answer, sources, generated}`；缺 API_KEY 时 `generated=false` 仅返回来源 |
| `get_note` | `note_id`(UUID) | 单篇笔记详情：标题/摘要/要点/标签/实体/正文 |
| `list_notes` | `q?`, `type?`, `tag?`, `page?=1`, `size?=20` | 笔记列表分页 |
| `get_graph` | `filter?="all"` | 知识图谱节点 + 共现边，`filter` 可 `concept/product/company` |
| `get_entity` | `entity_id`(UUID) | 实体详情 + 相关笔记 |
| `list_wiki` | — | 主题页列表 |
| `get_wiki` | `slug` | 主题页详情：结构化 sections + 引用来源 + 观点矛盾 |

`type` 字段统一映射为 Agent 友好的语义值：`link / pdf / word / excel / image`。

## 鉴权

MCP token 与登录用 JWT 分开：登录 JWT 走 `Authorization: Bearer <jwt>` 打 `/api/*`，
15 分钟过期、refresh 换发；MCP token 是长期 API key，仅用于 `/mcp`，由管理员手动颁发与撤销。

- 库里只存 bcrypt 哈希 + 前 8 位明文前缀（`prefix`，用于后台识别是哪个 token）
- 明文**仅在创建时返回一次**，前端弹窗提示复制保存
- 校验时线性扫所有 active token 做 `bcrypt.checkpw`（token 数量小，可接受）
- 命中即更新 `last_used_at`，后台可见最近使用时间

> 为什么不用 MCP SDK 自带的 TokenVerifier：它走完整 OAuth 2.1（需要 AS 端点、client
> 注册、PKCE），对「单进程、管理员手动发 token」的场景过重。这里用裸 ASGI 包装在
> `streamable_http_app` 前做 Bearer 校验，与 fuxi 既有鉴权一致，`stateless_http=True`
> 匹配无状态设计。

## 接入 Claude Desktop

1. 管理员在 fuxi 后台「管理 → MCP」新建 token，复制明文（仅一次）
2. 编辑 Claude Desktop 配置（macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "fuxi": {
      "url": "http://your-host:8000/mcp",
      "headers": {
        "Authorization": "Bearer <粘贴你的 token>"
      }
    }
  }
}
```

3. 重启 Claude Desktop，fuxi 的 8 个工具会出现在工具列表里，Agent 按需调用

> 线上入口走前端公开端口的 `/mcp` rewrite（后端仍监听 127.0.0.1）；Bearer token 仅用于受控网络环境，不要在不可信网络中传输或复用。

## 文件结构

| 文件 | 职责 |
|------|------|
| `backend/mcp_server.py` | FastMCP 实例、8 个工具注册、Bearer 鉴权包装、`is_available()` |
| `backend/routers/mcp_admin.py` | token CRUD（`/api/mcp-admin/tokens`）+ `verify_token()` |
| `sql/19_mcp_tokens.sql` | `mcp_tokens` 表 |
| `frontend/app/admin/mcp/page.tsx` | 后台 token 管理页 |

`backend/main.py` 在启动时 `import mcp_server`，若 `is_available()` 则构造 FastMCP、
拿到 `streamable_http_app`、在 lifespan 内 `session_manager.run()`（stateless_http 也
需要 session manager）。FastMCP 自身已提供 `/mcp` 路径，因此子应用挂在根路径并置于业务
路由之后，避免形成 `/mcp/mcp`。`/mcp` 不挂全局 `_auth`，因为它做自己的 Bearer token 校验。
