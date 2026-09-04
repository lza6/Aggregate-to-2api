// P3 剩余风险治理：api.ts 拆分 —— providers 域（提供商看板 + 邮箱池上游 + 自适应路由 + 代理池 + 模型目录）。
import { apiFetch } from './core';

export interface ProviderSummary {
  display_name: string;
  base_url: string;
  capabilities: string[];
  model_count: number;
  health_status: string;
  /** v7.7 契约对齐：仅生图提供商注入 credits（聊天提供商行无此键），故为可选 */
  credits?: number | null;
  error_count: number;
  degraded: boolean;
  // v6.9.1: 是否需要号池账号（供前端把「不需要账号」提供商排前面、nanobanana 折叠到末尾）
  needs_account?: boolean;
  // v6.9.1: 是否每请求需轮换代理（供前端展示能力说明）
  needs_proxy_per_request?: boolean;
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

// ── 模型目录（/v1/models，按 provider 分组；含生图模型 capability）──
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
