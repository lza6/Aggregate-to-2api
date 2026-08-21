import { useCallback, useEffect, useRef, useState } from 'react';

export interface UseApiOptions {
  /** 轮询间隔 ms；0/省略 = 只加载一次（手动 reload 刷新） */
  intervalMs?: number;
  /** 首次加载是否立即执行（默认 true） */
  immediate?: boolean;
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
 * - 卸载安全：clearInterval + unmounted 标记，过期响应不再 setState
 */
export function useApi<T>(fetcher: () => Promise<T>, options: UseApiOptions = {}): UseApiResult<T> {
  const { intervalMs = 0, immediate = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<Error | null>(null);
  // 序号防竞态：只有最新一轮请求的响应可以落地
  const seqRef = useRef(0);
  const unmountedRef = useRef(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async (isFirst: boolean) => {
    const seq = ++seqRef.current;
    if (isFirst) setLoading(true);
    try {
      const result = await fetcherRef.current();
      if (unmountedRef.current || seq !== seqRef.current) return;
      setData(result);
      setError(null);
    } catch (e) {
      if (unmountedRef.current || seq !== seqRef.current) return;
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      if (!unmountedRef.current && seq === seqRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    if (immediate) void run(true);
    if (intervalMs > 0) {
      const timer = setInterval(() => void run(false), intervalMs);
      return () => {
        unmountedRef.current = true;
        clearInterval(timer);
      };
    }
    return () => { unmountedRef.current = true; };
  }, [intervalMs, immediate, run]);

  const reload = useCallback(() => { void run(false); }, [run]);

  return { data, loading, error, reload };
}
