import { useState, useEffect } from 'react';
import { fetchTasks, cancelTask, retryTask, notify } from '../api';
import { Skeleton, ErrorRetry } from '../components/Feedback';
import { Skeleton as SkeletonStructured } from '../components/Skeleton';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/Button';
import { TaskProgress } from '../components/TaskProgress';
import { useApi } from '../hooks/useApi';
import { useTaskProgress } from '../hooks/useTaskProgress';
import { useVirtualList } from '../hooks/useVirtualList';
import { useT } from '../i18n';
import type { Task } from '../api';

const TASK_ROW_H = 52;
const TASK_CONTAINER_H = 560;
const COL_COUNT = 9;

export function TasksPage() {
  // P1-6 i18n：响应式 t()
  const t = useT();
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
        return <span className="tf-badge tf-badge-success"><span className="tf-dot" style={{ background: 'var(--success)' }} />{t('tasks.statusCompleted')}</span>;
      case 'processing':
        return <span className="tf-badge tf-badge-warning"><span className="tf-dot tf-dot-pulse" style={{ background: 'var(--warning)' }} />{t('tasks.statusProcessing')}</span>;
      case 'error':
        return <span className="tf-badge tf-badge-danger"><span className="tf-dot" style={{ background: 'var(--danger)' }} />{t('tasks.statusError')}</span>;
      case 'pending':
        return <span className="tf-badge tf-badge-info"><span className="tf-dot" style={{ background: 'var(--info)' }} />{t('tasks.statusPending')}</span>;
      case 'cancelled':
        return <span className="tf-badge tf-badge-neutral"><span className="tf-dot" style={{ background: 'var(--text-muted)' }} />{t('tasks.statusCancelled')}</span>;
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
            {t('tasks.title')}
            <span className="title-badge">{t('tasks.total', { n: total })}</span>
          </h1>
          <p className="page-desc">{t('tasks.desc')}</p>
        </div>
        <div className="tasks-filter-bar">
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            className="tf-select"
            aria-label="按状态过滤"
          >
            <option value="">{t('tasks.filterAll')}</option>
            <option value="pending">⏳ {t('tasks.statusPending')} (Pending)</option>
            <option value="processing">⚡ {t('tasks.statusProcessing')} (Processing)</option>
            <option value="completed">✅ {t('tasks.statusCompleted')} (Completed)</option>
            <option value="error">❌ {t('tasks.statusError')} (Error)</option>
            {/* L5 修复（审查）：P0-4 cancelled + P1-8 archived 状态入过滤（archived 冷历史可查） */}
            <option value="cancelled">⛔ {t('tasks.statusCancelled')} (Cancelled)</option>
            <option value="archived">🗄️ {t('tasks.statusArchived')} (Archived)</option>
          </select>
          <button onClick={reload} className="tf-btn tf-btn-secondary" aria-label="刷新任务列表">
            <span>🔄</span> {t('tasks.refresh')}
          </button>
        </div>
      </div>

      <div className="tf-table-container">
        {/* P2-C1: 骨架屏替代 spinner —— 首次加载时显示结构化表格行骨架 */}
        {loading && !data && (
          <div style={{ padding: '8px 12px' }}>
            <SkeletonStructured variant="rows" count={6} columns={COL_COUNT} height={20} />
          </div>
        )}

        {data && (
          <div style={{ overflowX: 'auto' }}>
            <table className="tf-table">
              <thead>
                <tr>
                  <th>{t('tasks.colId')}</th>
                  <th>{t('tasks.colStatus')}</th>
                  <th>{t('tasks.colProgress')}</th>
                  <th>{t('tasks.colModel')}</th>
                  <th style={{ minWidth: 260 }}>{t('tasks.colPrompt')}</th>
                  <th>{t('tasks.colDuration')}</th>
                  <th>调用方 IP</th>
                  <th>{t('tasks.colCreated')}</th>
                  <th>{t('tasks.colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 && !loading && !error && (
                  <tr>
                    <td colSpan={COL_COUNT}>
                      <EmptyState
                        icon="📋"
                        text={t('tasks.emptyText')}
                        hint={t('tasks.emptyHint')}
                        ctaLabel={t('tasks.emptyCta')}
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
                  {topPad > 0 && <tr style={{ height: topPad }} aria-hidden="true"><td colSpan={COL_COUNT} /></tr>}
                  {vlist.visible.map(t => (
                    <TaskRow key={t.id} task={t} onReload={reload} getStatusBadge={getStatusBadge} />
                  ))}
                  {bottomPad > 0 && <tr style={{ height: bottomPad }} aria-hidden="true"><td colSpan={COL_COUNT} /></tr>}
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

        .task-row-actions {
          display: flex;
          align-items: center;
          gap: 6px;
          white-space: nowrap;
        }
      `}</style>
    </div>
  );
}

/**
 * 单行任务组件（P0-4）：每行独立 hooks ——
 * - 运行中（pending/processing）行：useTaskProgress 驱动阶段徽章/进度条 + 「取消」按钮（幂等）；
 * - error 行：「重试」按钮（一键重投为新任务）；
 * 取消/重试操作成功后即时更新本行状态（乐观），并触发列表 reload 拉取真实数据。
 */
function TaskRow({ task, onReload, getStatusBadge }: {
  task: Task;
  onReload: () => void;
  getStatusBadge: (s: string) => React.ReactNode;
}) {
  // P1-6 i18n：响应式 t()
  const t = useT();
  const running = task.status === 'pending' || task.status === 'processing';
  const progress = useTaskProgress(task.id, { enabled: running });
  const [busy, setBusy] = useState<null | 'cancel' | 'retry'>(null);
  const [localStatus, setLocalStatus] = useState(task.status);
  // 父级轮询/reload 拉回真实状态后同步（覆盖乐观更新）
  useEffect(() => { setLocalStatus(task.status); }, [task.status]);

  const handleCancel = async () => {
    if (busy) return;
    setBusy('cancel');
    try {
      const res = await cancelTask(task.id);
      if (res.cancelled) {
        setLocalStatus('cancelled');
        notify(t('tasks.cancelOk', { id: task.id.slice(0, 8) }), 'success');
      } else {
        // 幂等命中：任务已是终态（completed/error/cancelled），未发生变更，不报错
        notify(t('tasks.cancelFinal', { id: task.id.slice(0, 8), s: res.status }), 'info');
        setLocalStatus(res.status);
      }
      onReload();
    } catch (e) {
      notify(t('tasks.cancelFail') + ': ' + (e instanceof Error ? e.message : String(e)), 'error');
    } finally {
      setBusy(null);
    }
  };

  const handleRetry = async () => {
    if (busy) return;
    setBusy('retry');
    try {
      const res = await retryTask(task.id);
      notify(t('tasks.retryOk', { id: res.task_id.slice(0, 8) }), 'success');
      onReload();
    } catch (e) {
      notify(t('tasks.retryFail') + ': ' + (e instanceof Error ? e.message : String(e)), 'error');
    } finally {
      setBusy(null);
    }
  };

  const isRunning = localStatus === 'pending' || localStatus === 'processing';

  return (
    <tr data-task-id={task.id}>
      <td>
        <code style={{ fontSize: 11.5, color: 'var(--primary-600)' }}>
          {task.id ? task.id.slice(0, 8) : '-'}
        </code>
      </td>
      <td>{getStatusBadge(localStatus)}</td>
      <td>
        <TaskProgress
          status={localStatus}
          statusDetail={progress.statusDetail}
          progress={progress.progress}
          compact
        />
      </td>
      <td>
        <span className="task-model-pill">{task.model}</span>
      </td>
      <td>
        <div className="task-prompt-text" title={task.prompt ?? undefined}>
          {task.prompt || <span style={{ color: 'var(--text-muted)' }}>-</span>}
        </div>
      </td>
      <td>
        <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>
          {task.duration_sec != null ? `${task.duration_sec.toFixed(1)}s` : '-'}
        </span>
      </td>
      <td>
        <code className="task-ip-pill" title={task.client_ip ?? '未记录'}>
          {task.client_ip ? task.client_ip : (task.client_location ?? '—')}
        </code>
      </td>
      <td style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
        {task.created_at ? new Date(task.created_at * 1000).toLocaleString() : '-'}
      </td>
      <td>
        <div className="task-row-actions">
          {isRunning && (
            <Button
              variant="danger"
              size="sm"
              loading={busy === 'cancel'}
              disabled={busy !== null && busy !== 'cancel'}
              onClick={() => void handleCancel()}
              aria-label={`取消任务 ${task.id.slice(0, 8)}`}
            >
              {t('tasks.cancel')}
            </Button>
          )}
          {localStatus === 'error' && (
            <Button
              variant="secondary"
              size="sm"
              loading={busy === 'retry'}
              disabled={busy !== null && busy !== 'retry'}
              onClick={() => void handleRetry()}
              aria-label={`重试任务 ${task.id.slice(0, 8)}`}
            >
              {t('tasks.retry')}
            </Button>
          )}
          {!isRunning && localStatus !== 'error' && (
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
          )}
        </div>
      </td>
    </tr>
  );
}