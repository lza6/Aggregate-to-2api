# 听风AI v7.4.0 发布说明 — landing Vibe Coding 视觉升级

## 概述

v7.4.0 是**公开落地页（landing）视觉与 SEO 专项升级**版本。仅动 `landing/`（Vue 3.5 + Vite），未触碰后端 API 与 frontend 管理面板，向后完全兼容。

- **液态玻璃 Liquid Glass 调色板**（2026 trending，演进原 indigo 单调主调）
- **Three.js 粒子流场 3D 背景**（抽象粒子，呼应"AI 生成·数据流转"语义）
- **motion-v 滚动揭示动效**（Framer 范式的 Vue 版，7 Section 全 motion 化）
- **SEO 全量补齐**（meta + JSON-LD + OG/Twitter Card，修正 og:image 死链）

**零外部 CDN 依赖原则不变**：motion-v / three / @vueuse/core 全部 npm 本地 bundle。

---

## 视觉：液态玻璃调色板

### 实现
- `landing/src/styles/base.css`（+240 行）token 重写，保留旧 token 名兼容各 Section 引用：
  - 底层 `--bg #0a0e1a` 深蓝黑（玻璃需更深底才透得出）
  - 玻璃层 `--card rgba(255,255,255,0.045)` + `backdrop-filter: blur(20px) saturate(140%)`
  - 高光 `--brand #60a5fa` 天蓝 + `--accent #f472b6` 粉珊瑚（替代原 indigo）
  - `.card::before` 顶部高光反光边（液态玻璃质感核心）
- 降级：`@supports not (backdrop-filter)` 退纯色；`prefers-reduced-motion` 全局禁动画；移动端 blur 降到 12px

---

## 3D：Three.js 粒子流场（Hero3D.vue 新建）

### 实现
- `landing/src/components/Hero3D.vue`（+201 行）：
  - ~2200 粒子球形云分布，颜色在天蓝↔粉珊瑚间随机插值，AdditiveBlending 软光感
  - 流场运动：整体慢转 + 粒子 sin 呼吸位移；相机鼠标 parallax 缓动跟随
  - **懒加载**：`defineAsyncComponent(() => import('./Hero3D.vue'))` + `import('three')` 动态导入，three 不进首屏 LCP 关键路径
  - **资源释放**：`onBeforeUnmount` 调 `renderer.forceContextLoss()` 防 GL context 句柄累积（小屏↔大屏切换重复挂载，浏览器 ~16 context 上限）
  - **三档降级**：WebGL 创建失败→CSS aura；`reduced-motion`→只渲染静态帧；小屏粒子减半

### 包体积
- 首屏 `index.js gzip 90.08kb`（符合 <150kb 预算）
- three 独立 chunk `gzip 189.60kb` 懒加载，不在 LCP 关键路径（真 3D 的必然代价）

---

## 动效：motion-v@2.4.0

### 实现
- `landing/src/composables/useReveal.js`（新建）：封装 whileInView 预设 + reduced-motion 降级
- 7 个 Section 全部 `whileInView` scroll reveal + stagger 延迟：
  - SectionStatus chip 逐个 stagger 入场 + hover spring 抬升
  - SectionProviders 卡片 hover 抬升
  - SectionFaq/Changelog 答案用 `AnimatePresence` height 动画（exit 优雅收起）
  - SectionCta 主按钮 spring 磁吸 hover（stiffness 400 / damping 17）
- **关键修正**：Hero 首屏 h1/h2/sub **改用 CSS `fade-up` 而非 motion**——motion 的 `initial:opacity:0` 在 JS 延迟/失败时会让 LCP 候选元素 h1 永久透明，对爬虫与 LCP 致命；非首屏内容才用 motion reveal

---

## SEO：meta + 结构化数据

### 实现
- `landing/index.html` 补全：
  - `description`（150 字内含关键词）+ `keywords` + `robots index,follow,max-image-preview:large`
  - `canonical` 指根；Open Graph（type/site_name/title/desc/url/locale+alternate/image）；Twitter Card `summary_large_image`
  - `theme-color #0a0e1a` + `color-scheme dark`
  - JSON-LD `SoftwareApplication`（Google 富媒体支持）+ `WebSite`
- **死链修正**：og:image/twitter:image 原指向 `/static/tingfeng-logo.png`，后端只注册了 `/static/logo.png` 与 `/static/logo-md.png` 路由 → 改指 `/static/logo-md.png`
- **删非标准 WebAPI**：JSON-LD 原 WebAPI 块用 `endpoint` 非标准属性，Google 不保证支持，删改 WebSite

---

## 独立审查线程发现并修复的问题（9 条）

critical-code-reviewer fork + 运行时集成审计 fork 并行审查，发现 9 条全部修复：

| # | 级 | 问题 | 修法 |
|---|----|------|------|
| P0-1 | 阻塞 | og:image 死链 | 改指 /static/logo-md.png |
| P0-2 | 阻塞 | package-lock.json 未提交 | 与 package.json 一起提交 |
| P0-3 | 阻塞 | hero h1 opacity:0 LCP 风险 | 改 CSS fade-up |
| P1-1 | 高 | WebGL 未 forceContextLoss | 加 forceContextLoss |
| P1-2 | 高 | WebGL 探测多分配 context | 删探测直接 try |
| P1-3 | 高 | WebAPI JSON-LD 非标准 | 删改 WebSite |
| P2-1 | 中 | loop 每帧除法 | 缓存上界 n |
| P2-2 | 中 | three chunk 超限警告 | chunkSizeWarningLimit:800 |
| P2-3 | 中 | SectionUsage motion 包裹无意义 | 改回 div |

---

## 工程

- `landing/vite.config.js`：`build.chunkSizeWarningLimit:800`（three 独立 chunk ~189kb gzip 是真 3D 必然体积，诚实保留不改最小化）
- `.specify/specs/004-landing-vibe-coding/`：spec.md / plan.md / tasks.md（Spec Kit 7 阶段规范文档）
- `docs/reports/v7.4-landing-vibe-coding-report.html`：HTML 变更报告 + 8 题测验

---

## 验证

- `npm install`（landing +4 依赖）→ ✓ added 20 packages in 8s
- `npm run build` → ✓ 414 modules, 2.75s
- `vite preview` + `curl /` → ✓ HTTP 200
- Node 等价契约测试 9 项全绿：id=app / /assets/ / banned 0 / version 7.4.0 / og:image 路由 / lock 依赖 / SoftwareApplication / WebAPI 已删 / theme-color
- critical-code-reviewer fork 审查 → 9 问题全修，build 复验通过
- Chrome headless E2E 截图 + console error 抓取（见 workflow_status.md 验证记录）

## 已知限制 / 剩余风险

- **motion-v 运行时兼容**：build 通过 ≠ 运行时 OK，Chrome headless E2E 已验证无 console error
- **og:image 尺寸**：复用 logo-md.png（320×320），非 1200×630 社交卡最佳比例，可能裁切但不再死链
- **three 体积**：189kb gzip 超预算但懒加载，LCP 不受影响，真 3D 必然代价
- **backdrop-filter 移动端**：已降到 blur(12px)，中端机同屏 4 层 blur 帧率建议后续压测

## 部署

- landing dist 随 `deploy.yml` 的 `landing-dist.tgz` 热部署到服务器 `/home/ubuntu/imagefree-api/landing/dist`
- 后端 API 无改动，但随 tag 触发镜像重建（无功能变更）
- 版本一致性断言：CI `frontend-version-gate` + deploy.yml 均断言 dist 含 `7.4.0`
