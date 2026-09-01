// P3 剩余风险治理：api.ts 拆分 —— chat 域（聊天补全 + 用量 + 额度 + 鉴权状态 + 模型目录 + 图生图生成）。
import { apiFetch, authHeaders } from './core';
import type { Task } from './tasks';

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

export interface ChatAuthStatus {
  enabled: boolean;
  admin_enabled?: boolean;
  key_mask?: string;
  key?: string;
  header: string;
  alt_headers: string[];
}

export async function fetchChatUsage(period = '24h'): Promise<ChatUsageStats> {
  return apiFetch<ChatUsageStats>(`/v1/chat/usage?period=${period}`);
}

export async function fetchChatRemaining(): Promise<ChatRemaining> {
  return apiFetch<ChatRemaining>('/v1/chat/remaining');
}

export async function fetchChatAuthStatus(options?: { adminKey?: string }): Promise<ChatAuthStatus> {
  const headers: Record<string, string> = {};
  if (options?.adminKey) headers['Authorization'] = `Bearer ${options.adminKey}`;
  return apiFetch<ChatAuthStatus>('/v1/chat/auth/status', { headers });
}

export async function fetchChatModels(): Promise<{ items: ChatModelInfo[]; count: number; auth_required?: boolean }> {
  return apiFetch<{ items: ChatModelInfo[]; count: number; auth_required?: boolean }>('/v1/chat/models');
}

// ── v6.5.0 在线生成（文生图/图生图）PLAYGROUND ──
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

const API_BASE = '';

/** 聊天补全（供 playground 用）；流式 SSE 响应体由页面自行 reader 解析；自动携带本地保存的 Key */
export async function chatCompletions(body: Record<string, unknown>, signal?: AbortSignal): Promise<Response> {
  return fetch(`${API_BASE}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
}
