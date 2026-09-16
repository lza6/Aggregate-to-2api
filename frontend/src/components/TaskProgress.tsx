/**
 * TaskProgress — 任务阶段徽章 + 简化进度条（P0-4）
 *
 * 纯展示组件：消费 useTaskProgress 的 statusDetail/progress 或列表轮询的映射值，
 * 渲染「阶段徽章流转 + 简化进度条」。不改任何状态、不发请求。
 *
 * 渲染规则：
 * - status 为终态（completed/error/cancelled）→ 不渲染（行内已有状态徽章，避免重复）；
 * - 运行中（pending/processing）→ 已知阶段（queued/solving/generating）显示徽章+定值进度条；
 *   未知子阶段（轮询拿不到 solving/generating）→ 回退「运行中」徽章 + 不确定进度条（CSS 扫光动画）。
 * - compact：列表行内紧凑样式（细进度条、小徽章）。
 */
import type { CSSProperties } from 'react';

export interface TaskProgressProps {
  /** 顶层任务状态：pending/processing/completed/error/cancelled */
  status: string | null;
  /** 阶段徽章：queued/solving/generating/completed/cancelled（可来自 SSE 事件或状态映射） */
  statusDetail?: string | null;
  /** 阶段进度 0-100；null=未知（回退不确定进度条） */
  progress?: number | null;
  /** 紧凑模式（列表行内用，默认 false） */
  compact?: boolean;
  /** 覆盖容器样式（列表行内限宽用） */
  style?: CSSProperties;
}

const STAGE_META: Record<string, { label: string; tone: string }> = {
  queued: { label: '排队', tone: 'info' },
  solving: { label: '求解中', tone: 'warning' },
  generating: { label: '生成中', tone: 'warning' },
  completed: { label: '已完成', tone: 'success' },
  cancelled: { label: '已取消', tone: 'neutral' },
};

const TERMINAL_STATUS = new Set(['completed', 'error', 'cancelled']);

export function TaskProgress({ status, statusDetail, progress, compact = false, style }: TaskProgressProps) {
  // 终态不在此渲染（行内已有状态徽章）；仅运行态展示阶段流转
  if (!status || TERMINAL_STATUS.has(status)) return null;

  const stage = (statusDetail && STAGE_META[statusDetail]) ? STAGE_META[statusDetail] : null;
  const label = stage?.label ?? '运行中';
  const known = stage !== null && typeof progress === 'number' && progress >= 0;
  const width = known ? `${Math.max(0, Math.min(100, (progress as number)))}%` : '100%';

  const className = compact ? 'tf-task-progress tf-task-progress-compact' : 'tf-task-progress';

  return (
    <div className={className} style={style} aria-label={`任务阶段：${label}`}>
      <span className={`tf-task-stage tf-task-stage-${stage?.tone ?? 'neutral'}`}>{label}</span>
      <span
        className="tf-task-progress-track"
        role="progressbar"
        aria-label={label}
        aria-valuenow={known ? Math.round(progress as number) : undefined}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span className={known ? 'tf-task-progress-fill' : 'tf-task-progress-fill tf-task-progress-indeterminate'} style={{ width }} />
      </span>
      <style>{`
        .tf-task-progress { display: flex; flex-direction: column; gap: 4px; min-width: 108px; }
        .tf-task-stage { font-size: 11px; font-weight: 600; line-height: 1.2; }
        .tf-task-stage-info { color: var(--info); }
        .tf-task-stage-warning { color: var(--warning-text, var(--warning)); }
        .tf-task-stage-success { color: var(--success); }
        .tf-task-stage-neutral { color: var(--text-muted); }
        .tf-task-progress-track { display: block; width: 100%; height: 4px; background: var(--bg-subtle); border-radius: var(--radius-full); overflow: hidden; }
        .tf-task-progress-fill { display: block; height: 100%; background: linear-gradient(90deg, var(--primary-500) 0%, var(--primary-400, var(--primary-500)) 100%); border-radius: var(--radius-full); transition: width 0.45s cubic-bezier(0.16, 1, 0.3, 1); }
        .tf-task-progress-indeterminate { width: 40% !important; animation: tf-task-progress-slide 1.1s ease-in-out infinite; }
        .tf-task-progress-compact .tf-task-progress-track { height: 3px; }
        @keyframes tf-task-progress-slide { 0% { transform: translateX(-110%); } 100% { transform: translateX(280%); } }
      `}</style>
    </div>
  );
}

export default TaskProgress;