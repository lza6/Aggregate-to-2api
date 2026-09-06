import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton } from '../components/Skeleton';

describe('Skeleton', () => {
  it('variant=lines 默认渲染 count 行', () => {
    const { container } = render(<Skeleton variant="lines" count={4} />);
    expect(container.querySelectorAll('.sk-bar')).toHaveLength(4);
  });

  it('variant=rows 渲染 count 行表格骨架（含列分布）', () => {
    const { container } = render(<Skeleton variant="rows" count={3} columns={5} />);
    expect(container.querySelectorAll('.sk-row')).toHaveLength(3);
    // 每行至少 columns 个 sk-bar
    expect(container.querySelectorAll('.sk-row:first-child .sk-bar').length).toBeGreaterThanOrEqual(5);
  });

  it('variant=cards 渲染 cards 个卡片骨架', () => {
    const { container } = render(<Skeleton variant="cards" cards={3} />);
    expect(container.querySelectorAll('.sk-card')).toHaveLength(3);
  });

  it('aria-busy=true + role=status（WCAG 2.2）', () => {
    render(<Skeleton />);
    const wrapper = document.querySelector('.sk-wrapper');
    expect(wrapper).not.toBeNull();
    expect(wrapper!.getAttribute('aria-busy')).toBe('true');
    expect(wrapper!.getAttribute('role')).toBe('status');
  });

  it('默认 variant=lines', () => {
    const { container } = render(<Skeleton />);
    expect(container.querySelectorAll('.sk-bar').length).toBeGreaterThan(0);
    expect(container.querySelector('.sk-rows-wrap')).toBeNull();
    expect(container.querySelector('.sk-cards-wrap')).toBeNull();
  });

  it('自定义 className 与 style 合并', () => {
    const { container } = render(<Skeleton className="my-extra" />);
    const wrapper = container.querySelector('.sk-wrapper');
    expect(wrapper?.classList.contains('my-extra')).toBe(true);
  });
});
