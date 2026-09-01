import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { reportFrontendError } from '../lib/telemetry';

// Mock 遥测上报：避免真实 fetch/sendBeacon，并便于断言 componentDidCatch 调用。
vi.mock('../lib/telemetry', () => ({
  reportFrontendError: vi.fn(),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

beforeEach(() => {
  // vi.mock 生成的 reportFrontendError 是跨用例共享的 mock，需清空调用记录
  vi.clearAllMocks();
});

/** 故意抛错的子组件；可用 module 级开关控制是否抛错（便于测「重试后不再抛」）。
 * 这里用受控 props：shouldThrow=true 抛错；false 渲染正常内容。 */
function Bomb({ shouldThrow, text = '正常渲染内容' }: { shouldThrow: boolean; text?: string }) {
  if (shouldThrow) throw new Error('Boom! 渲染阶段异常');
  return <div>{text}</div>;
}

function renderWithRouter(ui: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={ui} />
        <Route path="/providers" element={<div>总览页</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ErrorBoundary', () => {
  it('子组件抛出渲染期异常时，渲染内置 fallback 而非崩溃', () => {
    // React 会在测试环境把边界错误打印到 console.error —— 静默掉避免测试噪声。
    const spy = vi.spyOn(console, 'error').mockImplementation(() => { /* noop */ });
    renderWithRouter(<ErrorBoundary><Bomb shouldThrow /></ErrorBoundary>);
    expect(screen.getByText('页面渲染异常')).toBeInTheDocument();
    expect(screen.getByText(/Boom! 渲染阶段异常/)).toBeInTheDocument();
    // 边界兜底，不卸载整棵树
    expect(screen.getByRole('alert')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('fallback 渲染「重试」按钮，且点击后触发 onReset 重新渲染 children', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => { /* noop */ });
    let shouldThrow = true;
    const { rerender } = renderWithRouter(
      <ErrorBoundary>{shouldThrow ? <Bomb shouldThrow /> : <div>修复后的内容</div>}</ErrorBoundary>,
    );
    expect(screen.getByText('页面渲染异常')).toBeInTheDocument();

    const retryBtn = screen.getByRole('button', { name: /重试/ });
    expect(retryBtn).toBeInTheDocument();

    // 模拟外部修复：把 shouldThrow 置 false 后点击重试，边界 reset 后渲染 children
    shouldThrow = false;
    rerender(<ErrorBoundary>{shouldThrow ? <Bomb shouldThrow /> : <div>修复后的内容</div>}</ErrorBoundary>);
    fireEvent.click(retryBtn);
    expect(screen.getByText('修复后的内容')).toBeInTheDocument();
    expect(screen.queryByText('页面渲染异常')).not.toBeInTheDocument();
    spy.mockRestore();
  });

  it('onError 回调在捕获时被调用（含 error 与 componentStack）', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => { /* noop */ });
    const onError = vi.fn();
    renderWithRouter(<ErrorBoundary onError={onError}><Bomb shouldThrow /></ErrorBoundary>);
    expect(onError).toHaveBeenCalledTimes(1);
    const [err] = onError.mock.calls[0];
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe('Boom! 渲染阶段异常');
    spy.mockRestore();
  });

  it('捕获时默认上报 reportFrontendError（FE.BOUNDARY）', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => { /* noop */ });
    renderWithRouter(<ErrorBoundary><Bomb shouldThrow /></ErrorBoundary>);
    expect(reportFrontendError).toHaveBeenCalledTimes(1);
    expect(reportFrontendError).toHaveBeenCalledWith('FE.BOUNDARY', expect.stringContaining('Boom!'), expect.any(String));
    spy.mockRestore();
  });

  it('自定义 fallback 渲染函数生效', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => { /* noop */ });
    const custom = (_err: Error, _onReset: () => void) => <div className="custom-fb">自定义兜底</div>;
    renderWithRouter(<ErrorBoundary fallback={custom}><Bomb shouldThrow /></ErrorBoundary>);
    expect(screen.getByText('自定义兜底')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('正常子组件不触发 fallback 与上报', () => {
    const onError = vi.fn();
    renderWithRouter(<ErrorBoundary onError={onError}><Bomb shouldThrow={false} /></ErrorBoundary>);
    expect(screen.getByText('正常渲染内容')).toBeInTheDocument();
    expect(screen.queryByText('页面渲染异常')).not.toBeInTheDocument();
    expect(onError).not.toHaveBeenCalled();
    expect(reportFrontendError).not.toHaveBeenCalled();
  });
});
