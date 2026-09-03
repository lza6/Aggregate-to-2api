# Implementation Tasks: Landing Vibe Coding 视觉升级

> 追溯型 tasks（事后补档）。全部任务已完成 `[x]`。Phase5 含审查线程修复。

## Phase 1: 依赖与 Token（Foundation）

- [x] 1.1 在 `landing/package.json` 新增 4 依赖
  - `motion-v@^2.4.0` / `@tresjs/core@^5.8.3` / `three@^0.185.1` / `@vueuse/core@^14.4.0`
  - `npm install` 成功（added 20 packages in 8s）
  - **Depends on**: None
  - **Requirement**: R1.1

- [x] 1.2 重写 `landing/src/styles/base.css` 为液态玻璃调色板
  - 底层 `--bg #0a0e1a` + 玻璃层 `--card rgba(255,255,255,0.045)` + 高光 `--brand #60a5fa` / `--accent #f472b6`
  - `.card` 升级 `backdrop-filter: blur(20px) saturate(140%)` + 高光边 `::before`
  - **Depends on**: 1.1
  - **Requirement**: R1.2

- [x] 1.3 实现四档降级规则
  - `@supports not (backdrop-filter)` → 玻璃退纯色
  - `@media (max-width:768px)` → blur 降到 12px
  - `@media (prefers-reduced-motion: reduce)` → 全局禁动画
  - **Depends on**: 1.2
  - **Requirement**: R1.3

## Phase 2: 3D 与动效（Core）

- [x] 2.1 创建 `landing/src/components/Hero3D.vue`（Three.js 粒子流场）
  - ~2200 粒子 BufferGeometry + PointsMaterial(AdditiveBlending)
  - 颜色 `cBlue #60a5fa` ↔ `cPink #f472b6` lerp 渐变
  - 鼠标 parallax 相机微移
  - `defineAsyncComponent` 懒加载（在 App.vue）
  - **Depends on**: 1.1
  - **Requirement**: R2.1

- [x] 2.2 创建 `landing/src/composables/useReveal.js`
  - 封装 motion-v `whileInView` 预设
  - reduced-motion 退化为瞬时（opacity:1）
  - **Depends on**: 1.1
  - **Requirement**: R2.2

- [x] 2.3 改造 `landing/src/App.vue` 集成 3D + motion
  - 挂载 `<Hero3D>` 到 `.bg-field`（z=0）
  - `.aura` 升级流动光晕
  - `.glow-cursor` 鼠标跟随
  - `.nav` sticky + `useScroll` 滚动收缩
  - Hero 标题改 `.text-grad` 渐变
  - 全部 Section 包 `motion.section v-bind="revealN"`
  - **Depends on**: 2.1, 2.2
  - **Requirement**: R2.3

## Phase 3: Section 改造（7 组件 motion 化）

- [x] 3.1 `SectionStatus.vue` — chip → `motion.div` stagger 入场 + hover spring
  - **Depends on**: 2.2
  - **Requirement**: R3.1

- [x] 3.2 `SectionProviders.vue` — provider 卡片 → `motion.article` stagger + hover 抬升
  - **Depends on**: 2.2
  - **Requirement**: R3.2

- [x] 3.3 `SectionUsage.vue` — use-card → `motion.div` reveal
  - **Depends on**: 2.2
  - **Requirement**: R3.3

- [x] 3.4 `SectionCode.vue` — 修原 `computed` 重复声明 bug + tab → `motion.button` hover/tap + 卡片 reveal
  - **Depends on**: 2.2
  - **Requirement**: R3.4

- [x] 3.5 `SectionFaq.vue` — FAQ 项 stagger + 答案 `AnimatePresence` height 动画
  - **Depends on**: 2.2
  - **Requirement**: R3.5

- [x] 3.6 `SectionChangelog.vue` — notes-list reveal + 答案 `AnimatePresence`
  - **Depends on**: 2.2
  - **Requirement**: R3.6

- [x] 3.7 `SectionCta.vue` — CTA `motion.div` reveal + 主按钮 spring 磁吸 hover + h2 渐变
  - **Depends on**: 2.2
  - **Requirement**: R3.7

## Phase 4: SEO

- [x] 4.1 重写 `landing/index.html` 头部
  - `<meta description>` 含关键词（150 字内）
  - `<meta keywords>` 覆盖 AI 图像生成/网关/OpenAI 兼容等
  - `<meta robots>` index,follow,max-image-preview:large
  - `<link canonical>` 指向线上根 URL
  - **Depends on**: None
  - **Requirement**: R4.1

- [x] 4.2 OG + Twitter Card 双套社交 meta
  - og:type/site_name/title/description/url/locale/locale:alternate/image
  - twitter:card summary_large_image + image
  - **Depends on**: 4.1
  - **Requirement**: R4.2

- [x] 4.3 JSON-LD 结构化数据
  - SoftwareApplication（applicationCategory/operatingSystem/offers/featureList/softwareVersion）
  - WebAPI（documentation/provider）— **审查线程 P1 标注**：`endpoint` 非标准字段，Google 会忽略，不阻塞
  - **Depends on**: 4.1
  - **Requirement**: R4.3

- [x] 4.4 `<meta theme-color>` + `<meta color-scheme>` 暗色声明
  - **Depends on**: 4.1
  - **Requirement**: R4.4

## Phase 5: 验证与审查修复

- [x] 5.1 `npm run build` 构建通过
  - 414 modules transformed, built in 3.03s
  - 首屏 index.js gzip 90.10kb（≤150kb 预算 ✅）
  - three 独立 chunk gzip 189.60kb（懒加载 ✅）
  - **Depends on**: 3.1-3.7, 4.1-4.4
  - **Requirement**: R5.1

- [x] 5.2 `vite preview + curl` 烟雾验证
  - HTTP 200, size=4466
  - dist/index.html 含 `id="app"` `/assets/` `og:title` `theme-color` `description` `application/ld+json`
  - banned 词回归 0（`pg-prompt` `/v1/generate` `在线使用` 均无）
  - **Depends on**: 5.1
  - **Requirement**: R5.2

- [x] 5.3 Node 等价覆盖契约测试（Python 解释器不可用，用 Node 替代）
  - 校验 dist 含 id="app" + /assets/ + version 一致 + banned 词 0 + og:image 资源存在
  - **Depends on**: 5.1
  - **Requirement**: R5.3

- [x] 5.4 **审查线程 P0 修复：og:image 死链**
  - 原指向 `/static/tingfeng-logo.png`（282kb，无路由）→ 改为 `/static/logo-md.png`（9589 字节，`health.py` 已注册路由）
  - **Depends on**: 5.2
  - **Requirement**: R5.4

- [ ] 5.5 **审查线程 P0 修复：h1 初始 opacity:0 SEO/LCP 风险**
  - hero h1 不用 motion reveal，或 initial 从 opacity:1 起
  - **状态**：待修（审查线程 P0-2，主线程尚未修复）
  - **Depends on**: 5.2
  - **Requirement**: R5.5

- [ ] 5.6 **审查线程 P1 修复：WebGL forceContextLoss**
  - Hero3D.vue onBeforeUnmount 加 `c.renderer.forceContextLoss?.()` 彻底释放 GL context
  - **状态**：待修（审查线程 P1-3，主线程尚未修复）
  - **Depends on**: 2.1
  - **Requirement**: R5.6

- [ ] 5.7 **审查线程 P2 修复：loop() 每帧除法缓存**
  - `for (let i = 0; i < arr.length / 3; i++)` → 缓存 `const n = arr.length / 3`
  - **状态**：待修（审查线程 P2-5）
  - **Depends on**: 2.1
  - **Requirement**: R5.7

- [ ] 5.8 **审查线程 P1 修复：删 WebAPI JSON-LD 块**
  - `endpoint` 非标准字段，删 WebAPI 块只保留 SoftwareApplication 降噪声
  - **状态**：待修（审查线程 P1-1）
  - **Depends on**: 4.3
  - **Requirement**: R5.8

## Notes

- Phase 1-4 全部完成，Phase 5 前 4 项完成，后 4 项为审查线程发现的待修项
- `[P]` 标记不适用（本任务为线性依赖）
- Python 契约测试因 `.venv` 损坏 + 系统无 `python`/`py`/`uv` 未跑，用 Node 等价覆盖（R5.3）
- CI `frontend-version-gate` job 会用干净环境重跑 `npm ci && npm run build` + Python 契约测试，push 后应绿
