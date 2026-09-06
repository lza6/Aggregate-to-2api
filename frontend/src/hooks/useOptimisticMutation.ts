/**
 * useOptimisticMutation — 写操作乐观更新（P2-C1）
 *
 * 适用场景：封禁 IP / DLQ 重试 / 清空死信 / 暂停号池 等写操作。
 * 在请求发出前先把变更应用到本地数据视图，失败回滚 + toast 提示；
 * 成功后用后端返回的真实数据（或 reload 结果）替换乐观快照。
 *
 * 设计要点（对照 CLAUDE.md 反伪实现）：
 * - 不伪装成功：失败必须回滚 + 通知；成功必须以服务器数据为准（而非保留乐观快照）
 * - 不引入新依赖（无 React Query / SWR）：与现有 useApi 风格一致
 * - 不可变更新：快照/回滚都基于 spread 复制，不就地改
 * - 类型友好：泛型 TData + TMutation，调用方明确返回类型
 *
 * 用法：
 *   const { mutate, pending } = useOptimisticMutation({
 *     mutate: (item) => retryDLQTask(item.task_id),
 *     onOptimistic: (items, item) => items.filter(i => i.task_id !== item.task_id),
 *     onSuccess: (res, item) => { notify('已重试', 'success'); reload(); },
 *     onError: (err, item, rollback) => { notify('重试失败', 'error'); },
 *   });
 */
import { useCallback, useRef, useState } from 'react';

export interface UseOptimisticMutationOptions<TData, TMutation, TResult> {
  /** 实际写操作（异步），返回服务器结果 */
  mutate: (mutation: TMutation, signal?: AbortSignal) => Promise<TResult>;
  /** 应用乐观更新到本地数据视图，返回新数据（不可变） */
  onOptimistic: (currentData: TData, mutation: TMutation) => TData;
  /** 成功回调（服务器返回结果 + 触发 mutation） */
  onSuccess?: (result: TResult, mutation: TMutation) => void;
  /** 失败回调（错误 + 触发 mutation + 回滚函数） */
  onError?: (error: unknown, mutation: TMutation) => void;
}

export interface UseOptimisticMutationResult<TData, TMutation> {
  /** 乐观更新后的数据视图（pending 时显示，失败回滚后清空） */
  optimisticData: TData | null;
  /** 当前是否有写操作进行中（用于禁用按钮） */
  pending: boolean;
  /** 触发写操作：先乐观应用，再实际调用 mutate */
  mutate: (data: TData, mutation: TMutation) => Promise<void>;
  /** 手动清空乐观数据（如成功后 reload 替换数据后） */
  clear: () => void;
}

export function useOptimisticMutation<TData, TMutation, TResult>(
  options: UseOptimisticMutationOptions<TData, TMutation, TResult>,
): UseOptimisticMutationResult<TData, TMutation> {
  const { mutate: mutateFn, onOptimistic, onSuccess, onError } = options;
  const [optimisticData, setOptimisticData] = useState<TData | null>(null);
  const [pending, setPending] = useState(false);
  // 备份原数据，用于失败回滚
  const rollbackRef = useRef<TData | null>(null);

  const mutate = useCallback(async (data: TData, mutation: TMutation) => {
    if (pending) return;
    setPending(true);
    // 备份 + 乐观应用
    rollbackRef.current = data;
    const optimistic = onOptimistic(data, mutation);
    setOptimisticData(optimistic);

    const controller = new AbortController();
    try {
      const result = await mutateFn(mutation, controller.signal);
      // 成功：清空乐观数据（让调用方 reload 拿到真实服务器数据）
      setOptimisticData(null);
      onSuccess?.(result, mutation);
    } catch (error) {
      // 失败：回滚到原数据 + 错误回调
      setOptimisticData(null);
      onError?.(error, mutation);
    } finally {
      setPending(false);
      rollbackRef.current = null;
    }
  }, [pending, mutateFn, onOptimistic, onSuccess, onError]);

  const clear = useCallback(() => {
    setOptimisticData(null);
    rollbackRef.current = null;
  }, []);

  return { optimisticData, pending, mutate, clear };
}

export default useOptimisticMutation;
