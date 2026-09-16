// src/lib/desktopNotify.ts — P1-7 桌面终态通知聚合（1s 窗口合并同类型）。
//
// 原实现：Agent 页每趟 run 到终态立即发一条系统通知，批量任务同时完成会刷屏。
// 本模块把「发送」收口到一处：最近 1s 窗口内到达的终态合并为一条汇总
// （单条仍走逐条文案，保持旧行为；多条 → 「N 项任务完成：X 成功 Y 失败」）。
//
// 浏览器环境（纯前端部署/jsdom 测试）：window.__TAURI_INTERNALS__ 缺失 → 提前返回，零副作用；
// Tauri 环境：动态 import `@tauri-apps/plugin-notification`（与旧代码同通道，浏览器构建不静态依赖该包）。
export interface TaskDoneEvent {
  name: string;
  ok: boolean;
}

export interface FlushSummary {
  count: number;
  ok: number;
  fail: number;
  body: string;
}

interface Pending {
  timer: ReturnType<typeof setTimeout> | null;
  count: number;
  ok: number;
  fail: number;
  firstName: string;
}

export const AGGREGATE_WINDOW_MS = 1000;

let pending: Pending | null = null;

async function sendDesktopNotification(title: string, body: string): Promise<void> {
  if (typeof window === 'undefined' || !(window as unknown as Record<string, unknown>).__TAURI_INTERNALS__) {
    return;
  }
  try {
    const notif = await import('@tauri-apps/plugin-notification');
    const granted = await notif.isPermissionGranted();
    if (granted) {
      await notif.sendNotification({ title, body });
    }
  } catch {
    // 浏览器环境（无 Tauri 插件）静默降级——桌面通知仅桌面可用
  }
}

function flush(): FlushSummary | null {
  const p = pending;
  pending = null;
  if (!p) return null;
  if (p.timer) clearTimeout(p.timer);

  const body =
    p.count <= 1
      ? `${p.firstName} ${p.ok > 0 ? '执行成功 ✅' : '执行失败 ❌'}`
      : `${p.count} 项任务完成：${p.ok} 成功${p.fail > 0 ? `，${p.fail} 失败` : ''}`;
  const summary: FlushSummary = { count: p.count, ok: p.ok, fail: p.fail, body };
  void sendDesktopNotification(
    p.count <= 1 ? '听风AI · DAG 任务完成' : '听风AI · 批量任务完成',
    body,
  );
  return summary;
}

/**
 * 登记一条终态通知，进入 1s 聚合窗口。窗口到期（或显式 flushDesktopNotifications）
 * 一次性发送合并结果；不跨窗口合并。
 */
export function notifyTaskDone(ev: TaskDoneEvent): void {
  if (!pending) {
    pending = { timer: null, count: 0, ok: 0, fail: 0, firstName: ev.name };
    pending.timer = setTimeout(() => {
      flush();
    }, AGGREGATE_WINDOW_MS);
  }
  pending.count += 1;
  if (ev.ok) pending.ok += 1;
  else pending.fail += 1;
}

/** 立即冲刷当前窗口（测试用 / 页面卸载兜底）；无窗口返回 null。 */
export function flushDesktopNotifications(): FlushSummary | null {
  return flush();
}