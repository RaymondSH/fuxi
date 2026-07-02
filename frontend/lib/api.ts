// 统一的后端请求封装。Web token 只存 httpOnly Cookie，JS 不读写凭证。
// access 过期时用 refresh Cookie 单飞换新 access，再重试原请求一次。

const BASE = "/api";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return { ...extra };
}

// ── refresh 单飞：并发 401 只触发一次换 token，其余请求等同一 promise ──
let _refreshPromise: Promise<void> | null = null;

function gotoLogin() {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

async function doRefresh(): Promise<void> {
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ client: "web" }),
  });
  if (!res.ok) {
    gotoLogin();
    throw new ApiError("unauthorized", "登录已过期，请重新登录", 401);
  }
}

/** 触发一次刷新（单飞）；多个 401 共享同一 Promise。 */
export function refreshAccess(): Promise<void> {
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
      const body = await res.json();
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
    // access 失效：尝试 refresh 后重试一次；登录页自身不刷新，避免循环
    if (
      res.status === 401 &&
      retry &&
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      try {
        await refreshAccess();
        return handle<T>(await retry(), undefined); // 重试只允许一次（retry 置空）
      } catch (e) {
        // refresh 失败已在 doRefresh 内清 token 跳登录，这里抛出中止业务
        throw e instanceof ApiError ? e : new ApiError("unauthorized", "登录已过期", 401);
      }
    }
    if (res.status === 429) code = "rate_limited";
    throw new ApiError(code, message, res.status);
  }
  // 204 No Content：无响应体，直接返回 null（调用方按需断言）
  if (res.status === 204) {
    return null as T;
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  const doFetch = () => fetch(`${BASE}${path}`, {
    cache: "no-store",
    credentials: "same-origin",
    headers: authHeaders(),
  });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method: "PUT",
      credentials: "same-origin",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  return handle<T>(await doFetch(), doFetch);
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const doFetch = () => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}${path}`, {
      method: "POST",
      credentials: "same-origin",
      body: form,
      headers: authHeaders(),
    });
  };
  return handle<T>(await doFetch(), doFetch);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const doFetch = () => fetch(`${BASE}${path}`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: authHeaders(),
  });
  return handle<T>(await doFetch(), doFetch);
}
