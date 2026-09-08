// v10.0.0：agent api 域封装测试（纯函数级：URL/方法/body 契约 + 错误透传）。
import { describe, it, expect, vi, afterEach } from 'vitest';
import { runDag, planDag, listDagRuns, getDagRun } from '../api/agent';

const base = globalThis as unknown as { fetchMock?: ReturnType<typeof vi.fn> };

function ok(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
}
function err(status: number, message: string) {
  return new Response(JSON.stringify({ error: { code: 'X', message } }), { status, headers: { 'content-type': 'application/json' } });
}

afterEach(() => vi.restoreAllMocks());

describe('agent api 封装', () => {
  it('runDag POST 到 /v1/agent/dag/run，body 含 name/nodes', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ run_id: 'r1', status: 'pending' }));
    const res = await runDag({ name: 't', nodes: [{ id: 'A', kind: 'llm' }] });
    expect(res.run_id).toBe('r1');
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/v1/agent/dag/run');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({ name: 't', nodes: [{ id: 'A', kind: 'llm' }] });
  });

  it('planDag POST 到 /v1/agent/dag/plan，scene 透传', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ nodes: [], meta: { valid: true } }));
    await planDag('画猫', 'image');
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({ prompt: '画猫', scene: 'image' });
  });

  it('getDagRun 编码 run_id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ run_id: 'r/1', status: 'succeeded', nodes: [] }));
    await getDagRun('r/1');
    const [url] = vi.mocked(globalThis.fetch).mock.calls[0] as unknown as [string];
    expect(url).toBe('/v1/agent/dag/r%2F1');
  });

  it('listDagRuns 带 limit/status query', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ items: [], count: 0 }));
    await listDagRuns({ limit: 5, status: 'succeeded' });
    const [url] = vi.mocked(globalThis.fetch).mock.calls[0] as unknown as [string];
    expect(url).toContain('limit=5');
    expect(url).toContain('status=succeeded');
  });

  it('HTTP 错误抛 ApiError（message 含中文 detail）', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(err(422, '节点数超过上限 50'));
    await expect(planDag('x')).rejects.toThrow(/节点数超过上限|DAG/);
  });
});
