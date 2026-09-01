/**
 * 共享轮询调度器（P1-3）：所有 useApi 的 intervalMs 轮询共用一个 setInterval tick，
 * 替代每个 useApi 实例各自 setInterval（Dashboard 8 个 useApi → 8 个独立 timer → 1 个）。
 *
 * 设计：
 * - 模块级单例：1s tick（TICK_MS），遍历任务表，按各自 intervalMs 分桶触发（精度 1s，
 *   对 Dashboard 5s/15s/30s/60s 轮询无感；向后兼容：intervalMs=0 的 useApi 不注册）。
 * - 页面可见性统一管：hidden 暂停 tick（不发起无效请求），visible 立即 reload 全部任务
 *   （等价于原 useApi 各自的 visibilitychange 补拉，但只绑一次全局监听）。
 * - SSR 安全：typeof document !== 'undefined' 判断；首个任务注册启动 tick，全部注销停止。
 *
 * 不破坏 useApi 签名：useApi 仍返回 {data, loading, error, reload}，仅内部把 setInterval
 * 换成 pollingScheduler.register(intervalMs, runner)。
 */

interface PollTask {
  intervalMs: number;
  lastRun: number;
  runner: () => void;
}

const TICK_MS = 1000;

class PollingScheduler {
  private tasks = new Map<number, PollTask>();
  private nextId = 1;
  private timer: ReturnType<typeof setInterval> | null = null;
  private visible = true;

  constructor() {
    if (typeof document !== 'undefined') {
      this.visible = document.visibilityState !== 'hidden';
      document.addEventListener('visibilitychange', this.onVisibility);
    }
  }

  private onVisibility = () => {
    const wasVisible = this.visible;
    if (typeof document !== 'undefined') {
      this.visible = document.visibilityState !== 'hidden';
    }
    // 从隐藏恢复到可见：立即补拉所有任务（等价于每个 useApi 的 reload）
    if (!wasVisible && this.visible) {
      const now = Date.now();
      for (const t of this.tasks.values()) {
        t.lastRun = now;
        try {
          t.runner();
        } catch {
          // runner 内部已捕获错误（useApi.run 的 try/catch），不传播到调度器
        }
      }
    }
  };

  /** 注册一个轮询任务，返回注销函数。intervalMs<=0 不注册（向后兼容一次性请求）。 */
  register(intervalMs: number, runner: () => void): () => void {
    if (intervalMs <= 0) return () => {};
    // 注册时同步当前可见性（避免上个测试残留 visible=false 污染本轮）
    if (typeof document !== 'undefined') {
      this.visible = document.visibilityState !== 'hidden';
    }
    const id = this.nextId++;
    this.tasks.set(id, { intervalMs, lastRun: Date.now(), runner });
    this.ensureTicking();
    return () => {
      this.tasks.delete(id);
      if (this.tasks.size === 0) this.stopTicking();
    };
  }

  /** 当前注册任务数（测试用，验证共享调度）。 */
  size(): number {
    return this.tasks.size;
  }

  /** 调度器是否在 tick（测试用）。 */
  isTicking(): boolean {
    return this.timer !== null;
  }

  private ensureTicking(): void {
    if (this.timer !== null || typeof document === 'undefined') return;
    this.timer = setInterval(() => {
      if (!this.visible) return;
      const now = Date.now();
      for (const t of this.tasks.values()) {
        if (now - t.lastRun >= t.intervalMs) {
          t.lastRun = now;
          try {
            t.runner();
          } catch {
            // runner 内部已捕获，不传播
          }
        }
      }
    }, TICK_MS);
  }

  private stopTicking(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}

/** 模块级共享调度器单例：所有 useApi 的轮询共用一个 setInterval，失焦统一暂停。 */
export const pollingScheduler = new PollingScheduler();
