/**
 * useTaskProgress — 单任务实时进度 hook（P0-4）
 *
 * 为任务列表运行行 / 生成页提交卡提供「阶段徽章流转（queued→solving→generating）+ 简化进度条」。
 *
 * 数据源选型（最小接线，保留可换 SSE）：
 * - 主路径 = 轮询 `GET /v1/tasks/{id}`：可靠拿到顶层状态（pending/processing/completed/error/cancelled），
 *   命中终态即停。但 GET 响应（task_to_public）不含 status_detail/progress 字段（它们只在 SSE 事件负载），
 *   故轮询路径用 `mapStatusToDetail` 做状态映射兜底（pending→queued/5，终态→100）。
 * - 增强路径 = SSE 订阅 `/v1/tasks/{id}/events`（真实浏览器 EventSource 存在时才开，与 Generate 页
 *   既有 startTxtSse 同一通道）：收到 status 事件即用精确的 status_detail/progress（solving=30/generating=80）
 *   覆盖映射值；SSE 断线 / jsdom 无 EventSource → 纯轮询兜底，行为不变。
 *
 * 设计约束：
 * - 仅 `enabled && taskId` 时启动（列表页只对 pending/processing 行启用，避免已终态行空轮询）。
 * - 每轮请求带自增序号防竞态；卸载 / 停用即停轮询 + 关 SSE。
 * - 不做乐观状态机：终态一律以后端为准。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchTask } from '../api';

export interface TaskProgressState {
  /** 顶层任务状态：pending/processing/completed/error/cancelled；null=尚未拉到 */
  status: string | null;
  /** 阶段徽章：queued/solving/generating/completed/cancelled；null=未知（渲染层回退「运行中」） */
  statusDetail: string | null;
  /** 阶段进度 0-100；null=未知（渲染层回退不确定进度条） */
  progress: number | null;
  /** 是否仍订阅中（运行中 + 已连上轮询/SSE） */
  running: boolean;
}

export interface UseTaskProgressOptions {
  /** 任务非运行态时跳过订阅（列表页只对 pending/processing 行启用） */
  enabled?: boolean;
  /** 轮询间隔 ms（默认 2000） */
  pollIntervalMs?: number;
}

const TERMINAL = new Set(['completed', 'error', 'cancelled']);

/** 运行态 → 阶段徽章/进度的兜底映射（轮询 /v1/tasks/{id} 只拿得到 status）。 */
function mapStatusToDetail(status: string): { statusDetail: string | null; progress: number | null } {
  switch (status) {
    case 'pending':
      return { statusDetail: 'queued', progress: 5 };
    case 'processing':
      return { statusDetail: null, progress: null };
    case 'completed':
      return { statusDetail: 'completed', progress: 100 };
    case 'cancelled':
      return { statusDetail: 'cancelled', progress: 100 };
    default:
      return { statusDetail: null, progress: null };
  }
}

export function useTaskProgress(taskId: string | null, options: UseTaskProgressOptions = {}): TaskProgressState {
  const { enabled = true, pollIntervalMs = 2000 } = options;
  const active = Boolean(taskId) && enabled;
  const [status, setStatus] = useState<string | null>(null);
  const [statusDetail, setStatusDetail] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const seqRef = useRef(0);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setRunning(false);
  }, []);

  useEffect(() => {
    if (!active) {
      stop();
      return;
    }
    const tId = taskId as string;
    const seq = ++seqRef.current;
    setRunning(true);

    const apply = (s: string, detail: string | null, p: number | null) => {
      if (seq !== seqRef.current) return;
      setStatus(s);
      setStatusDetail(detail);
      setProgress(p);
    };

    const finish = (s: string) => {
      if (seq !== seqRef.current) return;
      if (TERMINAL.has(s)) apply(s, s === 'cancelled' ? 'cancelled' : s === 'completed' ? 'completed' : null, 100);
      stop();
    };

    const poll = async () => {
      try {
        const t = await fetchTask(tId);
        if (seq !== seqRef.current) return;
        if (TERMINAL.has(t.status)) {
          finish(t.status);
          return;
        }
        const mapped = mapStatusToDetail(t.status);
        apply(t.status, mapped.statusDetail, mapped.progress);
      } catch {
        // 单轮轮询失败静默（网络抖动），下一轮继续；终态兜底由 SSE result/error 或后续轮询补
      }
    };

    void poll();
    timerRef.current = setInterval(() => {
      void poll();
    }, pollIntervalMs);

    // SSE 增强：仅真实浏览器（jsdom 无 EventSource → 直接走纯轮询）。同一通道与 Generate.startTxtSse 一致。
    if (typeof EventSource !== 'undefined') {
      try {
        const es = new EventSource(`/v1/tasks/${tId}/events`);
        esRef.current = es;
        const handleStatus = (ev: MessageEvent) => {
          if (seq !== seqRef.current) return;
          try {
            const data = JSON.parse(String((ev as MessageEvent).data ?? '{}')) as {
              status?: string;
              status_detail?: string;
              progress?: number;
            };
            if (data.status_detail || typeof data.progress === 'number' || data.status) {
              apply(
                data.status ?? 'processing',
                data.status_detail ?? null,
                typeof data.progress === 'number' ? data.progress : null,
              );
            }
          } catch {
            // 坏帧忽略
          }
        };
        // 终态事件（result/error）→ 立即拉一次权威状态收尾（poll 内部命中终态会 stop）
        const handleTerminal = () => {
          void poll();
        };
        const handleDisconnect = () => {
          if (esRef.current === es) {
            es.close();
            esRef.current = null;
          }
        };
        es.addEventListener('status', handleStatus);
        es.addEventListener('result', handleTerminal);
        es.addEventListener('error', handleTerminal);
        es.onerror = handleDisconnect; // 断线：关 SSE，轮询兜底继续
      } catch {
        // EventSource 构造失败 → 纯轮询
      }
    }

    return () => {
      seqRef.current++;
      stop();
    };
  }, [active, taskId, pollIntervalMs, stop]);

  return { status, statusDetail, progress, running };
}

export default useTaskProgress;
