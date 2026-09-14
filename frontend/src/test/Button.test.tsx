// P1-13：通用 Button 组件测试 —— loading/disabled 防重复点击、aria-busy、variant 类名。
// 风格对齐现有 test/ 目录（vitest + @testing-library/react + fireEvent，见 Skeleton.test.tsx）。
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '../components/ui/Button';

describe('Button', () => {
  it('默认渲染原生 button，语义正确', () => {
    const { container } = render(<Button>保存</Button>);
    expect(container.querySelector('button')).not.toBeNull();
    expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument();
  });

  it('variant 映射到对应 tf-btn-* 类名', () => {
    const { container } = render(
      <div>
        <Button variant="primary">P</Button>
        <Button variant="secondary">S</Button>
        <Button variant="ghost">G</Button>
        <Button variant="danger">D</Button>
      </div>,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons[0].classList.contains('tf-btn-primary')).toBe(true);
    expect(buttons[1].classList.contains('tf-btn-secondary')).toBe(true);
    expect(buttons[2].classList.contains('tf-btn-ghost')).toBe(true);
    expect(buttons[3].classList.contains('tf-btn-danger')).toBe(true);
  });

  it('size 映射到 tf-btn-sm / tf-btn-lg，md 不加尺寸类', () => {
    const { container } = render(
      <div>
        <Button size="sm">S</Button>
        <Button size="md">M</Button>
        <Button size="lg">L</Button>
      </div>,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons[0].classList.contains('tf-btn-sm')).toBe(true);
    expect(buttons[1].classList.contains('tf-btn-sm')).toBe(false);
    expect(buttons[1].classList.contains('tf-btn-lg')).toBe(false);
    expect(buttons[2].classList.contains('tf-btn-lg')).toBe(true);
  });

  it('自定义 className 透传并保留 tf-btn 基础类', () => {
    const { container } = render(<Button className="my-extra">X</Button>);
    const btn = container.querySelector('button')!;
    expect(btn.classList.contains('tf-btn')).toBe(true);
    expect(btn.classList.contains('my-extra')).toBe(true);
  });

  it('loading 时渲染 spinner、aria-busy=true 且 disabled（防重复点击）', () => {
    const { container } = render(<Button loading>提交中…</Button>);
    const btn = screen.getByRole('button', { name: /提交中/ });
    expect(btn).toHaveAttribute('aria-busy', 'true');
    expect(btn).toBeDisabled();
    expect(container.querySelector('.tf-btn-spinner')).not.toBeNull();
  });

  it('loading 时点击不触发 onClick（防重复提交）', () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>提交中…</Button>);
    fireEvent.click(screen.getByRole('button', { name: /提交中/ }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('disabled 时点击不触发 onClick', () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>保存</Button>);
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('非 loading/disabled 时点击触发 onClick', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>保存</Button>);
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('spinner 使用 aria-hidden，不干扰可访问名称', () => {
    render(<Button loading>保存</Button>);
    const btn = screen.getByRole('button', { name: '保存' });
    expect(btn.querySelector('.tf-btn-spinner')).toHaveAttribute('aria-hidden', 'true');
  });
});
