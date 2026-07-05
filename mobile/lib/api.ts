// 后端请求封装。移植自 frontend/lib/api.ts，适配 React Native：
//   - BASE 走 EXPO_PUBLIC_API_BASE（默认线上 /api 反代）
//   - 双 token：access（15min，业务请求带）+ refresh（7d，仅换 access）
//     存 expo-secure-store（iOS Keychain / Android EncryptedSharedPreferences）
//   - secure-store 是异步的，故模块级缓存 token + 启动预加载，读时同步取
//   - 401 时用 refresh 单飞换新 access 并重试一次；refresh 失败才清 token 跳登录
//   - 429 → code='rate_limited'（配额用完）

import * as SecureStore from "expo-secure-store";

export const BASE = process.env.EXPO_PUBLIC_API_BASE || "http://118.25.93.30:19000/api";
const ACCESS_KEY = "fuxi_access";
const REFRESH_KEY = "fuxi_refresh";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

// ── token 存取 ──
// secure-store 异步，这里维护内存缓存：启动时 loadTokens() 预载，之后 getSync() 同步读。
let _accessCache: string | null = null;
let _refreshCache: string | null = null;

/** 启动时调用一次，把 secure-store 里的双 token 预载进内存。 */
export async function loadTokens(): Promise<void> {
  try {
    _accessCache = await SecureStore.getItemAsync(ACCESS_KEY);
    _refreshCache = await SecureStore.getItemAsync(REFRESH_KEY);
  } catch {
    _accessCache = null;
    _refreshCache = null;
  }
}

/** 同步取 access token（须在 loadTokens 完成后调用）。 */
export function getAccessToken(): string | null {
  return _accessCache;
}

/** 同步取 refresh token（仅 api.ts 内部 refresh 流程使用）。 */
export function getRefreshToken(): string | null {
  return _refreshCache;
}

export async function setTokens(access: string, refresh: string): Promise<void> {
  _accessCache = access;
  _refreshCache = refresh;
  await SecureStore.setItemAsync(ACCESS_KEY, access);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh);
}

/** 仅更新 access（refresh 换新 access 后用，refresh 不变）。 */
async function setAccessToken(access: string): Promise<void> {
  _accessCache = access;
  await SecureStore.setItemAsync(ACCESS_KEY, access);
}

export async function clearTokens(): Promise<void> {
  _accessCache = null;
  _refreshCache = null;
  await SecureStore.deleteItemAsync(ACCESS_KEY);
  await SecureStore.deleteItemAsync(REFRESH_KEY);
}

// ── 401 回调：由 AuthProvider 注册，refresh 失败后触发跳登录 ──
let _onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(fn: (() => void) | null): void {
  _onUnauthorized = fn;
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  const t = getAccessToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

// ── refresh 单飞：并发 401 只触发一次换 token，其余请求等同一 promise ──
let _refreshPromise: Promise<string> | null = null;

async function doRefresh(): Promise<string> {
  const rt = getRefreshToken();
  if (!rt) {
    await clearTokens();
    _onUnauthorized?.();
    throw new ApiError("unauthorized", "未登录", 401);
  }
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt, client: "mobile" }),
  });
  if (!res.ok) {
    // refresh 失效/被撤销 → 彻底登出
    await clearTokens();
    _onUnauthorized?.();
    throw new ApiError("unauthorized", "登录已过期，请重新登录", 401);
  }
  const body = await res.json() as { access_token?: string };
  if (!body.access_token) {
    throw new ApiError("unauthorized", "刷新未返回 access token", 401);
  }
  const access: string = body.access_token;
  await setAccessToken(access);
  return access;
}

/** 触发一次刷新（单飞）；多个 401 共享同一 Promise。 */
function refreshAccess(): Promise<string> {
  if (!_refreshPromise) {
    _refreshPromise = doRefresh().finally(() => {
      _refreshPromise = null;
    });
  }
  return _refreshPromise;
}

async function handle<T>(res: Response, retry?: () => Promise<Response>): Promise<T> {
  if (!res.ok) {
    let code = "http_error";
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json() as {
        error?: { code?: string; message?: string };
        detail?: string;
      };
      // 兼容两种错误体：{error:{code,message}} 与 FastAPI 的 {detail}
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      } else if (typeof body?.detail === "string") {
        message = body.detail;
      }
    } catch {
      /* 非 JSON 错误体，沿用状态码 */
    }
    // access 失效：尝试 refresh 后重试一次
    if (res.status === 401 && retry) {
      try {
        await refreshAccess();
        return handle<T>(await retry(), undefined); // 重试只允许一次（retry 置空）
      } catch (e) {
        // refresh 失败已在 doRefresh 内清 token 通知跳登录，这里抛出中止业务
        throw e instanceof ApiError ? e : new ApiError("unauthorized", "登录已过期", 401);
      }
    }
    if (res.status === 429) code = "rate_limited";
    throw new ApiError(code, message, res.status);
  }
  // 204 No Content 无返回体（DELETE /notes/{id} 等用），返回 null
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  const doFetch = () => fetch(`${BASE}${path}`, { headers: authHeaders() });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, { method: "DELETE", headers: authHeaders() });
  return handle<T>(await doFetch(), doFetch);
}

// 文件上传：RN 用 FormData + 文件 uri，调用方需按平台构造 file 对象。
// 暂未在本期使用，签名保留以对齐 Web 端。
export async function apiUpload<T>(path: string, file: { uri: string; name?: string; type?: string }): Promise<T> {
  const doFetch = () => {
    const form = new FormData();
    form.append("file", file as any);
    return fetch(`${BASE}${path}`, { method: "POST", body: form, headers: authHeaders() });
  };
  return handle<T>(await doFetch(), doFetch);
}
