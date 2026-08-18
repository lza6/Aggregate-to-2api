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
  daily: { date: string; requests: number; images: number; errors: number }[];
  solver: {
    status: string;
    solve_total: number;
    solve_success_total: number;
    solve_failure_total: number;
    window_success_rate: number | null;
    circuit_open: boolean;
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

export interface Provider {
  prefix: string;
  name: string;
  models: number;
  status: string;
  error_count: number;
}

export interface GalleryItem {
  image_url: string;
  prompt: string;
  aspect_ratio: string;
  duration_sec: number | null;
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

export async function fetchProviders(): Promise<{ providers: Provider[] }> {
  const res = await fetch(`${API_BASE}/v1/providers`);
  return res.json();
}

export async function fetchGallery(limit = 20): Promise<{ items: GalleryItem[] }> {
  const res = await fetch(`${API_BASE}/v1/gallery?limit=${limit}`);
  return res.json();
}

export async function fetchLogs(lines = 100): Promise<{ logs: any[] }> {
  const res = await fetch(`${API_BASE}/v1/logs?lines=${lines}`);
  return res.json();
}

export async function fetchDLQ(): Promise<{ items: any[] }> {
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
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue/clear`, { method: 'POST' });
  return res.json();
}