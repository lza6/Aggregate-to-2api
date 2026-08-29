import { fetchTasks } from '../api';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import { useState } from 'react';
import type { Task } from '../api';

export function TasksPage() {
  const [status, setStatus] = useState('');
  const { data, loading, error, reload } = useApi(
    () => fetchTasks({ limit: 50, status: status || undefined }),
    { intervalMs: 10000 },
  );

  const tasks: Task[] = data?.items ?? [];
  const total = data?.total ?? 0;

  const getStatusBadge = (s: string) => {
    switch (s) {
      case 'completed':
        return <span className="tf-badge tf-badge-success"><span className="tf-dot" style={{ background: 'var(--success)' }} />已完成</span>;
      case 'processing':
        return <span className="tf-badge tf-badge-warning"><span className="tf-dot tf-dot-pulse" style={{ background: 'var(--warning)' }} />处理中</span>;
      case 'error':
        return <span className="tf-badge tf-badge-danger"><span className="tf-dot" style={{ background: 'var(--danger)' }} />失败</span>;
      case 'pending':
        return <span className="tf-badge tf-badge-info"><span className="tf-dot" style={{ background: 'var(--info)' }} />排队中</span>;
      default:
        return <span className="tf-badge tf-badge-neutral">{s}</span>;
    }
  };

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;

  return (
    <div className="tasks-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            生成任务管理
            <span className="title-badge">共 {total} 条记录</span>
          </h1>
          <p className="page-desc">查询并监控所有已提交的图像生成请求、提示词、执行状态与耗时</p>
        </div>
        <div className="tasks-filter-bar">
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            className="tf-select"
            aria-label="按状态过滤"
          >
            <option value="">全部状态 (All)</option>
            <option value="pending">⏳ 排队中 (Pending)</option>
            <option value="processing">⚡ 处理中 (Processing)</option>
            <option value="completed">✅ 已完成 (Completed)</option>
            <option value="error">❌ 失败 (Error)</option>
          </select>
          <button onClick={reload} className="tf-btn tf-btn-secondary">
            <span>🔄</span> 刷新
          </button>
        </div>
      </div>

      <div className="tf-table-container">
        <div style={{ overflowX: 'auto' }}>
          <table className="tf-table">
            <thead>
              <tr>
                <th>任务 ID</th>
                <th>运行状态</th>
                <th>目标模型</th>
                <th style={{ minWidth: 260 }}>提示词 (Prompt)</th>
                <th>执行耗时</th>
                <th>调用方 IP</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(t => (
                <tr key={t.id}>
                  <td>
                    <code style={{ fontSize: 11.5, color: 'var(--primary-600)' }}>
                      {t.id ? t.id.slice(0, 8) : '-'}
                    </code>
                  </td>
                  <td>{getStatusBadge(t.status)}</td>
                  <td>
                    <span className="task-model-pill">{t.model}</span>
                  </td>
                  <td>
                    <div className="task-prompt-text" title={t.prompt}>
                      {t.prompt || <span style={{ color: 'var(--text-muted)' }}>-</span>}
                    </div>
                  </td>
                  <td>
                    <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>
                      {t.duration_sec != null ? `${t.duration_sec.toFixed(1)}s` : '-'}
                    </span>
                  </td>
                  <td>
                    <code className="task-ip-pill" title={t.client_ip ?? '未记录'}>
                      {t.client_ip ? t.client_ip : (t.client_location ?? '—')}
                    </code>
                  </td>
                  <td style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                    {t.created_at ? new Date(t.created_at * 1000).toLocaleString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {loading && !data && (
          <div style={{ padding: '16px 20px' }}>
            <Skeleton lines={5} height={20} />
          </div>
        )}
        {!loading && !tasks.length && !error && (
          <Empty text="未找到相关任务" hint="提交生成请求后，任务状态将实时在此更新" />
        )}
      </div>

      <style>{`
        .tasks-container {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .tasks-filter-bar {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .task-model-pill {
          display: inline-block;
          font-size: 11.5px;
          font-weight: 500;
          color: var(--text-secondary);
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          padding: 2px 8px;
          border-radius: var(--radius-sm);
        }

        .task-prompt-text {
          max-width: 380px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12.5px;
          color: var(--text-primary);
        }

        .task-ip-pill {
          display: inline-block;
          font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
          font-size: 11px;
          color: var(--primary-500);
          background: var(--primary-50);
          border: 1px solid var(--primary-100);
          padding: 2px 7px;
          border-radius: var(--radius-sm);
          white-space: nowrap;
        }
      `}</style>
    </div>
  );
}
