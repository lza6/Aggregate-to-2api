import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from '../components/EmptyState';

describe('EmptyState', () => {
  it('默认图标 + 文案渲染', () => {
    render(<EmptyState text="暂无任务" />);
    expect(screen.getByText('暂无任务')).toBeInTheDocument();
    // 默认 icon 📦
    expect(screen.getByText('📦')).toBeInTheDocument();
  });

  it('自定义 icon + hint', () => {
    render(<EmptyState icon="📭" text="无数据" hint="请稍后再试" />);
    expect(screen.getByText('📭')).toBeInTheDocument();
    expect(screen.getByText('请稍后再试')).toBeInTheDocument();
  });

  it('无 hint 时不渲染 es-sub', () => {
    const { container } = render(<EmptyState text="x" />);
    expect(container.querySelector('.es-sub')).toBeNull();
  });

  it('ctaLabel + onCta 渲染主按钮并点击触发', () => {
    const onCta = vi.fn();
    render(<EmptyState text="无任务" ctaLabel="刷新" onCta={onCta} />);
    const btn = screen.getByRole('button', { name: /刷新/ });
    fireEvent.click(btn);
    expect(onCta).toHaveBeenCalledTimes(1);
  });

  it('无 onCta 时不渲染主按钮', () => {
    render(<EmptyState text="x" ctaLabel="刷新" />);
    expect(screen.queryByRole('button', { name: /刷新/ })).toBeNull();
  });

  it('secondaryHref 渲染次级链接', () => {
    render(<EmptyState text="x" secondaryLabel="前往生成" secondaryHref="/generate" />);
    const link = screen.getByRole('link', { name: /前往生成/ });
    expect(link).toHaveAttribute('href', '/generate');
  });

  it('onSecondary 渲染次级按钮并点击触发', () => {
    const onSecondary = vi.fn();
    render(<EmptyState text="x" secondaryLabel="查看日志" onSecondary={onSecondary} />);
    fireEvent.click(screen.getByRole('button', { name: /查看日志/ }));
    expect(onSecondary).toHaveBeenCalledTimes(1);
  });

  it('children 渲染自定义底部内容', () => {
    render(<EmptyState text="x">{<button>自定义</button>}</EmptyState>);
    expect(screen.getByRole('button', { name: '自定义' })).toBeInTheDocument();
  });

  it('role=status 无障碍语义', () => {
    render(<EmptyState text="x" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
