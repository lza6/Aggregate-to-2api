// P2-16/P2-15: 成本仪表「按 provider / 按 model」视角切换 + 导出 CSV（Blob 下载）。
// 风格对齐现有 test/ 目录（vitest + @testing-library/react，见 AgentPage.test.tsx）。
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CostsPage } from '../pages/Costs';

// recharts ResponsiveContainer 依赖 ResizeObserver（jsdom 无）——模块级桩掉，避免挂载即崩
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// jsdom 的 URL 无 createObjectURL/revokeObjectURL —— 注入并捕获组件生成的 Blob 引用
const capturedBlobs: Blob[] = [];
Object.defineProperty(URL, 'createObjectURL', {
  value: (b: Blob) => {
    capturedBlobs.push(b);
    return 'blob:test';
  },
  configurable: true,
});
Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true });

const costBody = {
  month_to_date_usd: 12.34,
  today_usd: 1.01,
  budget_usd: 100,
  budget_remaining_pct: 87.6,
  over_budget: false,
  burn_rate_warning: false,
  monthly: [{ month: '2026-08', cost_usd: 5.5, calls: 3 }],
  by_provider: [
    { provider: 'openai', calls: 2, cost_usd: 4.5, tokens: 100, credits_used: 10, images: 1 },
    { provider: 'aifreeforever', calls: 1, cost_usd: 7.84, tokens: 0, credits_used: 8, images: 2 },
  ],
  by_model: [
    { provider: 'openai', model: 'gpt-4o-mini', cost_usd: 4.5, calls: 2 },
    { provider: 'aifreeforever', model: 'flux-1.1-pro', cost_usd: 7.84, calls: 1 },
  ],
  image_cost_usd_mtd: 7.84,
  note: '口径说明',
};
const forecastBody = { daily_avg_30d: 0.4, projected_exceed_date: null, days_remaining: 18, budget_usd: 100, current_spent_30d: 12.34, disabled: false, note: '预测' };

function mockFetch() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.includes('/cost-forecast')) {
      return new Response(JSON.stringify(forecastBody), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    return new Response(JSON.stringify(costBody), { status: 200, headers: { 'content-type': 'application/json' } });
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  capturedBlobs.length = 0;
});

describe('CostsPage 成本视角切换', () => {
  it('默认按提供商展示 provider 表格，空态文案正确', async () => {
    mockFetch();
    render(<CostsPage />);
    await waitFor(() => expect(screen.getByText('openai')).toBeTruthy());
    expect(screen.getByText('按提供商成本')).toBeTruthy();
    expect(screen.queryByText('按模型成本')).toBeNull();
  });

  it('点击「按模型」切换到 model 表格（provider+model 列），aria-pressed 同步', async () => {
    mockFetch();
    render(<CostsPage />);
    await waitFor(() => expect(screen.getByText('openai')).toBeTruthy());
    const modelBtn = screen.getByRole('button', { name: '按模型' });
    expect(modelBtn.tagName).toBe('BUTTON');
    expect(modelBtn).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(modelBtn);
    await waitFor(() => expect(screen.getByText('按模型成本')).toBeTruthy());
    expect(screen.getByText('gpt-4o-mini')).toBeTruthy();
    expect(screen.getByText('flux-1.1-pro')).toBeTruthy();
    expect(modelBtn).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '按提供商' })).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('CostsPage 导出 CSV', () => {
  it('点击导出生成 Blob 下载（含 UTF-8 BOM + 维度列 + 全部行）', async () => {
    mockFetch();
    render(<CostsPage />);
    await waitFor(() => expect(screen.getByText('openai')).toBeTruthy());
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    fireEvent.click(screen.getByRole('button', { name: /导出 CSV/ }));
    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(capturedBlobs.length).toBeGreaterThan(0);
    const text = await capturedBlobs[capturedBlobs.length - 1].text();
    // BOM 由组件在字符串前拼接 U+FEFF；Blob.text() 的 UTF-8 解码会剥离 BOM，此处改用字节级断言
    const bytes = new Uint8Array(await capturedBlobs[capturedBlobs.length - 1].arrayBuffer());
    expect(bytes[0]).toBe(0xef);
    expect(bytes[1]).toBe(0xbb);
    expect(bytes[2]).toBe(0xbf);
    expect(text).toContain('维度');
    expect(text).toContain('openai');
    expect(text).toContain('aifreeforever/flux-1.1-pro');
    expect(text).toContain('gpt-4o-mini');
  });

  it('无成本数据时导出按钮 disabled', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      new Response(JSON.stringify({ ...costBody, by_provider: [], by_model: [] }), { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    render(<CostsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: /导出 CSV/ })).toBeDisabled());
  });
});
