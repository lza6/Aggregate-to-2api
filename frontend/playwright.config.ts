import { defineConfig } from '@playwright/test';

/**
 * P1-14 视觉探针（尽力而为）：
 * - 运行对象：自托管前端 build 或本地 dev server（默认 http://127.0.0.1:8100，前端挂载于 /admin）。
 * - 服务未起时探针只能验证静态骨架；重试按钮等依赖后端 run 状态的断言在有 session 时才会触发。
 * - 截图输出 frontend/artifacts/（已 gitignore，不入库）。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  workers: 1,
  outputDir: 'artifacts/test-results',
  reporter: [['list']],
  use: {
    baseURL: process.env.TF_PW_URL ?? 'http://127.0.0.1:8100',
    headless: true,
  },
});
