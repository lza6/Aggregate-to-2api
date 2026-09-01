// P3 剩余风险治理：api.ts 拆分 —— misc 域（stats/诊断/成本/号池/画廊/日志/系统规格/AI 生态/SSE 指标）。
import { apiFetch, adminHeaders } from './core';

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

export async function fetchStats(): Promise<Stats> {
  return apiFetch<Stats>('/v1/stats');
}

export interface GalleryItem {
  image_url: string;
  image_mime: string | null;
  prompt: string;
  aspect_ratio: string;
  duration_sec: number | null;
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

// ── P3-2: SSE 事件流指标看板（只读，需 admin key）──
export interface SseStatsSnapshot {
  total_events: number;
  events_by_type: Record<string, number>;
  retry_events: number;
  compensation_rate: number;
  total_subscriptions: number;
  cancelled_subscriptions: number;
  cancellation_rate: number;
  tasks_seen: number;
  avg_events_per_task: number;
  uptime_seconds: number;
}

export async function fetchSseStats(): Promise<SseStatsSnapshot> {
  return apiFetch<SseStatsSnapshot>('/v1/sse/stats', {
    headers: adminHeaders(),
    caller: 'SSE 指标获取失败',
  });
}
