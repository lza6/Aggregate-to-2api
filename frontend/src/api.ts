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
}

export interface AccountPoolResponse {
  accounts: Record<string, AccountPoolProviderStats>;
  email_pool: {
    total_registered: number;
    by_provider: Record<string, number>;
    by_status?: Record<string, number>;
    successful_registrations?: number;
    failed_registrations?: number;
  };
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
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue/${taskId}/retry`, { method: 'POST' });
  return res.json();
}

export async function clearDLQ(): Promise<{ detail?: string; message?: string; success?: boolean }> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue`, { method: 'DELETE' });
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

export async function fetchChatModels(): Promise<{ items: ChatModelInfo[]; count: number }> {
  const res = await fetch(`${API_BASE}/v1/chat/models`);
  return res.json();
}

/** 聊天补全（供 playground 用）；流式 SSE 响应体由页面自行 reader 解析 */
export async function chatCompletions(body: Record<string, unknown>, signal?: AbortSignal): Promise<Response> {
  return fetch(`${API_BASE}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
}