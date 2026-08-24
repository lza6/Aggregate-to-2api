## v4.2.1 UI 精简 + 画廊 Prompt 复用 + SSE 事件钩子

### UI 去重美化（docs.html）
- 导航 12 -> 8 tabs：移除"快速开始/API Playground/任务中心/用量统计"四个顶层入口
- "文档与任务"聚合：docs-sec 点击同时展示 API 文档 + 任务中心 + 用量统计
- "在线使用"保留唯一生成入口（文生图/图生图）
- stats-grid 只随页面内容出现，不再每个 tab 重复

### 画廊 Prompt 深度复用（黑匣子全开）
- 每件作品 alt 携带 prompt
- 灯箱新增 3 个按钮：复制 Prompt、复制 Prompt 并重填（自动填入文生图输入框并切到在线使用）
- 原"复制图片链接"/"导出高清原图"保留
- 复用 copyTextSafe() 三级 fallback

### SSE 事件钩子（worker 4 处）
- 入队 -> status: pending + queue_pos
- 开始处理 -> status: processing + phase solving
- token 获取 -> progress: generating
- 终态 -> result / error（自动结束事件流）
- 与 /v1/tasks/{id}/events + Last-Event-ID 断线补偿闭环

### 测试
- test_terms 集成 6 passed（lifespan asynccontextmanager 修复）
- test_adaptive_router 14 passed
- test_main_validation/test_edit_mutex 全绿
- tests/integration/ 全绿（含 full_flow/async_flow 修复 minimaxh3->nanobanana 对齐 bootstrap）
- 生产 /v1/healthz OK / workers 10 / gallery 50