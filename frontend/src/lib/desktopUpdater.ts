// src/lib/desktopUpdater.ts — P1-11 应用自升级检查（仅 Tauri 桌面环境生效）。
//
// 策略：
// - 浏览器环境（纯前端开发/部署）→ 不 import、不执行，静默无副作用（零行为变化）
// - Tauri 环境 → 动态 import `@tauri-apps/plugin-updater`，启动后异步 check()：
//   有新版 → 自动 downloadAndInstall + relaunch（无交互打扰，跟随官方推荐用法）；
//   无新版 → 静默；异常 → 吞掉只 console.warn（不干扰主流程）
// 端点/签名公钥在 tauri.conf.json plugins.updater 配置，见 desktop/src-tauri/。
export async function maybeCheckForDesktopUpdate(): Promise<void> {
  // 仅在 Tauri 运行时执行（window.__TAURI_INTERNALS__ 为 Tauri 注入的全局标记）
  if (typeof window === 'undefined' || !(window as unknown as Record<string, unknown>).__TAURI_INTERNALS__) {
    return;
  }
  try {
    const updater = await import('@tauri-apps/plugin-updater');
    const update = await updater.check();
    if (update) {
      await update.downloadAndInstall();
      // Windows 上 downloadAndInstall 后由 NSIS 被动安装模式接管，无需 relaunch 即可应用
      const { relaunch } = await import('@tauri-apps/plugin-process');
      await relaunch();
    }
  } catch (err) {
    // 自升级失败不阻断应用（网络/签名/端点异常均属可降级路径）
    console.warn('[desktopUpdater] 更新检查失败（已忽略）:', err);
  }
}
