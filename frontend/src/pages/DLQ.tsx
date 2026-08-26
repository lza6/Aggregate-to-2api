import { useState } from 'react';
import { fetchDLQ, retryDLQTask, clearDLQ, notify } from '../api';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { DLQItem } from '../api';

export function DLQPage() {
  const { data, loading, error, reload } = useApi(() => fetchDLQ(), { intervalMs: 0 });
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const items: DLQItem[] = data?.items ?? [];

  const handleRetry = async (taskId: string) => {
    if (retryingId) return;
    setRetryingId(taskId);
    try {
      const result = await retryDLQTask(taskId);
      notify(result?.detail ?? result?.message ?? '重试任务已触发', 'success');
    } catch (e) {
      notify('重试失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    }
    setRetryingId(null);
    reload();
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
          <button onClick={reload} disabled={loading} className="tf-btn tf-btn-secondary">
            <span>🔄</span> 刷新
          </button>
          {items.length > 0 && (
            <button onClick={handleClear} disabled={clearing} className="tf-btn tf-btn-danger">
              {clearing ? '清空中...' : '🗑️ 清空所有死信'}
            </button>
          )}
        </div>
      </div>

      <div className="tf-table-container">
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
              {items.map((item) => {
                const busy = retryingId === item.task_id;
                return (
                  <tr key={item.task_id}>
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
                        onClick={() => handleRetry(item.task_id)}
                        disabled={busy || retryingId !== null || clearing}
                        className="tf-btn tf-btn-primary tf-btn-sm"
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

        {loading && !data && (
          <div style={{ padding: '16px 20px' }}>
            <Skeleton lines={4} height={20} />
          </div>
        )}
        {!loading && !items.length && !error && (
          <Empty text="死信队列为空" hint="集群运行健康，所有重试耗尽的任务会自动捕获并隔离于此" />
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
