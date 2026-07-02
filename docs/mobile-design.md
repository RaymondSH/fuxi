# fuxi 移动端设计文档

> 状态：脚手架阶段（M1）已完成。本文件是移动端选型、鉴权、网络打通与后续路线的单一真相。
> 接口契约沿用 [api-contract.md](api-contract.md)；鉴权沿用 [auth-design.md](auth-design.md)。

## 背景

fuxi 已有 Web（Next.js）+ 后端（FastAPI）。移动端定位为「内容消费入口」：碎片化阅读、
随时问答、知识图谱浏览。入库等策展操作仍在桌面端完成（移动端仅 admin 保留能力，优先级低）。

## 技术选型

| 层 | 选型 | 理由 |
|----|------|------|
| 框架 | React Native + Expo（SDK 52，expo-router） | 与 Web 同为 React/TS，可复用类型与逻辑；Expo 绕开原生编译配置，一条命令出两端 |
| 路由 | expo-router（文件式） | 与 Next.js App Router 思路一致 |
| 样式 | NativeWind v4（Tailwind v3 语法） | 复用 Web 端 class 名与色板，两端 UI 写法一致 |
| token 存储 | expo-secure-store | iOS Keychain / Android EncryptedSharedPreferences，比 localStorage 安全 |
| 状态 | React Context（auth） | 脚手架阶段最简；后续接 TanStack Query 做接口缓存 |

> 选 RN 而非 Flutter：团队已是 TS 栈，`lib/types.ts` 可直接复用；Flutter 需学 Dart 且无复用。
> 选 NativeWind 而非 StyleSheet：Web 端登录页等 UI 可近乎原样复制 class。

## 鉴权（已实现：双 token）

Web 与移动端共用 access/refresh token 体系，但凭据传输与存储严格分开：

| | Web | 移动端 |
|--|--|--|
| token 存放 | 后端写入 httpOnly Cookie，JavaScript 不可读 | expo-secure-store（Keychain / EncryptedSharedPreferences） |
| 请求携带 | Cookie（`credentials: include`） | `Authorization: Bearer <access>` |
| 401 处理 | 单飞 refresh 后重试，失败跳登录 | 单飞 refresh 后重试，失败清凭据并跳登录 |
| 有效期 | access 15 分钟、refresh 7 天 | 同上 |

登录请求显式传 `client=mobile` 时，响应体返回双 token；Web 登录只写 Cookie，不在响应体暴露
token。业务接口只接受 `type=access`，refresh token 不能冒充 Bearer access。

## 网络打通

线上后端 FastAPI 监听 `127.0.0.1:8000`（**内部**），仅由 Next.js `:19000` 通过 `/api` 反代对外。
移动端无法直连后端，三个方案：

| 方案 | 说明 | 状态 |
|------|------|------|
| **A（当前）** | 移动端走线上前端 `http://118.25.93.30:19000/api`，复用 Next.js rewrites 反代到后端 | ✅ 采用 |
| B | 本地后端 `localhost:8000`（开发期） | 可选，设 `EXPO_PUBLIC_API_BASE` |

`EXPO_PUBLIC_API_BASE` 默认 `http://118.25.93.30:19000/api`，改 `.env` 即切换。

### ATS / 明文 HTTP

线上是明文 HTTP，iOS 默认 ATS 会拦截。`app.json` 已配：
- iOS：`NSAppTransportSecurity.NSAllowsArbitraryLoads=true`
- Android：`usesCleartextTraffic=true`

> 当前线上采用 HTTP，因此这两项是运行所需配置。

### CORS

后端 `main.py` 加了 `CORSMiddleware`（`allow_origins=["*"]`，`allow_credentials=False`）。
Web 前端走反代同源不受影响；移动端（尤其 Expo Web 调试平台）需要。鉴权走 JWT，放开源不影响安全。

## 目录结构

```
mobile/
├── app.json / app.config.ts        # Expo 配置（ATS 例外、scheme、插件）
├── babel.config.js / metro.config.js   # NativeWind 集成
├── tailwind.config.js / global.css     # 色板（对齐 Web 端 globals.css）
├── tsconfig.json                   # @/* 路径别名
├── .env.example                    # EXPO_PUBLIC_API_BASE
├── app/
│   ├── _layout.tsx                 # 根布局：AuthProvider + Stack + 守卫
│   ├── index.tsx                   # 首页占位（用户名 + 登出）
│   └── login.tsx                   # 登录页（复刻 Web 端）
├── contexts/
│   └── AuthProvider.tsx           # login/logout/bootstrap/守卫 + 401 回调注册
└── lib/
    ├── api.ts                      # fetch 封装（secure-store + 异步 token + ApiError）
    └── types.ts                    # 从 frontend/lib/types.ts 复制
```

## 鉴权链路

```
启动 → AuthProvider.bootstrap
       ├─ loadToken() 从 secure-store 预载 token 到内存
       ├─ 有 token → GET /auth/me → 设 user（校验通过）/ 清 token（失效）
       └─ 无 token → loading=false

守卫 → loading 完成后：
       ├─ 无 user 且非 /login → router.replace("/login")
       └─ 有 user 且在 /login → router.replace("/")

登录 → POST /auth/login → setToken(secure-store) → 设 user → 跳首页
登出 → clearToken → 清 user → 跳登录
401  → api.ts 清 token → 触发 onUnauthorized 回调 → AuthProvider 清 user → 守卫跳登录
```

## 验证（脚手架阶段）

| 项 | 结果 |
|----|------|
| `npx tsc --noEmit` | ✅ 零错误 |
| `npx expo config` | ✅ 解析通过（scheme/slug/ios/android） |
| `npx expo start` | ✅ Metro bundler 启动成功 |

> 真机/模拟器登录跑通需本地有 Expo 环境且能访问线上后端。命令：
> `cd mobile && cp .env.example .env`（按需改）→ `npx expo start` → 按 i / a 开模拟器。

## 后续路线

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **M1**（已完成） | 脚手架 + 登录 + auth + API 封装 | — |
| M2 | Refresh token + 吊销接口 + 设备管理 | 新 SQL 表 |
| M3 | 检索页（搜索 + 标签筛选）+ 笔记详情 | M1 |
| M4 | 问答页（含 SSE 流式）+ 历史 | M1 |
| M5 | 知识图谱（力导向）+ 主题页 Wiki | M1 |
| M6 | 入库（admin：链接/拍照/文件上传） | M3 |
| M7 | 推送通知、离线缓存 | 后期 |
