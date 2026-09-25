import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'node:fs'

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

export default defineConfig({
  base: '/',
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: '0.0.0.0',
    port: 4590,
    // Spec 009：dev 下 /v1 代理到本地 Python 转发（dev_proxy.py → 生产 HTTPS）
    // 规避本机 Node25 TLS 会话复用 ECONNRESET（Node 直连生产持续失败，Python/curl 正常）
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:4591',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 800
  }
})
