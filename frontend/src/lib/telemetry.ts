/** D5: 前端错误遥测 —— window.onerror / unhandledrejection 浅层低噪声上报。

设计要点（对照 CLAUDE.md 反伪实现）：
- 不阻塞页面：上报用 navigator.sendBeacon（页面卸载也丢不丢得了）+ fetch 兜底，全部 try/catch。
- 不刷屏：同类 message+stack 5s 去重窗口，避免一次崩溃刷百条。
- 不改响应语义：后端 POST /v1/errors/frontend 只统计，不回业务数据。
- 不泄露：message/stack/url 做长度截断，不含用户密钥（API Key 仅在 localStorage，不出现在错误文本里）。
- 真实闭环：手动触发错误后，error_tracker 出现对应 FE.* code（验收点）。
 */
const ENDPOINT = '/v1/errors/frontend';
const DEDUP_WINDOW_MS = 5000;
const MAX_MSG = 500;
const MAX_STACK = 2000;

let lastKey = '';
let lastTs = 0;

function makeKey(message: string, stack: string): string {
  return `${message.slice(0, 80)}::${stack.slice(0, 80)}`;
}

/** 上报一条前端错误；失败静默（遥测本身不能成为新的错误源）。 */
export function reportFrontendError(code: string, message: string, stack?: string): void {
  try {
    const msg = (message ?? '').slice(0, MAX_MSG);
    const stk = (stack ?? '').slice(0, MAX_STACK);
    const key = makeKey(msg, stk);
    const now = Date.now();
    // 5s 内同类错误去重
    if (key === lastKey && now - lastTs < DEDUP_WINDOW_MS) return;
    lastKey = key;
    lastTs = now;
    const payload = JSON.stringify({
      code: (code || 'FE.UNKNOWN').slice(0, 32),
      message: msg,
      stack: stk || undefined,
      url: typeof location !== 'undefined' ? location.href : undefined,
    });
    // 优先 sendBeacon：页面卸载/导航时也能丢出去
    if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      if (navigator.sendBeacon(ENDPOINT, blob)) return;
    }
    // 兜底 fetch（keepalive 让 unload 期间也能发）
    void fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
      mode: 'same-origin',
    }).catch(() => { /* 遥测失败不影响用户 */ });
  } catch {
    // 连上报都崩了，绝不再抛
  }
}

/** 安装全局错误监听；幂等，重复调用只装一次。返回卸载函数（测试用）。 */
export function installFrontendTelemetry(): () => void {
  if (typeof window === 'undefined') return () => { /* noop */ };
  if ((window as unknown as { __tfTelemetryInstalled?: boolean }).__tfTelemetryInstalled) {
    return () => { /* noop */ };
  }
  (window as unknown as { __tfTelemetryInstalled?: boolean }).__tfTelemetryInstalled = true;

  const onError = (event: ErrorEvent) => {
    reportFrontendError('FE.RUNTIME', event.message || 'window.onerror', event.error?.stack || event.error?.message);
  };
  const onUnhandled = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const msg = reason instanceof Error ? reason.message : typeof reason === 'string' ? reason : 'unhandledrejection';
    const stk = reason instanceof Error ? reason.stack : undefined;
    reportFrontendError('FE.PROMISE', msg, stk);
  };
  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onUnhandled);
  return () => {
    window.removeEventListener('error', onError);
    window.removeEventListener('unhandledrejection', onUnhandled);
    (window as unknown as { __tfTelemetryInstalled?: boolean }).__tfTelemetryInstalled = false;
  };
}
