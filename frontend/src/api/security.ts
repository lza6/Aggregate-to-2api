// P3 剩余风险治理：api.ts 拆分 —— security 域（封禁/解封/列表/状态，均需管理 Key）。
import { apiFetch, adminHeaders } from './core';

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
