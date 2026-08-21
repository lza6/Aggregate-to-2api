# 实施计划：前端 P 系列（002-frontend-p-series）

## 技术栈

- React 19 + TypeScript 5.7 + Vite 6（现有，不变）
- 数据层：自建 `hooks/useApi.ts`（~80 行）——不引入 TanStack Query
  - 理由：6 页全是「单请求 + 间隔轮询」模式，Query 的缓存失效/变更管理用不上；
    新依赖 gzip ~13KB 且改 6 页调用面，收益不成比例。符合 Constitution 简单优先。
- 样式：沿用现有内联 `<style>` + prefers-color-scheme 模式（项目惯例，不引 CSS 框架）

## 架构

```
frontend/src/
├── api.ts                     # 既有：fetch 封装 + notify()（保留）
├── hooks/
│   └── useApi.ts              # 新：统一数据层（fetcher + interval + 竞态防护）
├── components/
│   ├── Feedback.tsx           # 新：Skeleton / Empty / ErrorRetry
│   ├── ToastHost.tsx          # 新：Toast 容器（监听 onToast，救活 notify）
│   ├── Gallery.tsx            # 改：sessionStorage 密码 + 403 处理 + 骨架屏
│   └── ...(既有组件不动)
├── pages/
│   ├── Dashboard.tsx          # 改：useApi + sessionStorage 画廊密码
│   ├── Providers.tsx          # 改：useApi + 三态
│   ├── Tasks.tsx              # 改：useApi + 三态
│   ├── Accounts.tsx           # 改：useApi + 结构化卡片 + 进度条
│   ├── Logs.tsx               # 不动（WebSocket 页，非轮询）
│   └── DLQ.tsx                # 改：useApi + 按钮 busy 态 + Toast
├── App.tsx                    # 改：React.lazy + Suspense
└── main.tsx                   # 不动
vite.config.ts                 # 改：manualChunks
```

## 关键设计

### useApi 竞态防护
useRef 存「当前生效的请求序号」；响应回来时序号不匹配则丢弃。
卸载时 clearInterval + 标记 unmounted（过期响应不再 setState）。

### 画廊密码流
1. Gallery 挂载 → 读 sessionStorage('galleryPwd')
2. undefined → 初始加载探测（不带密码）→ 403 → 弹框
3. 提交 → 存 sessionStorage → 重新加载
4. 403（密码错）→ 清 sessionStorage → 弹框 + 「密码错误」提示
（后端 /v1/gallery 403 语义：未带或带错密码，见 api/main.py:1226）

### Toast 环形闭合
api.ts 已有 notify()/onToast()（当前无人监听 = 死代码）。
ToastHost 挂 Layout：onToast 订阅 → state 队列（cap 4）→ 3s 自动退场 → 手动关。

### Bundle 分包
manualChunks：{ react: [react, react-dom, scheduler], router: [react-router-dom],
chart: [recharts + d3 依赖] } —— vendor 与业务代码分离；
非首屏路由（providers/tasks/accounts/logs/dlq）React.lazy。
预期：首屏 index chunk ≈ react+router+Dashboard+Gallery ≈ 150-200KB；
recharts（~400KB 未压缩）只随懒加载页拆出。

## 任务顺序（依赖链）

P-GALLERY → P-UI-1（useApi）→ P-UI-2（Feedback/Toast）→ P-UI-3（DLQ 交互）
→ P-UI-4（Accounts 结构化）→ P-UI-5（bundle）→ 构建验证 → 部署
（每步可独立构建通过；P-UI-1 是 P-UI-2/3/4 的地基）

## 风险

- React.lazy 与 StaticFiles(html=True) 的 SPA 回退：Vite 构建产物是多 JS 文件，
  FastAPI mount 目录直出——懒加载 chunk 按相对路径请求，/admin/assets/* 静态可达 ✅
  但刷新 /admin/tasks 深链会 404（StaticFiles 无 SPA fallback）——**维持现状**：
  现有 BrowserRouter 本就有此问题，本次不扩大范围（记录为已知限制，后续可加 catch-all）。
