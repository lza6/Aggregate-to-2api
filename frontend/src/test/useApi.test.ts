import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useApi } from '../hooks/useApi';

describe('useApi', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('首次加载（immediate=true，默认）：loading=true → resolve 后 data 落地、loading=false', async () => {
    const fetcher = vi.fn<[unknown], Promise<number>>().mockImplementation(async () => {
      return await Promise.resolve(42);
    });
    const { result } = renderHook(() => useApi(fetcher as unknown as () => Promise<number>));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBe(null);
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe(42);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(null);
  });

  it('immediate=false：初始不发起请求、loading=false', async () => {
    const fetcher = vi.fn().mockResolvedValue(1);
    const { result } = renderHook(() =>
      useApi(fetcher, { immediate: false }),
    );
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBe(null);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('reload() 手动触发新一轮 fetch', async () => {
    const fetcher = vi.fn().mockResolvedValue('x');
    const { result } = renderHook(() => useApi(fetcher));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    act(() => {
      result.current.reload();
    });
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('fetcher 抛错 → error 落地、loading=false', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useApi(fetcher));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('boom');
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBe(null);
  });

  it('非 Error 抛出值 → 包装为 Error', async () => {
    const fetcher = vi.fn().mockRejectedValue('string-error');
    const { result } = renderHook(() => useApi(fetcher));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('string-error');
  });

  it('轮询 interval：到点触发新请求', async () => {
    const fetcher = vi.fn().mockImplementation(async () => {
      return await Promise.resolve(Date.now());
    });
    renderHook(() => useApi(fetcher, { intervalMs: 1000 }));
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('轮询失败不停止：error 置位但下一轮继续', async () => {
    // fetcher：调用 1 返回 1，调用 2 抛 net，调用 3 返回 3，后续继续递增。
    // 注意 useApi 的 interval 与首次 immediate 都会发起请求：act 进入后会同时触发
    // immediate 首次 + advanceTimersByTime 推进的 interval。用 calls 计数判定。
    const fetcher = vi.fn().mockImplementation(async () => {
      const n = fetcher.mock.calls.length; // 1,2,3,...
      if (n === 2) throw new Error('net');
      return n;
    });
    const { result } = renderHook(() => useApi(fetcher, { intervalMs: 1000 }));
    // 推进到首个 interval tick（immediate 已发起调用1；推进 1s 触发调用2）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.data).toBe(1);
    expect(result.current.error?.message).toBe('net');
    // 再推进 1s → 调用3，成功，error 清空，data=3
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.data).toBe(3);
    expect(result.current.error).toBe(null);
  });

  it('竞态防护：慢响应被新响应覆盖时旧响应不落地', async () => {
    // 第一次慢（200ms 后才 resolve=旧值 1），第二次快（立即 resolve=新值 2）。
    // 期望最终 data=2（新响应），旧响应到达后被序号丢弃。
    let slowResolve: (v: number) => void = () => {};
    const slow = new Promise<number>((resolve) => {
      slowResolve = resolve;
    });
    const fetcher = vi
      .fn()
      .mockImplementationOnce(async () => {
        return await slow;
      })
      .mockImplementationOnce(async () => {
        return await Promise.resolve(2);
      });
    const { result } = renderHook(() => useApi(fetcher));
    // 第一次请求已发起（immediate）。立即触发第二次（reload）。
    act(() => {
      result.current.reload();
    });
    // 让第二次（快）resolve
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe(2);
    // 现在让第一次（慢）resolve = 1；因 seq 不匹配应被丢弃。
    await act(async () => {
      slowResolve(1);
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe(2);
  });

  it('卸载后不再 setState（unmounted 防护）', async () => {
    let slowResolve: (v: number) => void = () => {};
    const slow = new Promise<number>((resolve) => {
      slowResolve = resolve;
    });
    const fetcher = vi.fn().mockImplementation(async () => {
      return await slow;
    });
    const { result, unmount } = renderHook(() => useApi(fetcher));
    expect(result.current.loading).toBe(true);
    unmount();
    // 卸载后 resolve：不应抛「setState on unmounted」警告
    await act(async () => {
      slowResolve(99);
      await vi.runAllTimersAsync();
    });
    // 已卸载，result.current 不再更新；这里仅断言不抛。
    expect(result.current.data).toBe(null);
  });

  it('visibilitychange：隐藏时跳过轮询、恢复可见立即补拉一轮', async () => {
    const fetcher = vi.fn().mockImplementation(async () => {
      return await Promise.resolve(Date.now());
    });
    renderHook(() => useApi(fetcher, { intervalMs: 1000 }));
    expect(fetcher).toHaveBeenCalledTimes(1);

    // 切到 hidden：visibilitychange 事件 + 推进 2s（不应触发新请求）
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      configurable: true,
    });
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    // 切回 visible：visibilitychange 事件 + 少量推进让补拉的 fetch 落地
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      configurable: true,
    });
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(100);
    });
    // 恢复可见立即补拉一轮 → 至少 +1
    expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('intervalMs=0：只加载一次，不轮询', async () => {
    const fetcher = vi.fn().mockResolvedValue(1);
    renderHook(() => useApi(fetcher, { intervalMs: 0 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  // ── P2-4 防抖 + 竞态防护 ───────────────────────────────────────────
  it('debounceMs>0：连续 reload 只在静默期后发一次请求', async () => {
    const fetcher = vi.fn().mockResolvedValue('v');
    const { result } = renderHook(() => useApi(fetcher, { debounceMs: 250 }));
    // immediate 首次已发起（debounce 250ms 延迟执行）
    expect(fetcher).not.toHaveBeenCalled();
    act(() => { result.current.reload(); });
    act(() => { result.current.reload(); });
    act(() => { result.current.reload(); });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    // 静默期后只执行一次（合并了中间多次 reload）
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('debounceMs>0：静默期前最后一次 reload 生效，期间调用被取消', async () => {
    const fetcher = vi.fn().mockResolvedValue('final');
    const { result } = renderHook(() => useApi(fetcher, { debounceMs: 250 }));
    act(() => { result.current.reload(); });
    // 静默期内 reload 会重置定时器；推进到首个 250ms 前不执行
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(fetcher).not.toHaveBeenCalled();
    // 再触发一次 reload，推进完剩余静默期
    act(() => { result.current.reload(); });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe('final');
  });

  it('移除卸载后残留的 debounce 定时器（unmount 不 setState/不抛）', async () => {
    const fetcher = vi.fn().mockResolvedValue('x');
    const { unmount } = renderHook(() => useApi(fetcher, { debounceMs: 250 }));
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    // 卸载后不应触发请求
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('竞态防护：先发慢请求 300ms / 后发快请求 50ms，最终保留快结果、取消慢结果', async () => {
    let slowResolve: (v: string) => void = () => {};
    const slow = new Promise<string>((resolve) => { slowResolve = resolve; });
    const fetcher = vi
      .fn()
      .mockImplementationOnce(async () => { return await slow; }) // 第一次慢
      .mockImplementationOnce(async () => { return await Promise.resolve('fast'); }); // 第二次快
    const { result } = renderHook(() => useApi(fetcher));
    // immediate 已发起第一次（慢）
    expect(result.current.loading).toBe(true);
    // 立即触发第二次（快）
    act(() => { result.current.reload(); });
    // 快请求先落地
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe('fast');
    // 慢请求此刻才 resolve=1，因 seq 不匹配被丢弃
    await act(async () => {
      slowResolve('slow');
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe('fast');
  });

  it('fetcher 收到 AbortController.signal：后发请求会中止先发在途请求', async () => {
    const signals: (AbortSignal | undefined)[] = [];
    const fetcher = vi.fn<[AbortSignal | undefined], Promise<string>>()
      .mockImplementationOnce(async (_sig) => {
        return new Promise<string>((_res, reject) => {
          _sig?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        });
      })
      .mockImplementationOnce(async () => { return await Promise.resolve('fast'); });
    const { result } = renderHook(() => useApi(fetcher as unknown as (signal?: AbortSignal) => Promise<string>));
    act(() => { result.current.reload(); });
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(result.current.data).toBe('fast');
    expect(result.current.error).toBe(null);
  });
});
