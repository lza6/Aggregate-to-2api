import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { installFrontendTelemetry } from './lib/telemetry'
import { maybeCheckForDesktopUpdate } from './lib/desktopUpdater'

// D5: 前端错误遥测 —— 启动即装全局 onerror/unhandledrejection 监听，
// 浅层低噪声上报 POST /v1/errors/frontend（不影响页面渲染与响应）。
installFrontendTelemetry()

// P1-11: 桌面版启动后异步检查自升级（仅 Tauri 环境执行，浏览器静默无副作用）
void maybeCheckForDesktopUpdate()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
