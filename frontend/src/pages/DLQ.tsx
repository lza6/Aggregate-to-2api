import { useState } from 'react';
import { fetchDLQ, retryDLQTask, clearDLQ, notify } from '../api';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { DLQItem } from '../api';

export function DLQPage() {
  const { data, loading, error, reload } = useApi(() => fetchDLQ(), { intervalMs: 0 });
  // P-UI-3: 操作级 busy 态——重试中/清空中按钮禁用，杜绝连点重复请求
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const items: DLQItem[] = data?.items ?? [];

  const handleRetry = async (taskId: string) => {
    if (retryingId) return; // 已有一个在飞，禁止并发重试
    setRetryingId(taskId);
    try {
      const result = await retryDLQTask(taskId);
      notify(result?.message ?? '重试已触发', 'success');
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
      notify('死信队列已清空', 'success');
    } catch (e) {
      notify('清空失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    }
    setClearing(false);
    reload();
  };

  if (error && !data) {
    return (
      <div>
        <h1 style={{ fontSize: 22, marginBottom: 16 }}>死信队列</h1>
        <ErrorRetry message={error.message} onRetry={reload} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>死信队列 {items.length > 0 && <span style={{ fontSize: 13, color: '#6b7280' }}>共 {items.length} 条</span>}</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={reload} disabled={loading} className="btn">刷新</button>
          {items.length > 0 && (
            <button onClick={handleClear} disabled={clearing} className="btn btn-danger">
              {clearing ? '清空中...' : '清空全部'}
            </button>
          )}
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task ID</th>
              <th>模型</th>
              <th>错误</th>
              <th>重试次数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const busy = retryingId === item.task_id;
              return (
                <tr key={item.task_id}>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{item.task_id?.slice(0, 8)}</td>
                  <td>{item.model ?? '-'}</td>
                  <td title={item.error ?? ''} style={{ color: '#ef4444', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.error ?? '-'}</td>
                  <td>{item.attempts ?? '-'}</td>
                  <td>
                    <button
                      onClick={() => handleRetry(item.task_id)}
                      disabled={busy || retryingId !== null || clearing}
                      className="btn btn-sm"
                    >
                      {busy ? '重试中...' : '重试'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {loading && !data && <Skeleton lines={4} height={14} />}
        {!loading && !items.length && !error && <Empty text="死信队列为空" hint="重试耗尽的任务会进入这里" />}
      </div>
      <style>{`
        .btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; cursor: pointer; background: #e8eaf1; color: #1f2430; }
        .btn:disabled { opacity: .55; cursor: not-allowed; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-danger:disabled { background: #f87171; }
        .btn-sm { background: #6b8aff; color: #fff; padding: 4px 12px; font-size: 12px; border-radius: 6px; border: none; cursor: pointer; }
        .btn-sm:disabled { background: #93a7ff; }
        .table-wrap { overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #d1d5e0; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px 12px; border-bottom: 1px solid #d1d5e0; color: #6b7280; font-weight: 600; font-size: 12px; background: #f8f9fc; }
        td { padding: 10px 12px; border-bottom: 1px solid #d1d5e0; }
        tr:last-child td { border-bottom: none; }
        @media (prefers-color-scheme: dark) {
          .table-wrap { background: #1e2132; border-color: #2d3050; }
          th { background: #252840; border-color: #2d3050; color: #8b8fa3; }
          td { border-color: #2d3050; }
          .btn { background: #2d3050; color: #e1e4ed; }
        }
      `}</style>
    </div>
  );
}
