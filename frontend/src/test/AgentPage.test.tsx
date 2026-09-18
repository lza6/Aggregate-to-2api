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

  // P2-17/P2-15: run 终态 failed → 显示「重试」按钮；resume 404 降级重新 runDag；按钮为 button 语义
  it('run 失败显示重试按钮，点击降级重新提交 runDag（resume 404 兜底）', async () => {
    const failedRun = {
      ...runBody,
      status: 'failed',
      error_summary: '节点 n1 执行超时',
      nodes: planBody.nodes.map(n => ({ ...n, status: 'failed', error: 'boom' })),
    };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/plan')) return new Response(JSON.stringify(planBody), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/resume')) return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'DAG 续跑未启用（IF_DAG_RESUME_ENABLED=0）' } }), { status: 404, headers: { 'content-type': 'application/json' } });
      if (u.includes('/run')) return new Response(JSON.stringify({ ...runBody, run_id: 'r-2' }), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag/r-2')) return new Response(JSON.stringify(failedRun), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag/r-1')) return new Response(JSON.stringify(failedRun), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag?')) return new Response(JSON.stringify(emptyList), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag')) return new Response(JSON.stringify(oneList), { status: 200, headers: { 'content-type': 'application/json' } });
      return new Response('{}', { status: 404 });
    });
    render(<AgentPage />);
    fireEvent.change(screen.getByLabelText('任务描述'), { target: { value: '画一只猫并终检' } });
    fireEvent.click(screen.getByText('生成计划'));
    await waitFor(() => expect(screen.getByText(/计划预览/)).toBeTruthy());
    fireEvent.click(screen.getByText('提交执行'));
    // 失败终态 → 重试按钮（原生 button 语义）出现
    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument(), { timeout: 8000 });
    const retryBtn = screen.getByRole('button', { name: '重试' });
    expect(retryBtn.tagName).toBe('BUTTON');
    expect(screen.getByText(/run 异常|节点 n1 执行超时/)).toBeTruthy();
    // 点击重试：resume 404 → 降级重新 runDag（r-2）
    fireEvent.click(retryBtn);
    await waitFor(() => expect(notifySpy).toHaveBeenCalledWith(expect.stringContaining('已重新提交 DAG（r-2）'), 'success'));
  });

  // P2-17/P2-15: resume 开启成功时走续跑路径（不降级）
  it('run 失败且后端 resume 开启 → 点击重试走续跑（复用 run_id）', async () => {
    const failedRun = { ...runBody, status: 'failed', error_summary: 'boom' };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/plan')) return new Response(JSON.stringify(planBody), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/resume')) return new Response(JSON.stringify({ run_id: 'r-1', status: 'running', resumed: true }), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/run')) return new Response(JSON.stringify(runBody), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag?')) return new Response(JSON.stringify(emptyList), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag')) return new Response(JSON.stringify(failedRun), { status: 200, headers: { 'content-type': 'application/json' } });
      return new Response('{}', { status: 404 });
    });
    render(<AgentPage />);
    fireEvent.change(screen.getByLabelText('任务描述'), { target: { value: '画一只猫并终检' } });
    fireEvent.click(screen.getByText('生成计划'));
    await waitFor(() => expect(screen.getByText(/计划预览/)).toBeTruthy());
    fireEvent.click(screen.getByText('提交执行'));
    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await waitFor(() => expect(notifySpy).toHaveBeenCalledWith(expect.stringContaining('已续跑 DAG（r-1）'), 'success'));
  });

  // P1-11: DAG 终态触发的桌面系统通知在非 Tauri 环境（jsdom）必须静默降级，不抛错、不影响主流程
  it('run 成功终态：桌面通知动态 import 在浏览器环境静默降级（无 unhandled rejection）', async () => {
    const unhandled: unknown[] = [];
    const onRej = (e: PromiseRejectionEvent) => unhandled.push(e.reason);
    window.addEventListener('unhandledrejection', onRej);
    mockFetch(['pending', 'done']);
    render(<AgentPage />);
    fireEvent.change(screen.getByLabelText('任务描述'), { target: { value: '画一只猫' } });
    fireEvent.click(screen.getByText('生成计划'));
    await waitFor(() => expect(screen.getByText(/计划预览/)).toBeTruthy());
    fireEvent.click(screen.getByText('提交执行'));
    // 轮询推进到 succeeded 终态
    await waitFor(() => expect(screen.getByText(/r-1/)).toBeTruthy(), { timeout: 3000 });
    // 终态渲染后给 effect 异步降级留时间（动态 import 失败已 try/catch 吞掉）
    await new Promise(r => setTimeout(r, 300));
    window.removeEventListener('unhandledrejection', onRej);
    expect(unhandled.length).toBe(0);
  });
  // B2/P0-1: 我的技能区块（approved 空态 + 成功 run 展开显示「保存为技能」）
  it('技能区块：空态显示「暂无已批准技能」，成功 run 展开后可保存为技能', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: unknown) => {
      const u = String(url);
      if (u.includes('save-from-run')) return new Response(JSON.stringify({ ok: true, skill: { id: 's-new', name: 'my-skill', status: 'draft' } }), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('my-skills')) return new Response(JSON.stringify({ ok: true, count: 0, items: [] }), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag?')) return new Response(JSON.stringify(oneList), { status: 200, headers: { 'content-type': 'application/json' } });
      if (u.includes('/dag')) return new Response(JSON.stringify(oneList), { status: 200, headers: { 'content-type': 'application/json' } });
      return new Response('{}', { status: 404 });
    });
    render(<AgentPage />);
    // 我的技能空态
    await waitFor(() => expect(screen.getByText('我的技能')).toBeTruthy());
    await waitFor(() => expect(screen.getByText(/暂无已批准技能/)).toBeTruthy());
    // 历史列表成功 run → 展开 → 保存为技能按钮
    await waitFor(() => expect(screen.getByText('t')).toBeTruthy());
    fireEvent.click(screen.getByText('t'));
    await waitFor(() => expect(screen.getByText('保存为技能')).toBeTruthy());
    fireEvent.click(screen.getByText('保存为技能'));
    await waitFor(() => expect(notifySpy).toHaveBeenCalledWith(expect.stringContaining('已保存技能草稿'), 'success'));
    const saveCall = vi.mocked(globalThis.fetch).mock.calls.find(c => String(c[0]).includes('save-from-run'));
    expect(saveCall).toBeTruthy();
  });
});
