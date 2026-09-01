import { useCallback, useEffect, useRef, useState } from 'react';
import { pollingScheduler } from './usePollingScheduler';

export interface UseApiOptions {
  /** 轮询间隔 ms；0/省略 = 只加载一次（手动 reload 刷新） */
  intervalMs?: number;
  /** 首次加载是否立即执行（默认 true） */
  immediate?: boolean;
  /**
   * 查询防抖 ms（P2-4）：>0 时，连续触发（reload / 查询变化）会在最后一次触发后延迟该时长再发起请求，
   * 且会取消上一轮在途请求，保证只有最新查询结果落地。0/省略 = 不防抖。
   */
  debounceMs?: number;
}

export interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  /** 手动重新加载（错误重试 / 操作后刷新用） */
  reload: () => void;
}

/**
 * 统一数据层：fetcher + 可选轮询 + 竞态防护 + 卸载清理。
 *
 * - 轮询失败不停止：error 置位但下一轮继续（管理面板宁可重试，不静默断流）
 * - 竞态防护：响应序号不匹配（已被更新一轮覆盖）则丢弃
 * - 取消防护：每轮创建一个 AbortController 并传给 fetcher，新请求会取消旧请求；
 *   若 fetcher 忽略 signal（普通闭包），序号防护仍保证旧响应不落地
 * - 查询防抖：debounceMs>0 时快速合并查询变化，只在静默期后发一次请求
 * - 卸载安全：clearInterval + unmounted 标记，过期响应不再 setState
 *
 * fetcher 可声明可选 signal 形参以支持真正中止（如 `(signal) => fetchX(..., signal)`）；
 * 不声明 signal 的普通闭包 fetcher 依然兼容（TS 下 0≈参数函数可赋给带可选参数函数）。
 */
export function useApi<T>(fetcher: (signal?: AbortSignal) => Promise<T>, options: UseApiOptions = {}): UseApiResult<T> {
  const { intervalMs = 0, immediate = true, debounceMs = 0 } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<Error | null>(null);
  // 序号防竞态：只有最新一轮请求的响应可以落地
  const seqRef = useRef(0);
  const unmountedRef = useRef(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  // P2-4: 每轮请求的 AbortController（新请求取消旧请求）+ 防抖定时器
  const controllerRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const run = useCallback(async (isFirst: boolean) => {
    const seq = ++seqRef.current;
    // 新请求取消上一轮在途请求（fetcher 若忽略 signal，则仅靠序号防护丢弃旧响应）
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    if (isFirst) setLoading(true);

    const execute = async () => {
      try {
        const result = await fetcherRef.current(controller.signal);
        if (unmountedRef.current || seq !== seqRef.current) return;
        setData(result);
        setError(null);
      } catch (e) {
        if (unmountedRef.current || seq !== seqRef.current) return;
        // 主动取消导致的 AbortError 不算真实错误，静默丢弃
        if ((e as Error)?.name === 'AbortError') return;
        setError(e instanceof Error ? e : new Error(String(e)));
      } finally {
        if (!unmountedRef.current && seq === seqRef.current) setLoading(false);
      }
    };

    // P2-4: 查询防抖 —— 静默期结束后才发起请求
    if (debounceMs > 0) {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(() => {
        debounceTimerRef.current = null;
        void execute();
      }, debounceMs);
      return;
    }
    await execute();
  }, [debounceMs]);

  useEffect(() => {
    unmountedRef.current = false;
    if (immediate) void run(true);
    // P1-3 共享调度器：intervalMs>0 时注册到全局单例 pollingScheduler，
    // 所有 useApi 轮询共用一个 setInterval tick（Dashboard 8 个 useApi → 1 个 timer），
    // 失焦暂停 / 聚焦补拉由 scheduler 统一管（不再每个 useApi 各绑 visibilitychange）。
    if (intervalMs > 0) {
      const unregister = pollingScheduler.register(intervalMs, () => {
        if (unmountedRef.current) return;
        void run(false);
      });
      return () => {
        unmountedRef.current = true;
        unregister();
        controllerRef.current?.abort();
        if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      };
    }
    return () => {
      unmountedRef.current = true;
      controllerRef.current?.abort();
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [intervalMs, immediate, run]);

  const reload = useCallback(() => { void run(false); }, [run]);

  return { data, loading, error, reload };
}
