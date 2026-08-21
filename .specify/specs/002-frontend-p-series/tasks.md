# 任务清单：002-frontend-p-series

## Phase 1: 地基（useApi + Feedback + Toast）

- [ ] 1.1 新建 `src/hooks/useApi.ts`：fetcher/interval/竞态防护/卸载清理
- [ ] 1.2 新建 `src/components/Feedback.tsx`：Skeleton/Empty/ErrorRetry
- [ ] 1.3 新建 `src/components/ToastHost.tsx`：挂 Layout，救活 notify()
- [ ] 1.4 `tsc -b` 通过（依赖：1.1-1.3）

## Phase 2: 页面迁移（依赖 Phase 1）

- [ ] 2.1 [P] Dashboard：useApi(5s) + 画廊密码 sessionStorage（P-GALLERY）
- [ ] 2.2 [P] Providers：useApi(10s) + 三态
- [ ] 2.3 [P] Tasks：useApi(10s) + 三态
- [ ] 2.4 [P] DLQ：useApi + 按钮 busy/disabled + Toast + 二次确认（P-UI-3）
- [ ] 2.5 [P] Accounts：useApi(15s) + 结构化卡片 + 进度条 + 邮箱池表（P-UI-4）
- [ ] 2.6 Logs 页保持不动（WebSocket，非轮询）

## Phase 3: Bundle（依赖 Phase 2 全部）

- [ ] 3.1 vite.config.ts manualChunks（react/router/recharts）
- [ ] 3.2 App.tsx React.lazy + Suspense（5 个非首屏路由）
- [ ] 3.3 `npm run build`：无 500KB 告警 + 记录 chunk 体积对比

## Phase 4: 验收与部署

- [ ] 4.1 `tsc -b && npm run build` 零错误零告警
- [ ] 4.2 dev 起本地后端 + 前端，逐页点验（6 页 + 密码记住 + DLQ 连点 + Toast）
- [ ] 4.3 sync_deploy（如 dist 需同步）+ git 提交（6 个规范提交信息）
- [ ] 4.4 服务器部署：frontend dist 构建产物同步 + 容器重建 + /admin 冒烟
