// P3 剩余风险治理：api.ts 拆分 —— core 域（统一 fetch 封装 + 错误 + Toast + Key 存储）。
// 子域模块（providers/tasks/chat/security/stats）从本文件 import apiFetch/authHeaders/adminHeaders，
// index.ts barrel 聚合 re-export，避免 api.ts 与 api/ 同名路径歧义。

const API_BASE = '';

// ── 统一错误处理（P1-4）──────────────────────────────────────────────
// 所有经 apiFetch 的请求：统一超时、统一错误规范化（非 2xx 抛 ApiError，
// 映射 {status, code, message}；网络错误/超时 status=0，code 为 NETWORK_ERROR / TIMEOUT）。

/** 统一 API 错误对象。status=0 表示非 HTTP 错误（网络错误/超时/取消）。 */
export class ApiError extends Error {
  status: number;
  code: string | null;
  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** apiFetch 专有配置（在 RequestInit 基础上追加）。 */
export interface ApiFetchOptions extends RequestInit {
  /** 请求超时（ms），默认 30000；超时抛 ApiError(status=0, code='TIMEOUT')。 */
  timeoutMs?: number;
  /** 追踪/动作名：非 2xx 时拼进错误消息前缀（如「封禁失败 HTTP 401: ...」）；缺省用状态中文文案。 */
  caller?: string;
}

/** 常见 HTTP 状态的中文可读文案（响应体无可解析 detail 时兜底）。 */
const STATUS_TEXT: Record<number, string> = {
  400: '请求参数有误',
  401: '未授权或凭证缺失',
  403: '禁止访问或凭证无效',
  404: '资源不存在',
  405: '请求方法不支持',
  408: '请求超时',
  409: '资源冲突',
  410: '资源已失效',
  413: '请求体过大',
  415: '不支持的媒体类型',
  422: '请求参数校验失败',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误',
  501: '未实现的功能',
  502: '网关错误',
  503: '服务暂时不可用',
  504: '网关超时',
};

const DEFAULT_TIMEOUT_MS = 30_000;

/** 解析错误响应体 → { code, message }。code 优先取 body.code / body.error.code。 */
async function readErrorBody(res: Response): Promise<{ code: string | null; message: string }> {
  let text = '';
  try { text = await res.text(); } catch { text = ''; }
  let body: unknown = null;
  if (text) {
    try { body = JSON.parse(text); } catch { body = null; }
  }
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    const errObj = obj.error && typeof obj.error === 'object' ? obj.error as Record<string, unknown> : undefined;
    const code = typeof obj.code === 'string' ? obj.code
      : errObj && typeof errObj.code === 'string' ? errObj.code as string : null;
    const detail = obj.detail ?? obj.message ?? errObj?.message ?? obj.error;
    const message = typeof detail === 'string' ? detail.slice(0, 200)
      : typeof detail === 'number' ? String(detail)
      : detail && typeof detail === 'object' ? JSON.stringify(detail).slice(0, 200)
      : text.slice(0, 200);
    return { code, message };
  }
  return { code: null, message: text.slice(0, 200) };
}

/**
 * 统一 fetch 封装：
 * - 30s 超时（AbortController + race）
 * - 非 2xx 抛 ApiError（带 status/code/message）；网络错误 status=0 code=NETWORK_ERROR；超时 status=0 code=TIMEOUT
 * - 调用方传外部 signal 时透传给 fetch（与调用方取消联动）
 */
export async function apiFetch<T>(path: string, opts: ApiFetchOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, caller = '', ...init } = opts;
  const controller = new AbortController();
  const externalSignal = init.signal ?? undefined;
  // 调用方传外部 signal 时优先透传（保持 AbortSignal 同一性，供测试与调用方取消联动）；
  // 否则用内部 controller.signal 让超时能真实中止底层请求。
  const fetchSignal = externalSignal ?? controller.signal;
  if (externalSignal?.aborted) controller.abort();
  else if (externalSignal) externalSignal.addEventListener('abort', () => controller.abort(), { once: true });

  let timerId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timerId = setTimeout(() => {
      controller.abort();
      reject(new ApiError(0, caller ? `${caller} 超时，请稍后重试` : '请求超时，请稍后重试', 'TIMEOUT'));
    }, timeoutMs);
  });
  // 防未处理拒绝：timeout / fetchPromise 任一先 settle 后另一方的 rejection 需被吞掉
  void timeout.catch(() => { /* noop */ });
  const fetchPromise = fetch(`${API_BASE}${path}`, { ...init, signal: fetchSignal });
  void fetchPromise.catch(() => { /* noop */ });

  let res: Response;
  try {
    res = await Promise.race([fetchPromise, timeout]);
  } catch (e) {
    clearTimeout(timerId);
    if (e instanceof ApiError) throw e;
    const name = (e as Error)?.name;
    if (name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw new ApiError(0, caller ? `${caller} 已取消` : '请求已被取消', 'ABORTED');
      }
      throw new ApiError(0, caller ? `${caller} 超时，请稍后重试` : '请求超时，请稍后重试', 'TIMEOUT');
    }
    throw new ApiError(0, caller ? `${caller} 网络错误，请检查网络连接` : '网络错误，请检查网络连接', 'NETWORK_ERROR');
  }
  clearTimeout(timerId);

  if (!res.ok) {
    const { code, message: detail } = await readErrorBody(res);
    const statusText = STATUS_TEXT[res.status] ?? `HTTP ${res.status}`;
    // caller 给定时用「caller HTTP <status>: <detail>」；否则用状态中文文案（可带 detail）
    const message = caller
      ? (detail ? `${caller} HTTP ${res.status}: ${detail}` : `${caller} HTTP ${res.status}`)
      : `${statusText}${code ? `（${code}）` : ''}${detail ? `：${detail}` : ''}`;
    throw new ApiError(res.status, message, code);
  }
  // 200 空 body（如某些 DELETE 返回 204/空串）→ 返回 null，而非抛裸 SyntaxError
  const text = await res.text().catch(() => '');
  if (!text) return null as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

// ── 全局 Toast 通知 ──
export type ToastType = 'success' | 'error' | 'info';
export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

let toastListeners: ((toast: Toast) => void)[] = [];
export function onToast(fn: (toast: Toast) => void) {
  toastListeners.push(fn);
  return () => { toastListeners = toastListeners.filter(f => f !== fn); };
}
let toastId = 0;
export function notify(message: string, type: ToastType = 'info') {
  const toast: Toast = { id: ++toastId, message, type };
  toastListeners.forEach(f => f(toast));
}

// ── v6.7.0: 管理 Key（仅浏览器 localStorage，仅用于管理面写操作；永不注入匿名只读请求）──
// 与 IF_ADMIN_KEYS / IF_API_KEYS 的鉴权边界对应：封禁/解封/DLQ 重试/清空等
// 「写操作」要求携带管理 Key；只读展示（stats/tasks/account-pool 等）保持公开。
const ADMIN_KEY_STORAGE = 'imagefreeAdminApiKey';

export function getStoredAdminKey(): string {
  try { return localStorage.getItem(ADMIN_KEY_STORAGE) ?? ''; } catch { return ''; }
}

export function setStoredAdminKey(key: string): void {
  try {
    if (key.trim()) localStorage.setItem(ADMIN_KEY_STORAGE, key.trim());
    else localStorage.removeItem(ADMIN_KEY_STORAGE);
  } catch { /* ignore */ }
}

/** 管理面写操作头：仅当本地保存了管理 Key 才附带 Authorization；无 Key 时由后端决定（401/403/开放模式）。 */
export function adminHeaders(): Record<string, string> {
  const key = getStoredAdminKey();
  return key ? { 'Authorization': `Bearer ${key}` } : {};
}

// ── 本地保存的 API Key（仅浏览器 localStorage，永不上传） ──
const CHAT_KEY_STORAGE = 'imagefreeChatApiKey';

export function getStoredApiKey(): string {
  try { return localStorage.getItem(CHAT_KEY_STORAGE) ?? ''; } catch { return ''; }
}

export function setStoredApiKey(key: string): void {
  try {
    if (key.trim()) localStorage.setItem(CHAT_KEY_STORAGE, key.trim());
    else localStorage.removeItem(CHAT_KEY_STORAGE);
  } catch { /* ignore */ }
}

export function authHeaders(): Record<string, string> {
  const key = getStoredApiKey();
  return key ? { 'Authorization': `Bearer ${key}` } : {};
}
