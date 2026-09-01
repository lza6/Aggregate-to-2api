import { describe, it, expect, beforeEach, vi } from 'vitest';
// 直接引用源模块；adminHeaders 未导出，通过 getStoredAdminKey/setStoredAdminKey 间接覆盖其分支。
import {
  getStoredAdminKey,
  setStoredAdminKey,
  getStoredApiKey,
  setStoredApiKey,
} from '../api';

// ── 鉴权 / storage 纯逻辑 ──────────────────────────────────────────
// adminHeaders() 内部调用 getStoredAdminKey()；getStoredAdminKey 直接读写 localStorage。
// 我们通过 localStorage mock 覆盖「有 Key / 无 Key / 抛异常」三条分支。

describe('admin 鉴权 storage（getStoredAdminKey/setStoredAdminKey）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('无 Key 时 getStoredAdminKey 返回空串（adminHeaders 不附带 Authorization）', () => {
    expect(getStoredAdminKey()).toBe('');
  });

  it('setStoredAdminKey 保存 trim 后的值，getStoredAdminKey 取回', () => {
    setStoredAdminKey('  sk-admin-abc  ');
    expect(getStoredAdminKey()).toBe('sk-admin-abc');
    expect(localStorage.getItem('imagefreeAdminApiKey')).toBe('sk-admin-abc');
  });

  it('setStoredAdminKey 传空串/纯空白 → 移除条目（getStoredAdminKey 返回空）', () => {
    setStoredAdminKey('sk-admin-abc');
    expect(getStoredAdminKey()).toBe('sk-admin-abc');
    setStoredAdminKey('   ');
    expect(getStoredAdminKey()).toBe('');
    expect(localStorage.getItem('imagefreeAdminApiKey')).toBeNull();
  });

  it('localStorage 抛异常时 getStoredAdminKey 返回空串（不向上抛）', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    expect(getStoredAdminKey()).toBe('');
    spy.mockRestore();
  });

  it('localStorage.setItem 抛异常时 setStoredAdminKey 不向上抛', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    expect(() => setStoredAdminKey('sk-admin-abc')).not.toThrow();
    spy.mockRestore();
  });
});

describe('chat API Key storage（getStoredApiKey/setStoredApiKey）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('无 Key 时 getStoredApiKey 返回空串', () => {
    expect(getStoredApiKey()).toBe('');
  });

  it('保存与取回 trim 后的值', () => {
    setStoredApiKey('\tsk-chat-key\n');
    expect(getStoredApiKey()).toBe('sk-chat-key');
    expect(localStorage.getItem('imagefreeChatApiKey')).toBe('sk-chat-key');
  });

  it('传空串 → 移除条目', () => {
    setStoredApiKey('sk-chat-key');
    setStoredApiKey('');
    expect(getStoredApiKey()).toBe('');
    expect(localStorage.getItem('imagefreeChatApiKey')).toBeNull();
  });

  it('localStorage 抛异常时 get/set 均不向上抛', () => {
    const getSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('disabled');
    });
    expect(getStoredApiKey()).toBe('');
    getSpy.mockRestore();

    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('disabled');
    });
    expect(() => setStoredApiKey('sk-chat-key')).not.toThrow();
    setSpy.mockRestore();
  });
});

// ── fetch 包装函数：参数拼装 + 错误分支 ──────────────────────────────
// 覆盖 blockIp / unblockIp / fetchBlocklist / fetchBlockStatus / retryDLQTask / clearDLQ
// / generateImage / fetchTask / fetchEditTask 等的错误分支（res.ok=false 抛 Error 且文案含 HTTP 状态）
// 与成功分支（返回 res.json()）。adminHeaders 鉴权头通过 mock fetch 断言 Authorization 落点。

import {
  blockIp,
  unblockIp,
  fetchBlocklist,
  fetchBlockStatus,
  retryDLQTask,
  clearDLQ,
  generateImage,
  editImage,
  fetchTask,
  fetchEditTask,
  fetchGallery,
  fetchStats,
  fetchTasks,
  fetchProviders,
  fetchLogs,
  fetchDLQ,
  fetchDiagnostics,
  fetchAccountPool,
  fetchRoutingRecords,
  fetchProxyPool,
  fetchSystemSpec,
  fetchChatUsage,
  fetchChatRemaining,
  fetchChatAuthStatus,
  fetchChatModels,
  fetchImageModels,
  chatCompletions,
  signGallery,
  apiFetch,
  ApiError,
} from '../api';

function mockFetch(impl: typeof globalThis.fetch) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(impl);
}

function jsonRes(body: unknown, init?: { ok?: boolean; status?: number; text?: string }): Response {
  const ok = init?.ok ?? true;
  const status = init?.status ?? 200;
  const text = init?.text ?? '';
  // 构造最小 Response：res.ok 由 status 决定；res.json/text 返回预设值。
  const headers = new Headers({ 'content-type': 'application/json' });
  const payload = text ? text : JSON.stringify(body);
  const res = new Response(payload, { status, headers });
  // Response 构造器已按 status 设置 ok；如需覆盖 text 走 catch 分支，保留原样。
  void ok;
  return res;
}

describe('admin 写操作鉴权头落点（adminHeaders）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('无管理 Key 时 fetchBlocklist 不携带 Authorization', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    await fetchBlocklist();
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({});
    spy.mockRestore();
  });

  it('有管理 Key 时 fetchBlocklist 携带 Authorization: Bearer <key>', async () => {
    setStoredAdminKey('sk-admin-xyz');
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    await fetchBlocklist();
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({ Authorization: 'Bearer sk-admin-xyz' });
    spy.mockRestore();
  });

  it('blockIp 同时携带 Content-Type 与 Authorization', async () => {
    setStoredAdminKey('sk-admin-xyz');
    const spy = mockFetch(async () => jsonRes({ ok: true, record: { ip: '1.2.3.4', block_type: 'block' } }));
    await blockIp({ ip: '1.2.3.4' });
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer sk-admin-xyz',
    });
    spy.mockRestore();
  });

  it('unblockIp 走 DELETE 且携带 Authorization（含 IP URL 编码）', async () => {
    setStoredAdminKey('sk-admin-xyz');
    const spy = mockFetch(async () => jsonRes({ ok: true, removed: true }));
    await unblockIp('1.2.3.4/32');
    const [url, init] = spy.mock.calls[0];
    expect(init?.method).toBe('DELETE');
    expect(String(url)).toContain('1.2.3.4%2F32');
    expect(init?.headers).toEqual({ Authorization: 'Bearer sk-admin-xyz' });
    spy.mockRestore();
  });

  it('retryDLQTask 走 POST 且携带 Authorization', async () => {
    setStoredAdminKey('sk-admin-xyz');
    const spy = mockFetch(async () => jsonRes({ message: 'ok' }));
    await retryDLQTask('task-1');
    const [, init] = spy.mock.calls[0];
    expect(init?.method).toBe('POST');
    expect(init?.headers).toEqual({ Authorization: 'Bearer sk-admin-xyz' });
    spy.mockRestore();
  });

  it('clearDLQ 走 DELETE 且携带 Authorization', async () => {
    setStoredAdminKey('sk-admin-xyz');
    const spy = mockFetch(async () => jsonRes({ success: true }));
    await clearDLQ();
    const [, init] = spy.mock.calls[0];
    expect(init?.method).toBe('DELETE');
    expect(init?.headers).toEqual({ Authorization: 'Bearer sk-admin-xyz' });
    spy.mockRestore();
  });
});

// ── chat 鉴权头（authHeaders）：getStoredApiKey 驱动 ───────────────
describe('chat 鉴权头落点（authHeaders）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('无 API Key 时 generateImage 不携带 Authorization', async () => {
    const spy = mockFetch(async () => jsonRes({ id: 't1', status: 'queued', prompt: 'x', image_url: null, error: null, duration_sec: null, created_at: 0, model: 'm' }));
    await generateImage({ prompt: 'x' });
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
    spy.mockRestore();
  });

  it('有 API Key 时 generateImage 携带 Authorization', async () => {
    setStoredApiKey('sk-chat-key');
    const spy = mockFetch(async () => jsonRes({ id: 't1', status: 'queued', prompt: 'x', image_url: null, error: null, duration_sec: null, created_at: 0, model: 'm' }));
    await generateImage({ prompt: 'x' });
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer sk-chat-key',
    });
    spy.mockRestore();
  });

  it('有 API Key 时 editImage 携带 Authorization', async () => {
    setStoredApiKey('sk-chat-key');
    const spy = mockFetch(async () => jsonRes({ id: 't1', status: 'queued', prompt: 'x', image_url: null, error: null, duration_sec: null, created_at: 0, model: 'm' }));
    await editImage({ prompt: 'x' });
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer sk-chat-key',
    });
    spy.mockRestore();
  });

  it('chatCompletions 携带 Authorization 与 Content-Type', async () => {
    setStoredApiKey('sk-chat-key');
    const spy = mockFetch(async () => jsonRes({}));
    await chatCompletions({ model: 'm' });
    const [, init] = spy.mock.calls[0];
    expect(init?.method).toBe('POST');
    expect(init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer sk-chat-key',
    });
    spy.mockRestore();
  });

  it('fetchChatAuthStatus 传 adminKey 时携带 Authorization', async () => {
    const spy = mockFetch(async () => jsonRes({ enabled: false, header: 'Authorization', alt_headers: [] }));
    await fetchChatAuthStatus({ adminKey: 'sk-admin' });
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({ Authorization: 'Bearer sk-admin' });
    spy.mockRestore();
  });

  it('fetchChatAuthStatus 不传 adminKey 时不携带 Authorization', async () => {
    const spy = mockFetch(async () => jsonRes({ enabled: false, header: 'Authorization', alt_headers: [] }));
    await fetchChatAuthStatus();
    const [, init] = spy.mock.calls[0];
    expect(init?.headers).toEqual({});
    spy.mockRestore();
  });
});

// ── admin 写操作错误分支（res.ok=false 抛 Error）────────────────────
describe('admin 写操作错误分支（res.ok=false 抛 Error）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('blockIp 失败 → 抛「封禁失败 HTTP <status>: <detail>」', async () => {
    const spy = mockFetch(async () => jsonRes('forbidden', { status: 403, text: 'forbidden' }));
    await expect(blockIp({ ip: '1.2.3.4' })).rejects.toThrow(/封禁失败 HTTP 403/);
    spy.mockRestore();
  });

  it('unblockIp 失败 → 抛「解封失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('nope', { status: 404, text: 'nope' }));
    await expect(unblockIp('1.2.3.4')).rejects.toThrow(/解封失败 HTTP 404/);
    spy.mockRestore();
  });

  it('fetchBlocklist 失败 → 抛「封禁列表获取失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 500, text: 'boom' }));
    await expect(fetchBlocklist()).rejects.toThrow(/封禁列表获取失败 HTTP 500/);
    spy.mockRestore();
  });

  it('fetchBlockStatus 失败 → 抛「封禁状态查询失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 500, text: 'boom' }));
    await expect(fetchBlockStatus('1.2.3.4')).rejects.toThrow(/封禁状态查询失败 HTTP 500/);
    spy.mockRestore();
  });

  it('retryDLQTask 失败 → 抛「重试失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 500, text: 'boom' }));
    await expect(retryDLQTask('task-1')).rejects.toThrow(/重试失败 HTTP 500/);
    spy.mockRestore();
  });

  it('clearDLQ 失败 → 抛「清空失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 500, text: 'boom' }));
    await expect(clearDLQ()).rejects.toThrow(/清空失败 HTTP 500/);
    spy.mockRestore();
  });

  it('generateImage 失败 → 抛「生成失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 401, text: 'Unauthorized' }));
    await expect(generateImage({ prompt: 'x' })).rejects.toThrow(/生成失败 HTTP 401/);
    spy.mockRestore();
  });

  it('editImage 失败 → 抛「图生图提交失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 500, text: 'boom' }));
    await expect(editImage({ prompt: 'x' })).rejects.toThrow(/图生图提交失败 HTTP 500/);
    spy.mockRestore();
  });

  it('fetchTask 失败 → 抛「任务查询失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 404, text: 'nf' }));
    await expect(fetchTask('task-1')).rejects.toThrow(/任务查询失败 HTTP 404/);
    spy.mockRestore();
  });

  it('fetchEditTask 失败 → 抛「图生图任务查询失败 HTTP <status>」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 404, text: 'nf' }));
    await expect(fetchEditTask('task-1')).rejects.toThrow(/图生图任务查询失败 HTTP 404/);
    spy.mockRestore();
  });

  it('错误分支 detail 超长时截断 200 字符（slice(0,200)）', async () => {
    // blockIp 的错误文案为「封禁失败 HTTP <status>: <detail.slice(0,200)>」
    const long = 'x'.repeat(500);
    const spy = mockFetch(async () => new Response(long, { status: 500, headers: { 'content-type': 'text/plain' } }));
    await expect(blockIp({ ip: '1.2.3.4' })).rejects.toThrow(/封禁失败 HTTP 500: x{200}/);
    spy.mockRestore();
  });
});

// ── admin 写操作成功分支（res.ok=true 返回 json）────────────────────
describe('admin 写操作成功分支（res.ok=true 返回 json）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('blockIp 成功 → 返回 { ok, record }', async () => {
    const spy = mockFetch(async () => jsonRes({ ok: true, record: { ip: '1.2.3.4', block_type: 'block' } }));
    const r = await blockIp({ ip: '1.2.3.4' });
    expect(r.ok).toBe(true);
    expect(r.record.ip).toBe('1.2.3.4');
    spy.mockRestore();
  });

  it('fetchBlockStatus 成功 → 返回 { ip, rule, blocked }', async () => {
    const spy = mockFetch(async () => jsonRes({ ip: '1.2.3.4', rule: null, blocked: false }));
    const r = await fetchBlockStatus('1.2.3.4');
    expect(r.blocked).toBe(false);
    spy.mockRestore();
  });

  it('retryDLQTask 成功 → 返回 json body', async () => {
    const spy = mockFetch(async () => jsonRes({ message: 'retried' }));
    const r = await retryDLQTask('task-1');
    expect(r.message).toBe('retried');
    spy.mockRestore();
  });

  it('clearDLQ 成功 → 返回 json body', async () => {
    const spy = mockFetch(async () => jsonRes({ success: true }));
    const r = await clearDLQ();
    expect(r.success).toBe(true);
    spy.mockRestore();
  });
});

// ── 只读 fetcher 参数拼装 + URL 构造 ─────────────────────────────────
describe('只读 fetcher 参数拼装', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('fetchGallery 带 password 时拼入 query', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    await fetchGallery(5, 'secret');
    const [url] = spy.mock.calls[0];
    const s = String(url);
    expect(s).toContain('limit=5');
    expect(s).toContain('password=secret');
    spy.mockRestore();
  });

  it('fetchGallery 无 password 时不含 password 参数', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    await fetchGallery(10);
    const s = String(spy.mock.calls[0][0]);
    expect(s).toContain('limit=10');
    expect(s).not.toContain('password');
    spy.mockRestore();
  });

  it('fetchTasks 带 limit/offset/status 时拼入 query', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], total: 0 }));
    await fetchTasks({ limit: 10, offset: 20, status: 'done' });
    const s = String(spy.mock.calls[0][0]);
    expect(s).toContain('limit=10');
    expect(s).toContain('offset=20');
    expect(s).toContain('status=done');
    spy.mockRestore();
  });

  it('fetchTasks 无参数时 query 为空（仅 ?）', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], total: 0 }));
    await fetchTasks();
    const s = String(spy.mock.calls[0][0]);
    expect(s).toMatch(/\/v1\/tasks\?$/);
    spy.mockRestore();
  });

  it('fetchAccountPool 带 page/pageSize/search 时拼入 query', async () => {
    const spy = mockFetch(async () => jsonRes({ accounts: {}, email_pool: { total_registered: 0, by_provider: {} }, items: [], items_total: 0, page: 1, page_size: 1, total_pages: 1 }));
    await fetchAccountPool({ page: 2, pageSize: 5, search: 'foo' });
    const s = String(spy.mock.calls[0][0]);
    expect(s).toContain('page=2');
    expect(s).toContain('page_size=5');
    expect(s).toContain('search=foo');
    spy.mockRestore();
  });

  it('fetchAccountPool search 仅空白时不拼入', async () => {
    const spy = mockFetch(async () => jsonRes({ accounts: {}, email_pool: { total_registered: 0, by_provider: {} }, items: [], items_total: 0, page: 1, page_size: 1, total_pages: 1 }));
    await fetchAccountPool({ search: '   ' });
    const s = String(spy.mock.calls[0][0]);
    expect(s).not.toContain('search');
    spy.mockRestore();
  });

  it('fetchProxyPool 带 page/pageSize 时拼入 query', async () => {
    const spy = mockFetch(async () => jsonRes({ total: 0, page: 1, page_size: 1, total_pages: 1, residential: 0, free: 0, available: 0, cooldown: 0, items: [], top: [] }));
    await fetchProxyPool({ page: 3, pageSize: 7 });
    const s = String(spy.mock.calls[0][0]);
    expect(s).toContain('page=3');
    expect(s).toContain('page_size=7');
    spy.mockRestore();
  });

  it('fetchChatUsage 带 period', async () => {
    const spy = mockFetch(async () => jsonRes({ period: '24h', total_calls: 0, ok_calls: 0, fail_calls: 0, prompt_tokens: 0, completion_tokens: 0, reasoning_tokens: 0, tool_calls: 0, avg_duration_ms: null, today_calls: 0, today_tokens: 0, by_model: [] }));
    await fetchChatUsage('7d');
    expect(String(spy.mock.calls[0][0])).toContain('period=7d');
    spy.mockRestore();
  });

  it('fetchLogs 带 lines', async () => {
    const spy = mockFetch(async () => jsonRes({ logs: [] }));
    await fetchLogs(200);
    expect(String(spy.mock.calls[0][0])).toContain('lines=200');
    spy.mockRestore();
  });

  it('fetchRoutingRecords 带 limit', async () => {
    const spy = mockFetch(async () => jsonRes({ records: [], nodes: {} }));
    await fetchRoutingRecords(10);
    expect(String(spy.mock.calls[0][0])).toContain('limit=10');
    spy.mockRestore();
  });

  it('fetchBlocklist 带 limit', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    await fetchBlocklist(50);
    expect(String(spy.mock.calls[0][0])).toContain('limit=50');
    spy.mockRestore();
  });
});

// ── 只读 fetcher 成功分支（返回 json）────────────────────────────────
describe('只读 fetcher 成功返回 json', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('fetchStats 返回 Stats', async () => {
    const body = { total_requests: 1, total_images: 0, total_errors: 0, processing: 0, queued: 0, queue_capacity: 10, workers: 1, uptime_human: '1s', daily: [], monthly: [], solver: { status: 'ok', solve_total: 0, solve_success_total: 0, solve_failure_total: 0, solve_avg_seconds: null, window_success_rate: null, window_solve_count: 0, window_avg_seconds: null, consecutive_failures: 0, circuit_open: false, failure_reasons: {}, rejected_total: 0, token_pools: {} } };
    const spy = mockFetch(async () => jsonRes(body));
    const r = await fetchStats();
    expect(r.total_requests).toBe(1);
    spy.mockRestore();
  });

  it('fetchProviders 返回 { items, count }', async () => {
    const spy = mockFetch(async () => jsonRes({ items: {}, count: 0 }));
    const r = await fetchProviders();
    expect(r.count).toBe(0);
    spy.mockRestore();
  });

  it('fetchLogs 返回 { logs }', async () => {
    const spy = mockFetch(async () => jsonRes({ logs: [{ ts: 1, level: 'INFO', logger: 'x', message: 'y' }] }));
    const r = await fetchLogs();
    expect(r.logs[0].level).toBe('INFO');
    spy.mockRestore();
  });

  it('fetchDLQ 返回 { items, count }', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    const r = await fetchDLQ();
    expect(r.count).toBe(0);
    spy.mockRestore();
  });

  it('fetchDiagnostics 返回 Diagnostics', async () => {
    const body = { status: 'ok', timestamp: 1, db: { size_mb: 1, wal_size_mb: 0, rows: 0 }, queue: { queued: 0, capacity: 10, admin: 0, high: 0, normal: 0, processing: 0 }, workers: { total: 1, alive: 1, stale_count: 0, stale_ids: [], detail: [] }, token_pools: {}, solver: { status: 'ok', circuit_open: false, window_success_rate: null, avg_solve_seconds: null }, slow_log: { count: 0, avg_total_ms: 0, max_total_ms: 0, slowest_stage: null }, disk: { free_gb: 1, total_gb: 10, used_percent: 10, log_dir_writable: true }, uptime_seconds: 1 };
    const spy = mockFetch(async () => jsonRes(body));
    const r = await fetchDiagnostics();
    expect(r.status).toBe('ok');
    spy.mockRestore();
  });

  it('fetchChatModels 返回 { items, count }', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], count: 0 }));
    const r = await fetchChatModels();
    expect(r.count).toBe(0);
    spy.mockRestore();
  });

  it('fetchImageModels 返回 { items, count }', async () => {
    const spy = mockFetch(async () => jsonRes({ items: {}, count: 0 }));
    const r = await fetchImageModels();
    expect(r.count).toBe(0);
    spy.mockRestore();
  });

  it('fetchChatRemaining 返回 ChatRemaining', async () => {
    const spy = mockFetch(async () => jsonRes({ available_proxies: 1, calls_per_proxy_per_hour: 10, hourly_limit: 100, used_last_hour: 0, remaining: 100 }));
    const r = await fetchChatRemaining();
    expect(r.remaining).toBe(100);
    spy.mockRestore();
  });

  it('fetchSystemSpec 返回 SystemSpec', async () => {
    const body = { cpu: { cores: 2, model: 'x' }, memory: { total_mb: 1024, total_gb: 1 }, disk: { total_gb: 10, used_gb: 1, free_gb: 9 }, adaptive: { workers: 1, upstream_inflight: 0, token_pool_size: 1, max_queue: 10 } };
    const spy = mockFetch(async () => jsonRes(body));
    const r = await fetchSystemSpec();
    expect(r.cpu.cores).toBe(2);
    spy.mockRestore();
  });
});

// ── generateImage 透传 signal ───────────────────────────────────────
describe('generateImage 透传 AbortSignal', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('传入 signal 时 fetch 收到同一 signal', async () => {
    const ctrl = new AbortController();
    const spy = mockFetch(async () => jsonRes({ id: 't1', status: 'queued', prompt: 'x', image_url: null, error: null, duration_sec: null, created_at: 0, model: 'm' }));
    await generateImage({ prompt: 'x' }, ctrl.signal);
    const [, init] = spy.mock.calls[0];
    expect(init?.signal).toBe(ctrl.signal);
    spy.mockRestore();
  });
});

// ── P1-4 统一错误处理中间件（apiFetch / ApiError）─────────────────────
describe('apiFetch 统一错误处理（P1-4）', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('200 JSON → 返回解析后数据', async () => {
    const spy = mockFetch(async () => jsonRes({ ok: 1 }));
    const r = await apiFetch<{ ok: number }>('/v1/stats');
    expect(r.ok).toBe(1);
    expect(spy.mock.calls[0][0]).toBe('/v1/stats');
    spy.mockRestore();
  });

  it('401 → 抛 ApiError 且 status=401、message 为中文可读', async () => {
    const spy = mockFetch(async () => jsonRes('denied', { status: 401, text: 'Unauthorized' }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    expect((err as ApiError).message).toMatch(/未授权/);
    spy.mockRestore();
  });

  it('403 → status=403、message 含「禁止访问」', async () => {
    const spy = mockFetch(async () => jsonRes('forbidden', { status: 403, text: 'forbidden' }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(403);
    expect((err as ApiError).message).toMatch(/禁止访问/);
    spy.mockRestore();
  });

  it('422 → status=422、message 含「参数校验失败」', async () => {
    const spy = mockFetch(async () => jsonRes('bad', { status: 422, text: 'bad request' }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).message).toMatch(/参数校验失败/);
    spy.mockRestore();
  });

  it('429 → status=429、message 含「过于频繁」', async () => {
    const spy = mockFetch(async () => jsonRes('rate', { status: 429, text: 'rate limited' }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(429);
    expect((err as ApiError).message).toMatch(/过于频繁/);
    spy.mockRestore();
  });

  it('500 → status=500、message 含「服务器内部错误」', async () => {
    const spy = mockFetch(async () => jsonRes('boom', { status: 500, text: 'boom' }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(500);
    expect((err as ApiError).message).toMatch(/服务器内部错误/);
    spy.mockRestore();
  });

  it('空 body / text 不可解析 → 兜底状态文案', async () => {
    const spy = mockFetch(async () => new Response('', { status: 503 }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(503);
    expect((err as ApiError).message).toMatch(/服务暂时不可用/);
    spy.mockRestore();
  });

  it('网络 reject → status=0、code=NETWORK_ERROR、message 含「网络错误」', async () => {
    const spy = mockFetch(async () => { throw new TypeError('Failed to fetch'); });
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).code).toBe('NETWORK_ERROR');
    expect((err as ApiError).message).toMatch(/网络错误/);
    spy.mockRestore();
  });

  it('超时 → status=0、code=TIMEOUT、message 含「超时」', async () => {
    vi.useFakeTimers();
    try {
      // fetch 永不 resolve；靠 apiFetch 内置超时中止（用极小超时加速测试）
      const spy = mockFetch(async (_u, init) => {
        return await new Promise<Response>((_res, reject) => {
          (init?.signal as AbortSignal | undefined)?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
      });
      const p = apiFetch('/v1/x', { timeoutMs: 50 });
      // 先挂接拒绝处理器，避免推进定时器瞬间产生未处理拒绝
      const errP = p.then(() => null, (e: unknown) => e);
      await vi.advanceTimersByTimeAsync(100);
      const err = await errP;
      expect((err as ApiError).status).toBe(0);
      expect((err as ApiError).code).toBe('TIMEOUT');
      expect((err as ApiError).message).toMatch(/超时/);
      spy.mockRestore();
    } finally {
      vi.useRealTimers();
    }
  });

  it('caller 前缀拼进错误消息（如「封禁失败 HTTP 403: <detail>」）', async () => {
    const spy = mockFetch(async () => jsonRes('nope', { status: 403, text: 'you shall not pass' }));
    const err = await apiFetch('/v1/admin/security/block-ip', { method: 'POST', caller: '封禁失败' })
      .catch((e: unknown) => e);
    expect((err as ApiError).message).toMatch(/封禁失败 HTTP 403/);
    expect((err as ApiError).message).toContain('you shall not pass');
    spy.mockRestore();
  });

  it('错误体含 code/error.code 时映射进 ApiError.code', async () => {
    const spy = mockFetch(async () => jsonRes({ code: 'RATE_LIMIT_EXCEEDED', message: 'limit hit' }, { status: 429 }));
    const err = await apiFetch('/v1/x').catch((e: unknown) => e);
    expect((err as ApiError).code).toBe('RATE_LIMIT_EXCEEDED');
    expect((err as ApiError).message).toContain('limit hit');
    spy.mockRestore();
  });

  it('signGallery 薄封装：成功返回 url/expires_in', async () => {
    const spy = mockFetch(async () => jsonRes({ url: 'https://x/y?sig=1', expires_in: 60 }));
    const r = await signGallery(20, 'sk-admin');
    expect(r.url).toBe('https://x/y?sig=1');
    expect(r.expires_in).toBe(60);
    const [url, init] = spy.mock.calls[0];
    const s = String(url);
    expect(s).toContain('/v1/gallery/sign?');
    expect(s).toContain('limit=20');
    expect((init?.headers as Record<string, string>)?.Authorization).toBe('Bearer sk-admin');
    spy.mockRestore();
  });

  it('signGallery 非 2xx → 抛 ApiError（不再抛普通对象），status 保留', async () => {
    const spy = mockFetch(async () => jsonRes('no', { status: 403, text: 'forbidden' }));
    const err = await signGallery(5, 'sk').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(403);
    spy.mockRestore();
  });

  it('fetchTasks 薄封装请求路径拼接正确', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [], total: 0 }));
    await fetchTasks({ limit: 10, offset: 20, status: 'done' });
    expect(String(spy.mock.calls[0][0])).toContain('limit=10');
    expect(String(spy.mock.calls[0][0])).toContain('offset=20');
    expect(String(spy.mock.calls[0][0])).toContain('status=done');
    spy.mockRestore();
  });

  it('外部 signal 透传：generateImage 请求带同一 signal（不自造新 controller）', async () => {
    const ctrl = new AbortController();
    const spy = mockFetch(async () => jsonRes({ id: 't1', status: 'queued', prompt: 'x', image_url: null, error: null, duration_sec: null, created_at: 0, model: 'm' }));
    await generateImage({ prompt: 'x' }, ctrl.signal);
    const [, init] = spy.mock.calls[0];
    expect(init?.signal).toBe(ctrl.signal);
    spy.mockRestore();
  });
});

// ── notify / onToast：全局 Toast 通知 ───────────────────────────────
import { notify, onToast } from '../api';

describe('Toast 通知（notify/onToast）', () => {
  it('notify 触发所有订阅者，type 默认 info', () => {
    const received: unknown[] = [];
    const unsub = onToast((t) => received.push(t));
    notify('hello');
    notify('boom', 'error');
    expect(received).toHaveLength(2);
    expect(received[0]).toMatchObject({ message: 'hello', type: 'info' });
    expect(received[1]).toMatchObject({ message: 'boom', type: 'error' });
    unsub();
  });

  it('onToast 返回的反订阅函数移除监听', () => {
    const received: unknown[] = [];
    const unsub = onToast((t) => received.push(t));
    unsub();
    notify('after-unsub');
    expect(received).toHaveLength(0);
  });

  it('多个监听者均被通知', () => {
    let a = 0, b = 0;
    const u1 = onToast(() => a++);
    const u2 = onToast(() => b++);
    notify('x');
    expect(a).toBe(1);
    expect(b).toBe(1);
    u1();
    u2();
  });
});
