// 统一的后端请求封装。前端始终用相对 /api 路径，由 next.config 代理到 FastAPI。
// 登录后带 Bearer token；遇 401 清 token 跳登录页。

const BASE = "/api";
const TOKEN_KEY = "fuxi_token";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

// ── token 存取（localStorage；SSR 下安全降级）──
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

async function handle<T>(res: Response): Promise<T> {
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
    // 未登录 / 失效：清 token 并跳登录（登录页本身不跳，避免循环）
    if (res.status === 401 && typeof window !== "undefined") {
      clearToken();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    if (res.status === 429) code = "rate_limited";
    throw new ApiError(code, message, res.status);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  return handle<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(res);
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(res);
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  return handle<T>(res);
}
