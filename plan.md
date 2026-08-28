# 实施与架构方案：UI/UX 体验改进 (v6.3.3)

## 1. 架构约束与数据流
- **文档端 (`api/docs.html` / `deploy/api/docs.html`)**：单文件纯原生 HTML/CSS/JS 架构，依赖自身 CSS Custom Properties 进行主题与布局渲染，不引入构建工具。
- **管理端 (`frontend/src/*`)**：React 18 + Vite + TypeScript，全局状态通过 React Hooks (`useApi`) 与 WebSocket 原生长连接同步。

## 2. 核心实施方案与逻辑设计

### 方案 A：移动端 375px 窄屏适配
- 在 `docs.html` 和 `frontend/src/index.css` 中引入专属 `@media (max-width: 375px)` 断点；
- 统计卡片网格降级为 `grid-template-columns: 1fr` 单列，隐藏次要辅助说明（`.delta`），突出核心指标；
- 图表条状高度从 120px 压缩至 80px，字号降为 9px~11.5px，保证在 iPhone SE 上完全适配；
- 顶部导航栏与标题栏支持 `flex-wrap`，API Key 徽章增加 `text-overflow: ellipsis`。

### 方案 B：渐进式生图步骤状态机
- 设计 `.pg-stepper` 组件，包含 4 个离散阶段：
  1. `step-queue` (排队中)：任务创建成功后默认点亮；
  2. `step-turnstile` (Turnstile 求解)：轮询第 2 次后任务仍为 pending 时自动流转；
  3. `step-render` (上游渲染)：任务状态变为 `processing` 时点亮；
  4. `step-distribute` (下载分发)：状态变为 `completed` 并下载/渲染图片时点亮。
- 采用 SSE (`/v1/events/tasks`) 优先推送 + 指数短轮询兜底，双通道状态同步。

### 方案 C：可行动化错误提示 (Actionable Error UX)
- 错误分类拦截器：
  - **429 / 限流**：自动识别并在错误卡片中提示“当前提供商繁忙，已为您自动切换至备用引擎”，并给出降级模型建议；
  - **401 / 未配置 Key**：自动格式化标准 `curl` 调用命令，提供一键复制按钮与 `execCommand` 安全兜底。

### 方案 D：WebSocket 健壮性与心跳保活
- **指数退避重连**：`Math.min(1000 * Math.pow(1.5, reconnectCount), 10000)`；
- **状态流转**：`disconnected` $\to$ `reconnecting`（带 Spinner 旋转动画） $\to$ `connected`（重置计数器）；
- **心跳保活**：每 10 秒向服务端发送 `{ type: 'ping' }`，记录 `lastHeartbeat` 时间戳并渲染到页面顶部。

## 3. 回滚与兼容策略
- 若 CSS 适配引起其它视口异常，可随时恢复原有媒体查询断点；
- WebSocket 采用渐进增强设计，若 WS 协议不可用，核心数据依然通过 HTTP 短轮询正常加载。
