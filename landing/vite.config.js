import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'node:fs'

// 版本号 build-time 从 package.json 注入 __APP_VERSION__，页脚版本随构建自动更新，
// 杜绝硬编码版本漂移（参照 frontend/vite.config.ts 范式）。
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

export default defineConfig({
  base: '/',
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: '0.0.0.0',
    port: 4590
  },
  build: {
    // three 独立 chunk ~189kb gzip 是真 3D 的必然体积，懒加载不在 LCP 关键路径；
    // 抬高警告阈值避免 CI 噪声，诚实保留体积不改最小化策略
    chunkSizeWarningLimit: 800
  }
})
