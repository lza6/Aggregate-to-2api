const API_BASE = '';

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
  const res = await fetch(`${API_BASE}/v1/stats`);
  return res.json();
}

export async function fetchTasks(params?: { limit?: number; offset?: number; status?: string }): Promise<{ items: Task[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  if (params?.status) q.set('status', params.status);
  const res = await fetch(`${API_BASE}/v1/tasks?${q}`);
  return res.json();
}

export async function fetchProviders(): Promise<{ items: Record<string, ProviderSummary>; count: number }> {
  const res = await fetch(`${API_BASE}/v1/providers`);
  return res.json();
}

export async function fetchGallery(limit = 20, password?: string): Promise<{ items: GalleryItem[]; count: number }> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (password) q.set('password', password);
  const res = await fetch(`${API_BASE}/v1/gallery?${q}`);
  return res.json();
}

export interface LogEntry {
  ts: number;
  level: string;
  logger: string;
  message: string;
}

export async function fetchLogs(lines = 100): Promise<{ logs: LogEntry[] }> {
  const res = await fetch(`${API_BASE}/v1/logs?lines=${lines}`);
  return res.json();
}

export async function fetchDLQ(): Promise<{ items: DLQItem[]; count: number }> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue`);
  return res.json();
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
function adminHeaders(): Record<string, string> {
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
  const res = await fetch(`${API_BASE}/v1/admin/security/block-ip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`封禁失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

export async function unblockIp(ip: string): Promise<{ ok: boolean; removed: boolean; note?: string }> {
  const res = await fetch(`${API_BASE}/v1/admin/security/unblock-ip?ip=${encodeURIComponent(ip)}`, {
    method: 'DELETE',
    headers: adminHeaders(),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`解封失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

export async function fetchBlocklist(limit = 200): Promise<{ items: BlockRule[]; count: number }> {
  const res = await fetch(`${API_BASE}/v1/admin/security/blocklist?limit=${limit}`, { headers: adminHeaders() });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`封禁列表获取失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

export async function fetchBlockStatus(ip: string): Promise<{ ip: string; rule: BlockRule | null; blocked: boolean }> {
  const res = await fetch(`${API_BASE}/v1/admin/security/status?ip=${encodeURIComponent(ip)}`, { headers: adminHeaders() });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`封禁状态查询失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/diagnostics`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/account-pool?${q}`);
  return res.json();
}

export async function retryDLQTask(taskId: string): Promise<{ detail?: string; message?: string }> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue/${taskId}/retry`, {
    method: 'POST',
    headers: adminHeaders(),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`重试失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

export async function clearDLQ(): Promise<{ detail?: string; message?: string; success?: boolean }> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue`, {
    method: 'DELETE',
    headers: adminHeaders(),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`清空失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/routing/records?limit=${limit}`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/proxy-pool?${q}`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/system`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/chat/usage?period=${period}`);
  return res.json();
}

export async function fetchChatRemaining(): Promise<ChatRemaining> {
  const res = await fetch(`${API_BASE}/v1/chat/remaining`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/chat/auth/status`, { headers });
  return res.json();
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

function authHeaders(): Record<string, string> {
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
  const res = await fetch(`${API_BASE}/v1/models`);
  return res.json();
}

/** 文生图/图生图同步生成（自动携带本地保存 API Key）；需 Key，无 Key 后端返回 401 */
export async function generateImage(body: {
  prompt: string;
  aspect_ratio?: string;
  model?: string;
  resolution?: string;
  download?: boolean;
}, signal?: AbortSignal): Promise<Task> {
  const res = await fetch(`${API_BASE}/v1/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`生成失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

/** 图生图（AI 照片编辑，异步提交） */
export async function editImage(body: {
  image?: string;
  images?: string[];
  prompt: string;
  model?: string;
  download?: boolean;
}, signal?: AbortSignal): Promise<Task> {
  const res = await fetch(`${API_BASE}/v1/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`图生图提交失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

/** 轮询异步任务结果（/v1/tasks/{id} 或 /v1/edit/tasks/{id}） */
export async function fetchTask(id: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/v1/tasks/${id}`);
  if (!res.ok) throw new Error(`任务查询失败 HTTP ${res.status}`);
  return res.json();
}

export async function fetchEditTask(id: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/v1/edit/tasks/${id}`);
  if (!res.ok) throw new Error(`图生图任务查询失败 HTTP ${res.status}`);
  return res.json();
}

export async function fetchChatModels(): Promise<{ items: ChatModelInfo[]; count: number; auth_required?: boolean }> {
  const res = await fetch(`${API_BASE}/v1/chat/models`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/v1/ai-ecosystem`);
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`AI 生态数据获取失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
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
