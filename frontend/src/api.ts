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
  429: '请求过于频繁，请稍后再试',
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

export interface Stats {
  total_requests: number;
  total_images: number;
  total_errors: number;
  processing: number;
  queued: number;
  queue_capacity: number;
  workers: number;
  uptime_human: string;
  // 后端实际返回 { day, total, images, errors }（api/db.py stats_daily）——旧接口类型描述有误
  daily: { day: string; total: number; images: number; errors: number }[];
  monthly: { month: string; total: number; images: number; errors: number }[];
  solver: {
    status: string;
    solve_total: number;
    solve_success_total: number;
    solve_failure_total: number;
    solve_avg_seconds: number | null;
    window_success_rate: number | null;
    window_solve_count: number;
    window_avg_seconds: number | null;
    consecutive_failures: number;
    circuit_open: boolean;
    failure_reasons: Record<string, number>;
    rejected_total: number;
    token_pools: Record<string, { key: string; size: number; target: number; idle: boolean }>;
  };
  base64_gc?: {
    total_files: number; total_gb: number;
    hot_files: number; hot_gb: number;
    cold_files: number; cold_gb: number;
    quota_gb: number; usage_pct: number;
    pending_cleanup_count: number; pending_cleanup_gb: number;
  };
}

export interface Task {
  id: string;
  status: string;
  prompt: string;
  image_url: string | null;
  error: string | null;
  duration_sec: number | null;
  created_at: number;
  model: string;
  client_ip?: string | null;
  client_location?: string | null;
}

export interface ProviderSummary {
  display_name: string;
  base_url: string;
  capabilities: string[];
  model_count: number;
  health_status: string;
  credits: number | null;
  error_count: number;
  degraded: boolean;
  // v6.9.1: 是否需要号池账号（供前端把「不需要账号」提供商排前面、nanobanana 折叠到末尾）
  needs_account?: boolean;
  // v6.9.1: 是否每请求需轮换代理（供前端展示能力说明）
  needs_proxy_per_request?: boolean;
}

export interface GalleryItem {
  image_url: string;
  image_mime: string | null;
  prompt: string;
  aspect_ratio: string;
  duration_sec: number | null;
}

export interface DLQItem {
  task_id: string;
  model: string;
  error: string | null;
  attempts: number;
  last_attempt: number;
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

export async function fetchStats(): Promise<Stats> {
  return apiFetch<Stats>('/v1/stats');
}

export async function fetchTasks(params?: { limit?: number; offset?: number; status?: string }): Promise<{ items: Task[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  if (params?.status) q.set('status', params.status);
  return apiFetch<{ items: Task[]; total: number }>(`/v1/tasks?${q}`);
}

export async function fetchProviders(): Promise<{ items: Record<string, ProviderSummary>; count: number }> {
  return apiFetch<{ items: Record<string, ProviderSummary>; count: number }>('/v1/providers');
}

// v6.9.1: 邮箱池上游源清单（/v1/email-sources），供 Providers 页「邮箱池上游」卡片展示。
// 与 ProviderCard 同形态：name / base_url(官网) / priority / available / success_count / failure_count / last_error。
export interface EmailSource {
  name: string;
  base_url: string | null;
  priority: number;
  available: boolean;
  success_count: number;
  failure_count: number;
  last_error: string | null;
}

export async function fetchEmailSources(): Promise<{ items: EmailSource[]; count: number }> {
  return apiFetch<{ items: EmailSource[]; count: number }>('/v1/email-sources');
}

export async function fetchGallery(limit = 20, password?: string): Promise<{ items: GalleryItem[]; count: number }> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (password) q.set('password', password);
  return apiFetch<{ items: GalleryItem[]; count: number }>(`/v1/gallery?${q}`);
}

/** P1-1 画廊签名 URL：站长签发有限期访问链接（管理 Key 鉴权，后端返回带 exp+sig 的 URL）。 */
export async function signGallery(limit = 20, adminKey?: string): Promise<{ url: string; expires_in: number }> {
  const q = new URLSearchParams({ limit: String(limit) });
  const headers: Record<string, string> = {};
  if (adminKey) headers['Authorization'] = `Bearer ${adminKey}`;
  return apiFetch<{ url: string; expires_in: number }>('/v1/gallery/sign?' + q.toString(), { headers, caller: '签名失败' });
}

export interface LogEntry {
  ts: number;
  level: string;
  logger: string;
  message: string;
}

export async function fetchLogs(lines = 100): Promise<{ logs: LogEntry[] }> {
  return apiFetch<{ logs: LogEntry[] }>(`/v1/logs?lines=${lines}`);
}

export async function fetchDLQ(): Promise<{ items: DLQItem[]; count: number }> {
  return apiFetch<{ items: DLQItem[]; count: number }>('/v1/dead-letter-queue');
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
// P2-4 barrel：导出供 api/admin.ts | api/tasks.ts 等拆分子模块复用（函数体内引用，运行时 live binding 安全）。
export function adminHeaders(): Record<string, string> {
  const key = getStoredAdminKey();
  return key ? { 'Authorization': `Bearer ${key}` } : {};
}

// ── v6.7.0: 安全风控（封禁/解封/列表/状态/统计，均需管理 Key）──
export interface BlockRule {
  ip: string;
  block_type: 'block' | 'daily_limit';
  daily_limit?: number | null;
  reason?: string | null;
  ttl_seconds?: number | null;
  created_at?: number | null;
  expire_at?: number | null;
}

export async function blockIp(body: {
  ip: string;
  block_type?: 'block' | 'daily_limit';
  daily_limit?: number;
  reason?: string;
  ttl_seconds?: number;
}): Promise<{ ok: boolean; record: BlockRule }> {
  return apiFetch<{ ok: boolean; record: BlockRule }>('/v1/admin/security/block-ip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminHeaders() },
    body: JSON.stringify(body),
    caller: '封禁失败',
  });
}

export async function unblockIp(ip: string): Promise<{ ok: boolean; removed: boolean; note?: string }> {
  return apiFetch<{ ok: boolean; removed: boolean; note?: string }>(`/v1/admin/security/unblock-ip?ip=${encodeURIComponent(ip)}`, {
    method: 'DELETE',
    headers: adminHeaders(),
    caller: '解封失败',
  });
}

export interface BlocklistPage {
  items: BlockRule[];
  count: number;
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export async function fetchBlocklist(
  opts: { page?: number; pageSize?: number; limit?: number } = {},
): Promise<BlocklistPage> {
  const { page = 1, pageSize = 100, limit } = opts;
  const params = limit != null
    ? `limit=${limit}`
    : `page=${page}&page_size=${pageSize}`;
  return apiFetch<BlocklistPage>(`/v1/admin/security/blocklist?${params}`, {
    headers: adminHeaders(),
    caller: '封禁列表获取失败',
  });
}

export async function fetchBlockStatus(ip: string): Promise<{ ip: string; rule: BlockRule | null; blocked: boolean }> {
  return apiFetch<{ ip: string; rule: BlockRule | null; blocked: boolean }>(`/v1/admin/security/status?ip=${encodeURIComponent(ip)}`, { headers: adminHeaders(), caller: '封禁状态查询失败' });
}

// ── v3.1.0 S-6/S-7: 只读诊断 + worker 健康 ──
export interface DiagnosticsWorker {
  id: number;
  alive: boolean;
  stale: boolean;
  last_active_ago_seconds: number;
  processed: number;
}
export interface Diagnostics {
  status: string;
  timestamp: number;
  db: { size_mb: number | null; wal_size_mb: number; rows: number };
  queue: { queued: number; capacity: number; admin: number; high: number; normal: number; processing: number };
  workers: { total: number; alive: number; stale_count: number; stale_ids: number[]; detail: DiagnosticsWorker[] };
  token_pools: Record<string, unknown>;
  solver: { status: string; circuit_open: boolean; window_success_rate: number | null; avg_solve_seconds: number | null };
  slow_log: { count: number; avg_total_ms: number; max_total_ms: number; slowest_stage: string | null };
  disk: {
    free_gb: number | null; total_gb: number | null; used_percent: number | null;
    log_dir_writable: boolean;
  };
  uptime_seconds: number;
}

export async function fetchDiagnostics(): Promise<Diagnostics> {
  return apiFetch<Diagnostics>('/v1/diagnostics');
}

// ── v6.8.0: 成本可视化（M6-F3，对应后端 /v1/cost）──
export interface CostMonthly {
  month: string;
  cost_usd: number;
  calls: number;
}

export interface CostByProviderRow {
  provider: string;
  calls: number;
  cost_usd: number;
  tokens: number;
  // 图片成本挂 nanobanana 行时追加
  credits_used?: number;
  images?: number;
}

export interface CostByModelRow {
  provider: string;
  model: string;
  cost_usd: number;
  calls: number;
}

export interface CostOverview {
  month_to_date_usd: number;
  today_usd: number;
  budget_usd: number;
  budget_remaining_pct: number;
  over_budget: boolean;
  burn_rate_warning: boolean;
  monthly: CostMonthly[];
  by_provider: CostByProviderRow[];
  by_model: CostByModelRow[];
  image_cost_usd_mtd: number;
  note?: string;
}

export async function fetchCost(): Promise<CostOverview> {
  return apiFetch<CostOverview>('/v1/cost');
}

export interface AccountPoolProviderStats {
  total: number;
  ok: number;
  active: number;
  working: number;
  exhausted: number;
  cooling: number;
  dead: number;
  banned: number;
  registering: number;
  unregistered: number;
  credits: number;
  target: number;
  auto_register: boolean;
}

export interface AccountPoolItem {
  email: string;
  credits: number;
  status: string;
  created_at: number | null;
  checkin_at: number | null;
  register_ip?: string | null;
  // v6.3.4/v6.5.0: 签到画像与存活天数
  checkin_total?: number;
  checkin_cycle_day?: number;
  credits_earned_total?: number;
  next_claim_at?: number | null;
  age_days?: number | null;
  // v6.5.1: 每账号出图消耗画像
  credits_used_total?: number;
  images_used?: number;
  last_used_at?: number | null;
  credits_earned?: number;
}

export interface LiveRegistration {
  stage: string;
  stage_label: string;
  email: string;
  email_source: string;
  created_at: number;
  updated_at: number;
  last_error: string | null;
  error_category: string | null;
  stage_durations: Record<string, number>;
}

export interface AccountPoolResponse {
  accounts: Record<string, AccountPoolProviderStats>;
  // v6.6.0: 号池补满速率画像（每日新增 + 距目标天数）；后端字段名为 growth_stats
  growth_stats?: {
    total: number;
    new_in_24h: number;
    new_in_7d: number;
    avg_daily_7d: number;
    ok: number;
    target: number;
    gap: number;
    eta_days: number | null;
  };
  // v6.6.0: 成本口径聚合（配合 Dashboard 主卡）
  cost_summary?: {
    total_credits_used: number;
    total_images_used: number;
    total_credits_earned: number;
    accounts_with_usage: number;
    total_accounts: number;
    avg_cost_per_image: number | null;
  };
  email_pool: {
    total_registered: number;
    by_provider: Record<string, number>;
    by_status?: Record<string, number>;
    successful_registrations?: number;
    failed_registrations?: number;
  };
  live_registration?: LiveRegistration | null;
  items: AccountPoolItem[];
  items_total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function fetchAccountPool(params: { page?: number; pageSize?: number; search?: string } = {}): Promise<AccountPoolResponse> {
  const q = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  if (params.search?.trim()) q.set('search', params.search.trim());
  return apiFetch<AccountPoolResponse>(`/v1/account-pool?${q}`);
}

export async function retryDLQTask(taskId: string): Promise<{ detail?: string; message?: string }> {
  return apiFetch<{ detail?: string; message?: string }>(`/v1/dead-letter-queue/${taskId}/retry`, {
    method: 'POST',
    headers: adminHeaders(),
    caller: '重试失败',
  });
}

export async function clearDLQ(): Promise<{ detail?: string; message?: string; success?: boolean }> {
  return apiFetch<{ detail?: string; message?: string; success?: boolean }>('/v1/dead-letter-queue', {
    method: 'DELETE',
    headers: adminHeaders(),
    caller: '清空失败',
  });
}

// ── v3.2: 自适应路由记录 ──
export interface RoutingRecord {
  ts: number;
  request_id: string;
  model: string;
  requested_provider: string;
  selected_provider: string;
  score: number;
  scores: Record<string, number>;
  latency_ms: number;
  success: boolean | null;
  reason: string;
}

export interface RoutingNode {
  provider_id: string;
  success_count: number;
  failure_count: number;
  ewma_latency_ms: number;
  in_flight_requests: number;
  circuit_state: string;
  score: number;
}

export async function fetchRoutingRecords(limit = 50): Promise<{ records: RoutingRecord[]; nodes: Record<string, RoutingNode> }> {
  return apiFetch<{ records: RoutingRecord[]; nodes: Record<string, RoutingNode> }>(`/v1/routing/records?limit=${limit}`);
}

// ── 代理池（P3-4 健康体检复用） ──
export interface ProxyPoolEntry {
  url: string;
  source: string;
  daily_uses: number;
  use_count: number;
  cooling: boolean;
  cooldown_seconds: number;
  fails: number;
  country: string;
  country_code: string;
  country_emoji: string;
  latency_ms: number;
  checked_ago_seconds: number;
  protocols: unknown;
}

export interface ProxyPoolSnapshot {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  residential: number;
  free: number;
  available: number;
  cooldown: number;
  items: ProxyPoolEntry[];
  top: ProxyPoolEntry[];
}

export async function fetchProxyPool(params: { page?: number; pageSize?: number } = {}): Promise<ProxyPoolSnapshot> {
  const q = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  return apiFetch<ProxyPoolSnapshot>(`/v1/proxy-pool?${q}`);
}

// ── 服务器规格 ──
export interface SystemSpec {
  cpu: { cores: number; model: string };
  memory: { total_mb: number; total_gb: number };
  disk: { total_gb: number; used_gb: number; free_gb: number };
  adaptive: {
    workers: number;
    upstream_inflight: number;
    token_pool_size: number;
    max_queue: number;
  };
}

export async function fetchSystemSpec(): Promise<SystemSpec> {
  return apiFetch<SystemSpec>('/v1/system');
}

// ── v4.4 AI 聊天 ──
export interface ChatUsageStats {
  period: string;
  total_calls: number;
  ok_calls: number;
  fail_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  tool_calls: number;
  avg_duration_ms: number | null;
  today_calls: number;
  today_tokens: number;
  cost_usd?: number;
  today_cost_usd?: number;
  by_model: { model: string; calls: number; prompt_tokens: number; completion_tokens: number }[];
}

export interface ChatRemaining {
  available_proxies: number;
  calls_per_proxy_per_hour: number;
  hourly_limit: number;
  used_last_hour: number;
  remaining: number;
}

export interface ChatModelInfo {
  id: string;
  display_name: string;
  context_window: number;
  capabilities: string[];
  price_per_mtok?: number | null;
  max_messages?: number;
}

export async function fetchChatUsage(period = '24h'): Promise<ChatUsageStats> {
  return apiFetch<ChatUsageStats>(`/v1/chat/usage?period=${period}`);
}

export async function fetchChatRemaining(): Promise<ChatRemaining> {
  return apiFetch<ChatRemaining>('/v1/chat/remaining');
}

export interface ChatAuthStatus {
  enabled: boolean;
  admin_enabled?: boolean;
  key_mask?: string;
  key?: string;
  header: string;
  alt_headers: string[];
}

export async function fetchChatAuthStatus(options?: { adminKey?: string }): Promise<ChatAuthStatus> {
  const headers: Record<string, string> = {};
  if (options?.adminKey) headers['Authorization'] = `Bearer ${options.adminKey}`;
  return apiFetch<ChatAuthStatus>('/v1/chat/auth/status', { headers });
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

// P2-4 barrel：导出供 api/chat.ts 拆分子模块复用（函数体内引用，运行时 live binding 安全）。
export function authHeaders(): Record<string, string> {
  const key = getStoredApiKey();
  return key ? { 'Authorization': `Bearer ${key}` } : {};
}

// ── v6.5.0 在线生成（文生图/图生图）PLAYGROUND ──
export interface ImageModelInfo {
  id: string;
  name: string;
  upstream_model: string;
  capabilities: string[];
  aspect_ratios: string[];
  resolutions: string[];
  account_required?: boolean;
  description?: string;
}

/** 全量模型目录（/v1/models），按 provider 分组；含生图模型 capability */
export async function fetchImageModels(): Promise<{ items: Record<string, ImageModelInfo[]>; count: number }> {
  return apiFetch<{ items: Record<string, ImageModelInfo[]>; count: number }>('/v1/models');
}

/** 文生图/图生图同步生成（自动携带本地保存 API Key）；需 Key，无 Key 后端返回 401 */
export async function generateImage(body: {
  prompt: string;
  aspect_ratio?: string;
  model?: string;
  resolution?: string;
  download?: boolean;
}, signal?: AbortSignal): Promise<Task> {
  return apiFetch<Task>('/v1/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
    caller: '生成失败',
  });
}

/** 图生图（AI 照片编辑，异步提交） */
export async function editImage(body: {
  image?: string;
  images?: string[];
  prompt: string;
  model?: string;
  download?: boolean;
}, signal?: AbortSignal): Promise<Task> {
  return apiFetch<Task>('/v1/edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
    caller: '图生图提交失败',
  });
}

/** 轮询异步任务结果（/v1/tasks/{id} 或 /v1/edit/tasks/{id}） */
export async function fetchTask(id: string): Promise<Task> {
  return apiFetch<Task>(`/v1/tasks/${id}`, { caller: '任务查询失败' });
}

export async function fetchEditTask(id: string): Promise<Task> {
  return apiFetch<Task>(`/v1/edit/tasks/${id}`, { caller: '图生图任务查询失败' });
}

export async function fetchChatModels(): Promise<{ items: ChatModelInfo[]; count: number; auth_required?: boolean }> {
  return apiFetch<{ items: ChatModelInfo[]; count: number; auth_required?: boolean }>('/v1/chat/models');
}

// ── v6.7.0: TensorFeed AI 生态展示 ──
export interface AiEcosystemModel {
  id: string;
  name?: string;
  inputPrice?: number | null;
  outputPrice?: number | null;
  contextWindow?: number | null;
  tier?: string | null;
  released?: string | null;
}
export interface AiEcosystemProvider {
  id: string;
  name: string;
  models: AiEcosystemModel[];
}
export interface AiEcosystemService {
  name: string;
  status: string;
  provider?: string | null;
}
export interface AiEcosystemNewsItem {
  title?: string;
  source?: string;
  url?: string;
  publishedAt?: string;
}
export interface AiEcosystemResponse {
  models: {
    available: boolean;
    last_updated?: string | null;
    count: number;
    providers: AiEcosystemProvider[];
  };
  status: {
    available: boolean;
    all_operational: boolean;
    service_count: number;
    services: AiEcosystemService[];
    issues: string[];
  };
  today: {
    available: boolean;
    generated_at?: string | null;
    news: AiEcosystemNewsItem[];
    inference: Record<string, unknown>;
    papers: unknown[];
    hf: unknown[];
  };
  health: {
    available: boolean;
    news_count: number | null;
    model_count: number | null;
  };
  cache: {
    ttl_seconds: number;
    fetched_from_upstream_at: number;
  };
  stale?: boolean;
}

export async function fetchAiEcosystem(): Promise<AiEcosystemResponse> {
  return apiFetch<AiEcosystemResponse>('/v1/ai-ecosystem', { caller: 'AI 生态数据获取失败' });
}

/** 聊天补全（供 playground 用）；流式 SSE 响应体由页面自行 reader 解析；自动携带本地保存的 Key */
export async function chatCompletions(body: Record<string, unknown>, signal?: AbortSignal): Promise<Response> {
  return fetch(`${API_BASE}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
}
