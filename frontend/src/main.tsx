import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { installFrontendTelemetry } from './lib/telemetry'

// D5: 前端错误遥测 —— 启动即装全局 onerror/unhandledrejection 监听，
// 浅层低噪声上报 POST /v1/errors/frontend（不影响页面渲染与响应）。
installFrontendTelemetry()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
