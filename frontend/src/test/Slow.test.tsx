import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SlowPage } from '../pages/Slow';

// ── /v1/slow 确定 JSON（对照 api/routes/admin.py L573-602 响应形状）──
const slowResponse = {
  threshold_ms: 5000,
  enabled: true,
  stats: { count: 2, avg_total_ms: 8243.5, max_total_ms: 10340.2, slowest_stage: 'upstream' },
  count: 2,
  items: [
    {
      task_id: 'task_abc123', model: 'gpt-4o', provider: 'nanobanana',
      queue_ms: 1200.5, wait_token_ms: 300.2, solve_ms: 1500.8, upstream_ms: 6200.4,
      retry_ms: 1001.2, total_ms: 10340.2, slowest_stage: 'upstream', status: 'completed',
      trace_id: 'trace_1', submit_ms: 800.1, poll_ms: 5400.2, created_at: 1730000000,
    },
    {
      task_id: 'task_def456', model: 'dall-e-3', provider: 'imagefree',
      queue_ms: 500.0, wait_token_ms: 200.0, solve_ms: 3000.0, upstream_ms: 2000.0,
      retry_ms: 0, total_ms: 6100.4, slowest_stage: 'solve', status: 'completed',
      trace_id: 'trace_2', submit_ms: 300.0, poll_ms: 1700.0, created_at: 1730000060,
    },
  ],
};

function renderSlow() {
  return render(
    <MemoryRouter initialEntries={['/slow']}>
      <Routes>
        <Route path="/slow" element={<SlowPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SlowPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => slowResponse,
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('mock /v1/slow 返回确定 JSON，加载后渲染阶段画像各段的关键字段', async () => {
    renderSlow();

    // loading 骨架屏（4 个 Skeleton 复用同一 aria-label）
    expect(screen.getAllByLabelText('正在加载内容').length).toBe(4);

    // 分段时间画像表头
    await waitFor(() =>
      expect(screen.getByText('分段时间画像')).toBeInTheDocument(),
    );

    // 各阶段名（阶段画像表 + 明细表 badge 均可能出现，用 getAllByText）
    expect(screen.getAllByText('排队').length).toBeGreaterThan(0);
    expect(screen.getAllByText('等待 Token').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CF 求解').length).toBeGreaterThan(0);
    expect(screen.getAllByText('上游调用').length).toBeGreaterThan(0);
    expect(screen.getAllByText('重试累计').length).toBeGreaterThan(0);
    expect(screen.getAllByText('提交首字节').length).toBeGreaterThan(0);
    expect(screen.getAllByText('轮询完成').length).toBeGreaterThan(0);

    // 总体速览关键字段
    expect(screen.getByText('窗口内慢请求')).toBeInTheDocument();
    expect(screen.getByText('平均总耗时')).toBeInTheDocument();
    expect(screen.getByText('最慢总耗时')).toBeInTheDocument();
    expect(screen.getByText('最慢阶段')).toBeInTheDocument();
  });

  it('最近慢请求明细表渲染样本关键字段（任务ID/模型/总耗时/慢阶段/状态）', async () => {
    renderSlow();
    await waitFor(() => expect(screen.getByText('最近慢请求明细')).toBeInTheDocument());

    expect(screen.getByText('task_abc')).toBeInTheDocument(); // task_abc123 前 8 字符
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('nanobanana')).toBeInTheDocument();
    expect(screen.getAllByText('10.34s').length).toBeGreaterThan(0); // 10340.2ms → s（max 卡 + 明细行均可出现）
    expect(screen.getByText('dall-e-3')).toBeInTheDocument();

    // 慢阶段 badge
    expect(screen.getAllByText('上游调用').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CF 求解').length).toBeGreaterThan(0);
  });

  it('fetch 失败 → 渲染 ErrorRetry 错误态，点击重试触发重拉', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 500, text: async () => 'server boom' })
      .mockResolvedValueOnce({ ok: true, json: async () => slowResponse });
    vi.stubGlobal('fetch', fetchMock);

    renderSlow();
    await waitFor(() => expect(screen.getByText(/慢日志获取失败/)).toBeInTheDocument());

    // 错误态渲染「重新请求」按钮
    const retryBtn = screen.getByRole('button', { name: /重新请求/ });
    expect(retryBtn).toBeInTheDocument();

    retryBtn.click();
    await waitFor(() => expect(screen.getByText('分段时间画像')).toBeInTheDocument());
    expect(fetchMock.mock.calls.length).toBe(2);
  });

  it('enabled=false 时渲染「已禁用」徽标', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...slowResponse, enabled: false }),
    }));
    renderSlow();
    await waitFor(() => expect(screen.getByText('已禁用')).toBeInTheDocument());
  });
});
