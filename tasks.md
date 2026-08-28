# 任务拆解与可验收节点：UI/UX 改进闭环

## 任务节点清单

| 节点 ID | 目标 | 负责范围 | 交付物 | 验证方式 | 完成标准 | 状态 |
|---|---|---|---|---|---|---|
| **T-1** | 响应式与 375px 窄屏适配 | `api/docs.html`, `frontend/src/index.css` | 375px 媒体查询与卡片/图表样式 | 浏览器/样式测试 | iPhone SE 窄屏无水平溢出 | **done** |
| **T-2** | 渐进式生图步骤指示器 | `api/docs.html` | `.pg-stepper` 状态机与样式 | 任务状态轮询与模拟 | 4 个阶段按状态流转 | **done** |
| **T-3** | 行动化错误提示与一键复制 | `api/docs.html`, `Feedback.tsx`, `ChatPlayground.tsx` | 场景化错误卡片与一键复制 | 模拟 429 与 401 请求 | 限流提示切换备用引擎，401 提供一键命令复制 | **done** |
| **T-4** | WebSocket 指数退避重连与心跳 | `frontend/src/pages/Logs.tsx`, `index.css` | 断线重连与心跳指示器 | WS 连接断开与恢复测试 | 重连动画生效，心跳时间实时更新 | **done** |
| **T-5** | 自动化测试与全量构建 | `tests/test_ui_ux_improvements.py`, `frontend` | 单元测试套件与生产产物 | `pytest`, `npm run build` | 100% 测试通过，0 TS 编译错误 | **done** |
| **T-6** | HTML 自包含交互式变更报告 | `docs/reports/ui-ux-v6.3.3-change-report.html` | 自包含 HTML 报告 + 交互测验 | 浏览器渲染检查与评分测试 | 得分计算正确，自包含零外部依赖 | **in_progress** |
