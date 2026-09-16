import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { Gallery } from '../components/Gallery';
import type { GalleryItem } from '../api';
import { fetchGalleryPage, getStoredAdminKey, fetchGalleryDetail, downloadGalleryZip, softDeleteGalleryItem } from '../api';

// ── v16 P0-3 画廊相册化：分页列表 / 搜索防抖 / 多选 / 详情弹窗 / ZIP 打包 / 软删确认 / 无限滚动 ──

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    fetchGalleryPage: vi.fn(),
    signGallery: vi.fn(),
    getStoredAdminKey: vi.fn(() => ''),
    fetchGalleryDetail: vi.fn(),
    downloadGalleryZip: vi.fn(),
    softDeleteGalleryItem: vi.fn(),
  };
});

function item(id: string, prompt = 'test prompt'): GalleryItem {
  return { id, image_url: `https://img.example/${id}.png`, image_mime: 'image/png', prompt, aspect_ratio: '1:1', duration_sec: 1.2, model: 'imagefree/default' };
}

// jsdom 无 IntersectionObserver：stub 不自动触发加载（无限滚动走「加载更多」按钮兜底路径单测）
class IntersectionObserverStub implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin = '';
  readonly thresholds: ReadonlyArray<number> = [];
  constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] { return []; }
}
if (typeof IntersectionObserver === 'undefined') {
  vi.stubGlobal('IntersectionObserver', IntersectionObserverStub);
}

function page(items: GalleryItem[], total: number) {
  return { items, total, page: 1, page_size: 24 };
}

async function flush() {
  await act(async () => {});
}

function renderGallery() {
  return render(<Gallery limit={20} />);
}

describe('Gallery v16 P0-3 相册化', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    (getStoredAdminKey as ReturnType<typeof vi.fn>).mockReturnValue('');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('渲染多张图；点击勾选框进入多选并显示操作条', async () => {
    (fetchGalleryPage as ReturnType<typeof vi.fn>).mockResolvedValue(page([item('t1', '橘猫'), item('t2', '星球')], 2));
    renderGallery();
    await flush();
    expect(screen.getByAltText('橘猫')).toBeInTheDocument();
    expect(screen.getByAltText('星球')).toBeInTheDocument();
    expect(screen.getByText('2 张')).toBeInTheDocument();

    const boxes = screen.getAllByRole('button', { name: '选择' });
    fireEvent.click(boxes[0]);
    await flush();
    expect(screen.getByText('已选 1 张')).toBeInTheDocument();
    expect(screen.getByText('打包下载 ZIP')).toBeInTheDocument();
  });

  it('点击卡片打开详情弹窗并加载相似推荐', async () => {
    (fetchGalleryPage as ReturnType<typeof vi.fn>).mockResolvedValue(page([item('t1', '橘猫')], 1));
    (fetchGalleryDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      item: item('t1', '橘猫'),
      similar: [item('t9', '相似图')],
      similar_count: 1,
    });
    renderGallery();
    await flush();

    const card = screen.getByRole('button', { name: /查看作品：橘猫/ });
    fireEvent.click(card);
    await flush();

    expect(screen.getByRole('dialog', { name: '作品详情' })).toBeInTheDocument();
    expect(screen.getByText('相似作品')).toBeInTheDocument();
    expect(screen.getByAltText('相似图')).toBeInTheDocument();
    expect(fetchGalleryDetail).toHaveBeenCalledWith('t1', undefined, 5);
  });

  it('选中后打包下载调用 downloadGalleryZip 并带上选中 id', async () => {
    (fetchGalleryPage as ReturnType<typeof vi.fn>).mockResolvedValue(page([item('t1'), item('t2')], 2));
    (downloadGalleryZip as ReturnType<typeof vi.fn>).mockResolvedValue({ blob: new Blob(['zip']), total: 2, requested: 2 });
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = vi.fn(() => 'blob:x');
    (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL = vi.fn();

    renderGallery();
    await flush();
    const boxes = screen.getAllByRole('button', { name: '选择' });
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    await flush();

    fireEvent.click(screen.getByText('打包下载 ZIP'));
    await flush();
    expect(downloadGalleryZip).toHaveBeenCalledTimes(1);
    const arg = (downloadGalleryZip as ReturnType<typeof vi.fn>).mock.calls[0][0] as string[];
    expect(new Set(arg)).toEqual(new Set(['t1', 't2']));
  });

  it('软删需确认弹窗；确认后调用 softDeleteGalleryItem 并从列表移除', async () => {
    (fetchGalleryPage as ReturnType<typeof vi.fn>).mockResolvedValue(page([item('t1', '待删'), item('t2', '保留')], 2));
    (softDeleteGalleryItem as ReturnType<typeof vi.fn>).mockResolvedValue({ deleted: true, task_id: 't1', soft: true });

    renderGallery();
    await flush();
    const boxes = screen.getAllByRole('button', { name: '选择' });
    fireEvent.click(boxes[0]);
    await flush();

    // 点「移除」先弹确认框（不直接删）
    fireEvent.click(screen.getByText('移除'));
    await flush();
    expect(screen.getByRole('dialog', { name: '确认移除' })).toBeInTheDocument();
    expect(softDeleteGalleryItem).not.toHaveBeenCalled();

    // 点「取消」→ 不删
    fireEvent.click(screen.getByText('取消'));
    await flush();
    expect(softDeleteGalleryItem).not.toHaveBeenCalled();

    // 再走一遍 → 确认移除 → 删 t1
    fireEvent.click(screen.getByText('移除'));
    await flush();
    fireEvent.click(screen.getByText('确认移除'));
    await flush();
    expect(softDeleteGalleryItem).toHaveBeenCalledWith('t1', undefined);
    expect(screen.queryByAltText('待删')).not.toBeInTheDocument();
    expect(screen.getByAltText('保留')).toBeInTheDocument();
  });

  it('搜索框防抖后按 prompt 子串重载列表', async () => {
    vi.useFakeTimers();
    (fetchGalleryPage as ReturnType<typeof vi.fn>).mockImplementation((opts: { search?: string }) =>
      Promise.resolve(page(opts?.search ? [item('t1', '橘猫')] : [item('t1', '橘猫'), item('t2', '星球')], opts?.search ? 1 : 2)),
    );
    renderGallery();
    await flush();
    expect(screen.getByAltText('星球')).toBeInTheDocument();

    const input = screen.getByRole('searchbox', { name: '搜索画廊作品' });
    fireEvent.change(input, { target: { value: '橘猫' } });
    await vi.advanceTimersByTimeAsync(450);
    await flush();

    expect(fetchGalleryPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: '橘猫', page: 1 }));
    expect(screen.getByAltText('橘猫')).toBeInTheDocument();
    expect(screen.queryByAltText('星球')).not.toBeInTheDocument();
  });

  it('未加载完时显示「加载更多」，点击后追加下一页', async () => {
    (fetchGalleryPage as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(page([item('t1', '第一张')], 3))
      .mockResolvedValueOnce(page([item('t2', '第二张'), item('t3', '第三张')], 3));
    renderGallery();
    await flush();
    expect(screen.getByText(/加载更多（1\/3）/)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/加载更多/));
    await flush();

    expect(fetchGalleryPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    expect(screen.getByAltText('第二张')).toBeInTheDocument();
    expect(screen.getByAltText('第三张')).toBeInTheDocument();
    expect(screen.queryByText(/加载更多/)).not.toBeInTheDocument();
    expect(screen.getByText(/已加载全部 3 张/)).toBeInTheDocument();
  });
});
