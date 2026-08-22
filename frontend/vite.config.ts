import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// P-UI-5: vendor 分包 —— react 系 / router / 图表库分离，配合 App.tsx 路由懒加载
// base=/admin/ —— 后端以 StaticFiles 挂载于 /admin，资源必须用该前缀（否则根路径 404）
export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'scheduler'],
          'vendor-router': ['react-router-dom'],
          'vendor-chart': ['recharts'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/v1': 'http://127.0.0.1:8100',
      '/metrics': 'http://127.0.0.1:8100',
    },
  },
})
