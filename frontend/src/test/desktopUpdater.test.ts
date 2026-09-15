// src/test/desktopUpdater.test.ts — P1-11 自升级检查模块测试。
// 验收：
// - 浏览器环境（无 __TAURI_INTERNALS__）→ 零副作用：不 import/不执行/不 warn
// - 无 window（SSR-ish）→ 安全返回
// 注：Tauri 真实路径依赖宿主插件（@tauri-apps/plugin-updater），仅在打包 webview 内可用，
//    属运行时集成（人工/端到端验证），单测只保证浏览器降级零回归 + 异常安全。
import { describe, it, expect, vi, afterEach } from 'vitest';

const { maybeCheckForDesktopUpdate } = await import('../lib/desktopUpdater');

describe('desktopUpdater 浏览器降级', () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it('无 __TAURI_INTERNALS__ 标记 → 静默返回，不引入未处理的 rejection', async () => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const unhandled: unknown[] = [];
    const onRej = (e: PromiseRejectionEvent) => unhandled.push(e.reason);
    window.addEventListener('unhandledrejection', onRej);

    await maybeCheckForDesktopUpdate();
    await new Promise(r => setTimeout(r, 50));

    window.removeEventListener('unhandledrejection', onRej);
    expect(warnSpy).not.toHaveBeenCalled();
    expect(unhandled.length).toBe(0);
  });
});