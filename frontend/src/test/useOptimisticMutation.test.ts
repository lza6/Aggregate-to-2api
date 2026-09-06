import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useOptimisticMutation } from '../hooks/useOptimisticMutation';

describe('useOptimisticMutation', () => {
  it('乐观应用数据到视图（pending 期间显示乐观快照）', async () => {
    let resolveFn: ((v: string) => void) | null = null;
    const mutate = vi.fn(() => new Promise<string>(res => { resolveFn = res; }));
    const onOptimistic = vi.fn((items: string[], m: string) => [...items, m]);
    const { result } = renderHook(() => useOptimisticMutation<string[], string, string>({
      mutate,
      onOptimistic,
    }));
    act(() => {
      void result.current.mutate(['a', 'b'], 'c');
    });
    expect(onOptimistic).toHaveBeenCalledWith(['a', 'b'], 'c');
    expect(result.current.optimisticData).toEqual(['a', 'b', 'c']);
    expect(result.current.pending).toBe(true);
    // 解析后清空乐观数据
    await act(async () => { resolveFn!('done'); });
    expect(result.current.pending).toBe(false);
    expect(result.current.optimisticData).toBeNull();
  });

  it('成功调用 onSuccess', async () => {
    const mutate = vi.fn().mockResolvedValue('ok');
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useOptimisticMutation<string[], string, string>({
      mutate, onOptimistic: (arr, m) => [...arr, m], onSuccess,
    }));
    await act(async () => { await result.current.mutate(['x'], 'y'); });
    expect(onSuccess).toHaveBeenCalledWith('ok', 'y');
  });

  it('失败回滚乐观数据并调用 onError', async () => {
    const err = new Error('网络失败');
    const mutate = vi.fn().mockRejectedValue(err);
    const onError = vi.fn();
    const { result } = renderHook(() => useOptimisticMutation<string[], string, never>({
      mutate, onOptimistic: (arr, m) => [...arr, m], onError,
    }));
    await act(async () => { await result.current.mutate(['x'], 'y'); });
    expect(onError).toHaveBeenCalledWith(err, 'y');
    expect(result.current.optimisticData).toBeNull();
    expect(result.current.pending).toBe(false);
  });

  it('pending 时拒绝并发 mutate', async () => {
    let resolveFn: ((v: string) => void) | null = null;
    const mutate = vi.fn(() => new Promise<string>(res => { resolveFn = res; }));
    const onOptimistic = vi.fn((arr: string[], m: string) => [...arr, m]);
    const { result } = renderHook(() => useOptimisticMutation<string[], string, string>({
      mutate, onOptimistic,
    }));
    act(() => { void result.current.mutate(['a'], 'b'); });
    expect(result.current.pending).toBe(true);
    const before = mutate.mock.calls.length;
    act(() => { void result.current.mutate(['a'], 'c'); });
    // 第二次被 pending 拦截，不调用 mutate
    expect(mutate.mock.calls.length).toBe(before);
    await act(async () => { resolveFn!('done'); });
  });

  it('clear() 手动清空乐观数据', async () => {
    let resolveFn: ((v: string) => void) | null = null;
    const mutate = vi.fn(() => new Promise<string>(res => { resolveFn = res; }));
    const { result } = renderHook(() => useOptimisticMutation<string[], string, string>({
      mutate, onOptimistic: (arr, m) => [...arr, m],
    }));
    act(() => { void result.current.mutate(['a'], 'b'); });
    expect(result.current.optimisticData).not.toBeNull();
    act(() => { result.current.clear(); });
    expect(result.current.optimisticData).toBeNull();
    await act(async () => { resolveFn!('done'); });
  });
});
