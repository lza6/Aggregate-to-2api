// src/test/desktopNotify.test.ts — P1-7 桌面终态通知聚合（1s 窗口合并同类型）。
// 验收：
// - 单条 → 逐条文案（保持旧行为：含任务名）
// - 窗口内多条 → 一条汇总「N 项任务完成：X 成功 Y 失败」
// - 空窗口 flush → null
// - 浏览器环境（无 __TAURI_INTERNALS__）→ 发送静默降级，不产生 unhandled rejection
import { describe, it, expect, vi, afterEach } from 'vitest';

const { notifyTaskDone, flushDesktopNotifications } = await import('../lib/desktopNotify');

describe('desktopNotify 1s 窗口聚合', () => {
  afterEach(() => {
    // 清掉残留聚合窗口与定时器，避免跨用例/跨文件泄漏
    flushDesktopNotifications();
    vi.restoreAllMocks();
  });

  it('单条任务 → 单条通知（含任务名，保持旧行为）', () => {
    notifyTaskDone({ name: '任务A', ok: true });
    const s = flushDesktopNotifications();
    expect(s?.count).toBe(1);
    expect(s?.ok).toBe(1);
    expect(s?.fail).toBe(0);
    expect(s?.body).toContain('任务A');
  });

  it('窗口内 3 条合并为一条汇总：3 项任务完成：2 成功 1 失败', () => {
    notifyTaskDone({ name: 'A', ok: true });
    notifyTaskDone({ name: 'B', ok: true });
    notifyTaskDone({ name: 'C', ok: false });
    const s = flushDesktopNotifications();
    expect(s?.count).toBe(3);
    expect(s?.ok).toBe(2);
    expect(s?.fail).toBe(1);
    expect(s?.body).toContain('3 项任务完成');
    expect(s?.body).toContain('2 成功');
    expect(s?.body).toContain('1 失败');
  });

  it('多条全成功时不出现失败段', () => {
    notifyTaskDone({ name: 'A', ok: true });
    notifyTaskDone({ name: 'B', ok: true });
    const s = flushDesktopNotifications();
    expect(s?.count).toBe(2);
    expect(s?.ok).toBe(2);
    expect(s?.fail).toBe(0);
    expect(s?.body).not.toContain('失败');
  });

  it('空窗口 flush → null', () => {
    expect(flushDesktopNotifications()).toBeNull();
  });

  it('浏览器环境（无 __TAURI_INTERNALS__）：发送静默降级，无 unhandled rejection', async () => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    const unhandled: unknown[] = [];
    const onRej = (e: PromiseRejectionEvent) => unhandled.push(e.reason);
    window.addEventListener('unhandledrejection', onRej);

    notifyTaskDone({ name: '任务X', ok: true });
    flushDesktopNotifications();
    await new Promise(r => setTimeout(r, 50));

    window.removeEventListener('unhandledrejection', onRej);
    expect(unhandled.length).toBe(0);
  });
});
