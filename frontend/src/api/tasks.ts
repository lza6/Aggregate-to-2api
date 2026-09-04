// P3 剩余风险治理：api.ts 拆分 —— tasks 域（任务列表 + 单任务 + DLQ + 图生图编辑任务）。
import { apiFetch, adminHeaders } from './core';

export interface Task {
  id: string;
  status: string;
  prompt: string | null;
  image_url: string | null;
  /** 画廊/详情用：后端 task_to_public 会把 file:// base64 读出内联（<10MB 时） */
  image_base64?: string | null;
  image_mime?: string | null;
  error: string | null;
  duration_sec: number | null;
  created_at: number;
  /** txt | img | vid（txt2img/img2img/txt2vid），后端默认 txt */
  type?: string;
  model: string;
  aspect_ratio?: string | null;
  client_ip?: string | null;
  client_location?: string | null;
  user_agent?: string | null;
  /** 阶段耗时拆解（当前仅 total_sec，预留扩展） */
  timings?: Record<string, number>;
}

export interface DLQItem {
  task_id: string;
  model: string;
  error: string | null;
  attempts: number;
  /** v7.7 契约对齐：后端字段名 last_attempt_at（api/db/core.py） */
  last_attempt_at: number;
  created_at?: number;
}

export async function fetchTasks(params?: { limit?: number; offset?: number; status?: string }): Promise<{ items: Task[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  if (params?.status) q.set('status', params.status);
  return apiFetch<{ items: Task[]; total: number }>(`/v1/tasks?${q}`);
}

export async function fetchTask(id: string): Promise<Task> {
  return apiFetch<Task>(`/v1/tasks/${id}`, { caller: '任务查询失败' });
}

export async function fetchEditTask(id: string): Promise<Task> {
  return apiFetch<Task>(`/v1/edit/tasks/${id}`, { caller: '图生图任务查询失败' });
}

export async function fetchDLQ(): Promise<{ items: DLQItem[]; count: number }> {
  return apiFetch<{ items: DLQItem[]; count: number }>('/v1/dead-letter-queue');
}

export async function retryDLQTask(taskId: string): Promise<{ status: string; detail?: string }> {
  return apiFetch<{ status: string; detail?: string }>(`/v1/dead-letter-queue/${taskId}/retry`, {
    method: 'POST',
    headers: adminHeaders(),
    caller: '重试失败',
  });
}

export async function clearDLQ(): Promise<{ status: string; detail?: string }> {
  return apiFetch<{ status: string; detail?: string }>('/v1/dead-letter-queue', {
    method: 'DELETE',
    headers: adminHeaders(),
    caller: '清空失败',
  });
}
