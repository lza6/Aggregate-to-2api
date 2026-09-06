import { useState } from 'react';
import { fetchDLQ, retryDLQTask, clearDLQ, notify } from '../api';
import { Skeleton, ErrorRetry } from '../components/Feedback';
import { Skeleton as SkeletonStructured } from '../components/Skeleton';
import { EmptyState } from '../components/EmptyState';
import { useOptimisticMutation } from '../hooks/useOptimisticMutation';
import { useApi } from '../hooks/useApi';
import type { DLQItem } from '../api';

export function DLQPage() {
  const { data, loading, error, reload } = useApi(() => fetchDLQ(), { intervalMs: 0 });
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const items: DLQItem[] = data?.items ?? [];

  // P2-C1: 乐观更新 —— 重试 DLQ 任务时，立即从列表中移除该任务（视觉反馈）
  // 失败回滚（清空 optimisticData → 列表恢复原状），成功后 reload 拉真实数据
  const optimistic = useOptimisticMutation<DLQItem[], string, unknown>({
    mutate: (taskId) => retryDLQTask(taskId),
    onOptimistic: (list, taskId) => list.filter(i => i.task_id !== taskId),
    onSuccess: (_res, taskId) => {
      notify(`重试任务 ${taskId.slice(0, 8)} 已触发`, 'success');
      setRetryingId(null);
      reload();
    },
    onError: (err, _taskId) => {
      notify('重试失败: ' + (err instanceof Error ? err.message : String(err)), 'error');
      setRetryingId(null);
    },
  });

  const handleRetry = async (item: DLQItem) => {
    if (retryingId) return;
    setRetryingId(item.task_id);
    await optimistic.mutate(items, item.task_id);
  };

  const handleClear = async () => {
    if (clearing) return;
    if (!confirm('确定清空死信队列？此操作不可恢复。')) return;
    setClearing(true);
    try {
      await clearDLQ();
      notify('死信队列已成功清空', 'success');
    } catch (e) {
      notify('清空失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    }
    setClearing(false);
    reload();
  };

  if (error && !data) {
    return (
      <div className="dlq-container">
        <div className="page-header">
          <h1 className="page-title">死信队列 (DLQ)</h1>
        </div>
        <ErrorRetry message={error.message} onRetry={reload} />
      </div>
    );
  }

  // 乐观视图：重试期间移除对应项；其余项正常显示
  const visibleItems = optimistic.optimisticData ?? items;

  return (
    <div className="dlq-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            死信队列 (DLQ)
            {items.length > 0 && <span className="title-badge">{items.length} 个异常堆积</span>}
          </h1>
          <p className="page-desc">由于重试耗尽、上游提供商严重封禁或参数错误而中止的任务隔离与恢复区</p>
        </div>
        <div className="dlq-actions">
          <button onClick={reload} disabled={loading} className="tf-btn tf-btn-secondary" aria-label="刷新死信队列">
            <span>🔄</span> 刷新
          </button>
          {items.length > 0 && (
            <button onClick={handleClear} disabled={clearing} className="tf-btn tf-btn-danger" aria-label="清空所有死信任务">
              {clearing ? '清空中...' : '🗑️ 清空所有死信'}
            </button>
          )}
        </div>
      </div>

      <div className="tf-table-container">
        {/* P2-C1: 首次加载骨架屏 */}
        {loading && !data && (
          <div style={{ padding: '8px 12px' }}>
            <SkeletonStructured variant="rows" count={5} columns={5} height={20} />
          </div>
        )}

        {data && (
          <div style={{ overflowX: 'auto' }}>
            <table className="tf-table">
              <thead>
                <tr>
                  <th>任务 ID</th>
                  <th>目标模型</th>
                  <th style={{ minWidth: 320 }}>错误原因详情</th>
                  <th>已重试次数</th>
                  <th style={{ textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {visibleItems.map((item) => {
                  const busy = retryingId === item.task_id || optimistic.pending;
                  return (
                    <tr key={item.task_id} aria-busy={busy ? 'true' : undefined}>
                      <td>
                        <code style={{ fontSize: 11.5, color: 'var(--primary-600)' }}>
                          {item.task_id?.slice(0, 8)}
                        </code>
                      </td>
                      <td>
                        <span className="dlq-model-tag">{item.model ?? '-'}</span>
                      </td>
                      <td>
                        <div className="dlq-error-text" title={item.error ?? ''}>
                          {item.error ?? '-'}
                        </div>
                      </td>
                      <td>
                        <span className="dlq-attempts-badge">{item.attempts ?? '-'} 次</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          onClick={() => handleRetry(item)}
                          disabled={busy || retryingId !== null || clearing}
                          className="tf-btn tf-btn-primary tf-btn-sm"
                          aria-label={`重新入队任务 ${item.task_id?.slice(0, 8)}`}
                        >
                          {busy ? '重试中...' : '⚡ 重新入队'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {loading && data && (
          <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-muted)' }}>
            <Skeleton lines={1} height={12} />
          </div>
        )}
        {!loading && !items.length && !error && (
          <EmptyState
            icon="📭"
            text="死信队列为空"
            hint="集群运行健康，所有重试耗尽的任务会自动捕获并隔离于此"
            ctaLabel="刷新检查"
            onCta={reload}
          />
        )}
      </div>

      <style>{`
        .dlq-container {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .dlq-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .dlq-model-tag {
          font-size: 11.5px;
          font-weight: 500;
          color: var(--text-secondary);
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          padding: 2px 8px;
          border-radius: var(--radius-sm);
        }

        .dlq-error-text {
          color: var(--danger);
          font-size: 12.5px;
          max-width: 460px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-family: ui-monospace, monospace;
        }

        .dlq-attempts-badge {
          font-size: 12px;
          font-variant-numeric: tabular-nums;
          font-weight: 600;
          color: var(--text-secondary);
        }
      `}</style>
    </div>
  );
}
