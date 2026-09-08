// v10.0.0：Agent 页交互测试（规划 → 提交 → 轮询 → 节点着色 → 历史）。
// 用真实组件渲染 + fetch mock（不渲染轮询 hook 深层，聚焦用户路径）。
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AgentPage } from '../pages/Agent';
import * as coreApi from '../api/core';

// Toast 由全局 ToastHost 渲染，测试环境未挂——spy notify 断言提示（不依赖 DOM Toast）。
// 注意：afterEach restoreAllMocks 会移除 spy，故 beforeEach 重建（避免 stale spy 引用）。
let notifySpy: ReturnType<typeof vi.spyOn>;

const planBody = {
  nodes: [
    { id: 'scene', kind: 'scene', status: 'pending', depends_on: [], prompt: '识别场景', model: null, result: null, error: null, attempt: 0, duration_ms: 0, created_at: 1, started_at: null, finished_at: null },
    { id: 'n1', kind: 'llm', status: 'pending', depends_on: ['scene'], prompt: '生成', model: null, result: null, error: null, attempt: 0, duration_ms: 0, created_at: 1, started_at: null, finished_at: null },
  ],
  meta: { scene: 'image', mock: true, llm_used: false, model: '', valid: true },
};
const runBody = { run_id: 'r-1', status: 'pending', name: 't', fail_fast: true, max_parallel: 4, error_summary: null, created_at: 1, finished_at: null, nodes: planBody.nodes };
const doneRun = { ...runBody, status: 'succeeded', nodes: planBody.nodes.map(n => ({ ...n, status: 'succeeded', result: 'ok' })) };
const emptyList = { items: [], count: 0 };
const oneList = { items: [doneRun], count: 1 };

function mockFetch(seq: (string | null)[] = []) {
  let i = 0;
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: unknown) => {
    const u = String(url);
    const hit = () => { const v = seq[i++ % seq.length]; return v; };
    if (u.includes('/plan')) return new Response(JSON.stringify(planBody), { status: 200, headers: { 'content-type': 'application/json' } });
    if (u.includes('/run')) return new Response(JSON.stringify(runBody), { status: 200, headers: { 'content-type': 'application/json' } });
    if (u.includes('/dag/r-1')) return new Response(JSON.stringify(hit() === 'done' ? doneRun : runBody), { status: 200, headers: { 'content-type': 'application/json' } });
    if (u.includes('/dag?')) return new Response(JSON.stringify(emptyList), { status: 200, headers: { 'content-type': 'application/json' } });
    if (u.includes('/dag')) return new Response(JSON.stringify(oneList), { status: 200, headers: { 'content-type': 'application/json' } });
    return new Response('{}', { status: 404 });
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  notifySpy = vi.spyOn(coreApi, 'notify').mockImplementation(() => {});
});
afterEach(() => { vi.restoreAllMocks(); });

describe('AgentPage 用户路径', () => {
  it('空输入点「生成计划」给错误提示（不静默）', async () => {
    mockFetch();
    render(<AgentPage />);
    notifySpy.mockClear();
    fireEvent.click(screen.getByText('生成计划'));
    await waitFor(() => expect(notifySpy).toHaveBeenCalledWith('请先输入任务描述', 'error'));
  });

  it('输入 → 生成计划 → 展示节点预览 → 提交执行 → 显示 run 轮询', async () => {
    mockFetch(['pending', 'done']);
    render(<AgentPage />);
    fireEvent.change(screen.getByLabelText('任务描述'), { target: { value: '画一只猫并终检' } });
    fireEvent.click(screen.getByText('生成计划'));
    await waitFor(() => expect(screen.getByText(/计划预览/)).toBeTruthy());
    fireEvent.click(screen.getByText('提交执行'));
    await waitFor(() => expect(screen.getByText(/r-1/)).toBeTruthy());
  });

  it('历史为空展示空态提示', async () => {
    mockFetch();
    render(<AgentPage />);
    await waitFor(() => expect(screen.getByText('还没有 DAG 运行记录')).toBeTruthy());
  });
});
