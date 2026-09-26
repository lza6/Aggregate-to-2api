// P0-4 前端部分测试：任务实时进度可视化 + 幂等取消 + 一键重试。
// 风格对齐 GalleryAlbum.test.tsx（vi.mock('../api') + act flush + IntersectionObserver stub 惯例）。
//
// jsdom 无 EventSource：默认走 useTaskProgress 轮询兜底路径；本文件 stub 一个最小 EventSource
// 以验证 SSE 精确阶段徽章流转（solving/generating + progress）在真实浏览器路径下的渲染。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { TasksPage } from '../pages/Tasks';
import type { Task } from '../api';
import { fetchTasks, fetchTask, cancelTask, retryTask, notify } from '../api';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    fetchTasks: vi.fn(),
    fetchTask: vi.fn(),
    cancelTask: vi.fn(),
    retryTask: vi.fn(),
    notify: vi.fn(),
  };
});

// ── jsdom 最小 EventSource stub：登记实例 + 手动 dispatch 事件（验证 SSE 阶段流转用） ──
class EventSourceStub {
  static instances: EventSourceStub[] = [];
  listeners: Record<string, ((ev: MessageEvent) => void)[]> = {};
  onerror: ((ev: Event) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    EventSourceStub.instances.push(this);
  }
  addEventListener(type: string, cb: (ev: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(cb);
  }
  removeEventListener(): void {}
  close() {
    this.closed = true;
  }
  dispatch(type: string, data: unknown) {
    (this.listeners[type] ?? []).forEach(cb => cb({ data: JSON.stringify(data) } as MessageEvent));
  }
}

function task(id: string, status: string, extra: Partial<Task> = {}): Task {
  return {
    id,
    status,
    prompt: 'a cat',
    image_url: null,
    error: null,
    duration_sec: null,
    created_at: 1700000000,
    model: 'imagefree/default',
    ...extra,
  };
}

// jsdom 无 EventSource：模块作用域 stub 一次（沿用 GalleryAlbum 对 IntersectionObserver 的惯例），
// 使所有用例都能走到「SSE 增强 + 轮询兜底」双路径。
if (typeof EventSource === 'undefined') {
  vi.stubGlobal('EventSource', EventSourceStub);
}

function list(items: Task[]) {
  return { items, total: items.length };
}

async function flush() {
  await act(async () => {});
}

beforeEach(() => {
  vi.clearAllMocks();
  EventSourceStub.instances = [];
});

afterEach(() => {
  // v20.3.1 flaky 根治：restoreAllMocks 会还原 vi.stubGlobal('EventSource')，
  // 并行测试文件间导致 EventSource 被还原为 undefined → SSE dispatch 失败。
  // 改用 clearAllMocks（只清 mock 调用/实现，不清全局 stub）。
  vi.clearAllMocks();
  EventSourceStub.instances = [];
});

describe('Tasks 页面 P0-4 进度可视化 + 取消/重试', () => {
  it('processing 行显示阶段徽章/进度条：轮询兜底「运行中」→ SSE 事件流转到 solving/generating', async () => {
    fetchTasks.mockResolvedValue(list([task('t1', 'processing')]));
    fetchTask.mockResolvedValue(task('t1', 'processing'));
    render(<TasksPage />);
    await flush();

    // 轮询路径：status=processing 无精确子阶段 → 回退「运行中」徽章 + 不确定进度条（progressbar 无 valuenow）
    const runningLabel = screen.getByText('运行中');
    expect(runningLabel).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toBeInTheDocument();
    expect(bar).not.toHaveAttribute('aria-valuenow');

    // SSE 路径：status 事件携带 solving=30 → 阶段徽章流转 + 定值进度条
    const es = EventSourceStub.instances[EventSourceStub.instances.length - 1];
    expect(es).toBeTruthy();
    await act(async () => {
      es.dispatch('status', { status: 'processing', status_detail: 'solving', progress: 30 });
    });
    expect(screen.getByText('求解中')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '30');

    // 继续流转 generating=80
    await act(async () => {
      es.dispatch('status', { status: 'processing', status_detail: 'generating', progress: 80 });
    });
    expect(screen.getByText('生成中')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '80');
  });

  it('processing 行点「取消」→ 调 cancelTask + 行状态更新为 cancelled + 按钮消失', async () => {
    fetchTasks.mockResolvedValue(list([task('t1', 'processing')]));
    fetchTask.mockResolvedValue(task('t1', 'processing'));
    cancelTask.mockResolvedValue({ task_id: 't1', status: 'cancelled', cancelled: true });
    render(<TasksPage />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: /取消/ }));
    await flush();

    expect(cancelTask).toHaveBeenCalledWith('t1');
    expect(notify).toHaveBeenCalledWith(expect.stringContaining('已取消'), 'success');
    // 行状态徽章变 cancelled
    expect(screen.getByText('已取消')).toBeInTheDocument();
    expect(screen.queryByText('处理中')).not.toBeInTheDocument();
    // 已终态行不再显示取消按钮（防重复点击已由 loading 态 + 移除按钮双保险）
    expect(screen.queryByRole('button', { name: /取消/ })).not.toBeInTheDocument();
  });

  it('error 行点「重试」→ 调 retryTask + toast 新任务已提交', async () => {
    fetchTasks.mockResolvedValue(list([task('t1', 'error')]));
    retryTask.mockResolvedValue({ task_id: 't2', source_task_id: 't1', status: 'queued' });
    render(<TasksPage />);
    await flush();

    expect(screen.getByText('失败')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    await flush();

    expect(retryTask).toHaveBeenCalledWith('t1');
    expect(notify).toHaveBeenCalledWith(expect.stringContaining('重试已提交'), 'success');
  });

  it('幂等取消：任务已被终态 → cancelled=false → 提示已终态不报错 + 行状态同步为终态', async () => {
    fetchTasks.mockResolvedValue(list([task('t1', 'processing')]));
    fetchTask.mockResolvedValue(task('t1', 'processing'));
    cancelTask.mockResolvedValue({ task_id: 't1', status: 'completed', cancelled: false });
    render(<TasksPage />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: /取消/ }));
    await flush();

    expect(cancelTask).toHaveBeenCalledWith('t1');
    // 幂等命中：info 提示已终态，非 error
    expect(notify).toHaveBeenCalledWith(expect.stringContaining('终态'), 'info');
    expect(notify).not.toHaveBeenCalledWith(expect.anything(), 'error');
    // 行状态徽章同步为后端返回的当前终态
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /取消/ })).not.toBeInTheDocument();
  });
});