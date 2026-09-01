import { describe, it, expect, vi } from 'vitest';
// 复用 api.test.ts 的 mock 模式验证 fetchEmailSources 参数拼装与返回解析。
import { fetchEmailSources } from '../api';

function mockFetch(impl: typeof globalThis.fetch) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(impl);
}

function jsonRes(body: unknown): Response {
  const headers = new Headers({ 'content-type': 'application/json' });
  return new Response(JSON.stringify(body), { status: 200, headers });
}

describe('fetchEmailSources v6.9.1 邮箱池上游端点', () => {
  it('请求 /v1/email-sources 且返回 { items, count }', async () => {
    const spy = mockFetch(async () => jsonRes({
      items: [
        { name: 'mail.tm', base_url: 'https://mail.tm', priority: 80, available: true, success_count: 5, failure_count: 0, last_error: null },
        { name: 'custom-imap', base_url: null, priority: 0, available: false, success_count: 0, failure_count: 0, last_error: null },
      ],
      count: 2,
    }));
    const r = await fetchEmailSources();
    expect(String(spy.mock.calls[0][0])).toBe('/v1/email-sources');
    expect(r.count).toBe(2);
    expect(r.items[0].name).toBe('mail.tm');
    expect(r.items[1].base_url).toBeNull();
    spy.mockRestore();
  });

  it('base_url 为 null（custom-imap 无官网）时不报错', async () => {
    const spy = mockFetch(async () => jsonRes({ items: [{ name: 'custom-imap', base_url: null, priority: 0, available: false, success_count: 0, failure_count: 0, last_error: null }], count: 1 }));
    const r = await fetchEmailSources();
    expect(r.items[0].base_url).toBeNull();
    spy.mockRestore();
  });
});
