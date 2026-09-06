import { fetchTasks } from '../api';
import { Skeleton, ErrorRetry } from '../components/Feedback';
import { Skeleton as SkeletonStructured } from '../components/Skeleton';
import { EmptyState } from '../components/EmptyState';
import { useApi } from '../hooks/useApi';
import { useVirtualList } from '../hooks/useVirtualList';
import { useState, useEffect } from 'react';
import type { Task } from '../api';

const TASK_ROW_H = 52;
const TASK_CONTAINER_H = 560;

export function TasksPage() {
  const [status, setStatus] = useState('');
  const { data, loading, error, reload } = useApi(
    () => fetchTasks({ limit: 50, status: status || undefined }),
    { intervalMs: 10000 },
  );

  // v7.7 UX P1：状态筛选变化立即拉取（此前只改 state，最长要等 10s 轮询才反映，用户会判定"筛选坏了"）
  useEffect(() => { void reload(); }, [status, reload]);

  const tasks: Task[] = data?.items ?? [];
  const total = data?.total ?? 0;

  // P2-C1: 大列表虚拟化 —— 50+ 行任务列表用虚拟滚动减少 DOM 节点
  // hooks 顺序恒定：在条件 return 之前调用
  const vlist = useVirtualList(tasks, { itemHeight: TASK_ROW_H, containerHeight: TASK_CONTAINER_H, overscan: 6 });
  const topPad = vlist.startIndex * TASK_ROW_H;
  const bottomPad = (tasks.length - vlist.endIndex) * TASK_ROW_H;

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
          <button onClick={reload} className="tf-btn tf-btn-secondary" aria-label="刷新任务列表">
            <span>🔄</span> 刷新
          </button>
        </div>
      </div>

      <div className="tf-table-container">
        {/* P2-C1: 骨架屏替代 spinner —— 首次加载时显示结构化表格行骨架 */}
        {loading && !data && (
          <div style={{ padding: '8px 12px' }}>
            <SkeletonStructured variant="rows" count={6} columns={7} height={20} />
          </div>
        )}

        {data && (
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
                {tasks.length === 0 && !loading && !error && (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState
                        icon="📋"
                        text="未找到相关任务"
                        hint="提交生成请求后，任务状态将实时在此更新"
                        ctaLabel="前往生成"
                        onCta={() => { window.location.hash = ''; window.location.pathname = '/admin/generate'; }}
                      />
                    </td>
                  </tr>
                )}
              </tbody>
              {/* 虚拟化滚动体：把可见行单独渲染在 tfoot 之外的虚拟容器中。
                  保留 thead 固定 + 虚拟滚动体避免 50+ 行 DOM 堆积。 */}
              {tasks.length > 0 && (
                <tbody
                  ref={vlist.containerRef as unknown as React.Ref<HTMLTableSectionElement>}
                  onScroll={vlist.onScroll}
                  style={{ display: 'block', maxHeight: TASK_CONTAINER_H, overflowY: 'auto' }}
                >
                  {topPad > 0 && <tr style={{ height: topPad }} aria-hidden="true"><td colSpan={7} /></tr>}
                  {vlist.visible.map(t => (
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
                        <div className="task-prompt-text" title={t.prompt ?? undefined}>
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
                  {bottomPad > 0 && <tr style={{ height: bottomPad }} aria-hidden="true"><td colSpan={7} /></tr>}
                </tbody>
              )}
            </table>
          </div>
        )}

        {loading && data && (
          <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-muted)' }}>
            <Skeleton lines={1} height={12} />
          </div>
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
