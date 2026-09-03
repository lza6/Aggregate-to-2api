# Feature Specification: Landing Vibe Coding 视觉升级

> 追溯型 spec（事后补档）。实现已完成，本文档结构化记录需求与验收边界。
> 对应任务：给 `landing/` 落地页（Vue 3.5 + Vite）做 Vibe Coding 视觉升级。

## Problem Statement

公开落地页 `landing/` 此前为纯静态深色页，存在三类问题：

1. **视觉陈旧**：单层深蓝底 + indigo 主调，无动效、无 3D、无层级感，与 2026 trending 的液态玻璃（Liquid Glass）美学脱节，访客首屏无记忆点。
2. **SEO 基础薄弱**：`landing/index.html` 仅含 `<title>` 与一句 `<meta description>`，缺 OG/Twitter Card/JSON-LD/canonical/robots，社交分享卡裂图、Google 富媒体结果无结构化数据。
3. **无动效与交互反馈**：Section 切换无滚动揭示，按钮无 hover spring，无鼠标跟随光晕，导航无滚动收缩，整体"死板"。

本次升级目标：在不破坏现有 API 数据流（`/v1/stats` `/v1/meta` `/v1/healthz` 等实时拉取）的前提下，引入液态玻璃调色板、Three.js 粒子流场 3D 背景、motion-v 滚动揭示动效、SEO meta/JSON-LD，使落地页达到生产级"惊艳首屏 + SEO 可读 + 移动端可用"。

## User Stories

### Story 1: 访客首屏惊艳

As a 访客
I want 首屏看到流动的粒子流场 3D 背景 + 液态玻璃卡片 + 渐变标题 + 滚动揭示动效
So that 第一眼感知到"这是一个有设计感的高级 AI 网关"，而非又一个模板站

**Acceptance Criteria:**
- [x] Hero 区有全屏 3D 粒子流场背景（~2200 粒子，天蓝↔粉珊瑚渐变，鼠标 parallax）
- [x] 标题为渐变文本，副标题淡入
- [x] 每个 Section 滚动进入视口时 fade-up 揭示（stagger）
- [x] Provider 卡片 hover spring 抬升
- [x] CTA 主按钮 spring 磁吸 hover
- [x] 导航滚动时 backdrop-blur 加深、padding 收缩

### Story 2: SEO 爬虫可读

As a 搜索引擎爬虫 / 社交平台抓取器
I want 完整的 meta 标签 + 结构化数据 + 可达的社交分享图
So that 页面能被正确索引、社交分享卡显示品牌 logo 而非裂图

**Acceptance Criteria:**
- [x] `<meta description>` 含核心关键词（150 字内）
- [x] `<meta keywords>` 覆盖 AI 图像生成/网关/OpenAI 兼容等
- [x] `<link rel="canonical">` 指向线上根 URL
- [x] OG 标签齐全（type/title/description/url/locale/image）
- [x] Twitter Card summary_large_image + image
- [x] JSON-LD SoftwareApplication 结构化数据（含 featureList/offers/version）
- [x] `<html lang>` 由 useI18n 同步 zh-CN/en
- [x] og:image/twitter:image 指向真实可达的 `/static/logo-md.png`（由 `api/routes/health.py` 注册的 FileResponse 路由服务）

### Story 3: 移动端降级可用

As a 移动端用户 / 低性能设备 / 无 WebGL 环境
I want 页面在降级条件下仍可读可用不卡顿
So that 不会因为 3D 或动效导致白屏、卡死、耗电

**Acceptance Criteria:**
- [x] WebGL 不可用 → 3D 退回 CSS aura 渐变兜底
- [x] `prefers-reduced-motion: reduce` → 所有 motion 退化为瞬时、3D 只渲染一帧静态
- [x] 移动端（max-width:768px）→ backdrop-filter blur 降到 12px、粒子数减半
- [x] `@supports not (backdrop-filter)` → 玻璃卡片退纯色
- [x] 3D 组件懒加载（`defineAsyncComponent`），three chunk 不进首屏 LCP 关键路径

## Non-Functional Requirements

### 性能（NFR-PERF）

- **LCP < 2.5s**：首屏 JS（vue + motion-v + @vueuse/core + App + Sections）gzip **≤ 150kb**（实测 90.10kb ✅）
- **three 懒加载**：three chunk（gzip 189.60kb）异步加载，不在 LCP 关键路径
- **CLS < 0.1**：3D canvas `pointer-events:none` + `position:fixed`，不挤压内容流
- **INP < 200ms**：motion 动效用 transform/opacity（compositor-friendly），不触发布局

### 可访问性（NFR-A11Y）

- 全局 `prefers-reduced-motion` 降级（禁动画）
- 3D canvas 与光晕层 `aria-hidden="true"`
- `:focus-visible` 焦点环可见
- nav `position:sticky` 不遮挡焦点跳转

### SEO（NFR-SEO）

- 完整 meta（description/keywords/robots/author/canonical/theme-color/color-scheme）
- OG + Twitter Card 双套社交 meta
- JSON-LD SoftwareApplication（成熟类型，Google 富媒体支持）
- `<html lang>` 随 i18n 切换同步
- 语义 HTML：`<header><nav><main><section><footer>`

### 安全（NFR-SEC）

- 零外部 CDN：three/motion-v/@vueuse 全部 `npm install` 本地 bundle，不引入 `<script src="https://...">`
- og:image 指向后端已注册路由（不暴露任意文件路径）

## Success Metrics

- 首屏 LCP < 2.5s（Lighthouse 移动端模拟）
- 社交分享卡显示品牌 logo（非裂图）
- `npm run build` 通过且无 chunk size 报错（three 警告已调 chunkSizeWarningLimit）
- 移动端 60fps 滚动流畅

## Out of Scope

- **frontend 管理面板**（React，独立工程，本次不动）
- **后端 API**（FastAPI，本次不动，仅确认 `/static/*` 路由存在性）
- **真实浏览器 E2E**（受 MCP playwright 连接失败限制，本次用 `vite preview + curl + Node 契约等价` 替代）
- **og:image 1200×630 定制图**（复用现有 `/static/logo-md.png`，社交平台可能裁切，留作 P3）
