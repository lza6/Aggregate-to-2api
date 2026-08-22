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

export async function fetchLogs(lines = 100): Promise<{ logs: any[] }> {
  const res = await fetch(`${API_BASE}/v1/logs?lines=${lines}`);
  return res.json();
}

export async function fetchDLQ(): Promise<{ items: DLQItem[]; count: number }> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue`);
  return res.json();
}

export async function fetchAccountPool(): Promise<any> {
  const res = await fetch(`${API_BASE}/v1/account-pool`);
  return res.json();
}

export async function retryDLQTask(taskId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue/${taskId}/retry`, { method: 'POST' });
  return res.json();
}

export async function clearDLQ(): Promise<any> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue`, { method: 'DELETE' });
  return res.json();
}