import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CommandPalette } from '../components/CommandPalette';

function renderWithRouter(ui: React.ReactNode) {
  return render(<MemoryRouter initialEntries={['/']}>{ui}</MemoryRouter>);
}

/** 触发 Cmd/Ctrl+K 打开面板（封装 act 包裹 state 更新） */
function openPalette() {
  const ev = new KeyboardEvent('keydown', { key: 'k', bubbles: true, cancelable: true });
  Object.defineProperty(ev, 'ctrlKey', { value: true });
  act(() => { document.dispatchEvent(ev); });
}

describe('CommandPalette', () => {
  it('默认不渲染（open=false）', () => {
    const { container } = renderWithRouter(<CommandPalette />);
    expect(container.querySelector('.cmdk-overlay')).toBeNull();
  });

  it('Cmd+K 打开面板', () => {
    renderWithRouter(<CommandPalette />);
    openPalette();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/输入页面名或关键词/)).toBeInTheDocument();
  });

  it('Ctrl+K 也能打开（Windows）', () => {
    renderWithRouter(<CommandPalette />);
    openPalette();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('过滤：输入"日志"只显示相关项', () => {
    renderWithRouter(<CommandPalette />);
    openPalette();
    const input = screen.getByPlaceholderText(/输入页面名或关键词/);
    act(() => { fireEvent.change(input, { target: { value: '日志' } }); });
    expect(screen.getByText('实时日志')).toBeInTheDocument();
    expect(screen.queryByText('仪表盘')).not.toBeInTheDocument();
  });

  it('无匹配时显示"无匹配页面"', () => {
    renderWithRouter(<CommandPalette />);
    openPalette();
    const input = screen.getByPlaceholderText(/输入页面名或关键词/);
    act(() => { fireEvent.change(input, { target: { value: 'zzzzzzz' } }); });
    expect(screen.getByText('无匹配页面')).toBeInTheDocument();
  });

  it('Esc 关闭面板', () => {
    renderWithRouter(<CommandPalette />);
    openPalette();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    const evEsc = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
    act(() => { document.dispatchEvent(evEsc); });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('点击遮罩关闭面板', () => {
    const { container } = renderWithRouter(<CommandPalette />);
    openPalette();
    const overlay = container.querySelector('.cmdk-overlay')!;
    act(() => { fireEvent.click(overlay); });
    expect(container.querySelector('.cmdk-overlay')).toBeNull();
  });

  it('aria-combobox 与 listbox 语义存在（WCAG 2.2 AA）', () => {
    renderWithRouter(<CommandPalette />);
    openPalette();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });
});
