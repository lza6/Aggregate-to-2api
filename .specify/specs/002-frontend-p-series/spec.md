# 前端 P 系列规范：画廊密码记住 + 数据层统一 + 三态反馈 + 交互闭环 + 号池结构化 + Bundle 瘦身

## 问题陈述

管理面板（frontend/，React 19 + Vite 6，挂载于后端 /admin）当前存在六类生产可用性缺陷：

1. **P-GALLERY**：画廊密码仅存于 React state，刷新即丢，用户每次刷新都要重输密码。
2. **P-UI-1**：6 个页面各自手写 `useEffect + setInterval + setState` 轮询，无统一数据层——
   无缓存、无去重、无错误重试、页面切换后台轮询不停止、组件卸载后 setState 竞态。
3. **P-UI-2**：加载态只有「加载中...」文本，无骨架屏；空态/错误态/重试缺失或零散；
   Toast 容器从未被挂载到任何页面（api.ts 的 notify() 是死代码——没有组件监听它）。
4. **P-UI-3**：DLQ 重试/清空按钮无 disabled/loading 态，可被连点打出重复请求；
   下载/复制无成功反馈；危险操作只有原生 confirm()。
5. **P-UI-4**：号池页直接 `JSON.stringify` 渲染 `<pre>`，运维无法一眼读懂账号水位。
6. **P-UI-5**：单 JS chunk 636KB（gzip 187KB），超 Vite 500KB 告警线；无 manualChunks、无路由懒加载。

## 用户故事

### US1: 画廊密码记住（P-GALLERY）
作为管理面板用户，我刷新仪表盘后不想重新输入画廊密码。
**验收标准：**
- [ ] 密码存 sessionStorage（标签页级：关标签页失效，符合管理面板安全直觉）
- [ ] 刷新后画廊直接加载，不再弹密码框
- [ ] 密码错误（403）时清空已存密码并重新弹框，提示「密码错误」
- [ ] 提交密码后有 loading 反馈，防止连点

### US2: 数据层统一（P-UI-1）
作为维护者，我希望所有页面用同一套数据获取模式（缓存 + 轮询 + 错误态）。
**验收标准：**
- [ ] 方案：**降级预案 hooks/useApi**（不引入 TanStack Query——当前 6 页全是简单轮询，
  新依赖 47KB 不划算；useApi 80 行内解决，符合 Constitution「Simplicity Over Cleverness」）
- [ ] `useApi<T>(fetcher, deps, { intervalMs })` 返回 `{ data, loading, error, reload }`
- [ ] 轮询在组件卸载时停止（clearInterval）；请求竞态防护（过期响应不覆盖新响应）
- [ ] Dashboard 5s / Tasks 10s / Providers 10s / Accounts 15s / DLQ 手动刷新
- [ ] 6 页全部替换手写 useEffect+setState，无残留

### US3: 三态组件 + Toast（P-UI-2）
作为用户，我要能分清「加载中 / 空 / 出错了 + 重试」。
**验收标准：**
- [ ] 新建 components/Feedback.tsx：`Skeleton`（骨架块）/ `Empty`（空态+说明）/ `ErrorRetry`（错误+重试按钮）
- [ ] 新建 components/ToastHost.tsx：挂载到 Layout，监听 api.ts 的 onToast（救活 notify() 死代码）
- [ ] Toast 三态（success/error/info）自动 3s 消失、可手动关、最多同屏 4 条
- [ ] 每页首载骨架屏、空数据空态、失败错误+重试

### US4: 交互反馈闭环（P-UI-3）
作为用户，我点按钮要立刻看到反馈，且不能重复提交。
**验收标准：**
- [ ] DLQ 重试：按钮 loading（转圈文字）+ disabled，请求中不可再点
- [ ] DLQ 清空：二次确认（保留 confirm）+ 清空按钮 loading
- [ ] 成功/失败都走 notify() → Toast 展示
- [ ] 所有含异步操作的按钮统一 `disabled={busy}` 模式

### US5: 号池看板结构化（P-UI-4）
作为运维，我要一眼看懂号池水位，不读 JSON。
**验收标准：**
- [ ] minimaxh3 / nanobanana 各一组卡片：总数 / ok / exhausted / credits / 注册状态
- [ ] 对 target（500）的进度条（当前可用 / 目标）
- [ ] 邮箱池统计（total_registered + by_provider）小表
- [ ] 加载骨架屏 + 空态；自动补号关闭时显示提示徽标

### US6: Bundle 瘦身 + 路由懒加载（P-UI-5）
作为用户，首屏要快。
**验收标准：**
- [ ] vite.config.ts `manualChunks`：react / react-dom / react-router / recharts 分离
- [ ] App.tsx 非首屏路由 React.lazy + Suspense fallback（骨架）
- [ ] `npm run build` 无 >500KB 单 chunk 告警
- [ ] 首屏 JS（index chunk）显著小于原 636KB

## 非功能需求

- **兼容性**：React 19 + TS 5.7；后端 /admin 挂载不变（dist 输出结构不变）
- **暗色模式**：新组件沿用现有 `prefers-color-scheme` media query 模式
- **无新运行时依赖**（P-UI-1 用降级预案，不装 TanStack Query）
- **类型安全**：新组件全部 typed，`any` 仅限既有 api.ts 返回值处

## 成功指标

- `npm run build` 通过 + 无 500KB 告警
- `tsc -b` 零错误
- 6 页全部走 useApi，grep 无残留手写轮询（Logs 页 WebSocket 除外——它是 WS 不是轮询）
- 刷新 Dashboard 不再要求重输画廊密码（sessionStorage 生效）
- DLQ 按钮连点不会发出第二个请求

## 范围外

- 不做 TanStack Query 迁移（明确选择降级预案）
- 不改后端 API（/v1/* 契约不动）
- 不做移动端专项优化（现有响应式保持）
- 不做 i18n

## 澄清记录

### Q1: 密码存 sessionStorage 还是 localStorage？
**答**：sessionStorage——管理面板密码不应跨标签页/会话持久；刷新保住即可。
### Q2: Toast 容器放哪？
**答**：Layout 内固定右上角，z-index 最高，跟随所有页面。
### Q3: useApi 轮询失败怎么处理？
**答**：error 置位但轮询继续（下一轮重试）——管理面板宁可多试，不要静默断流。
