# Implementation Plan: Landing Vibe Coding 视觉升级

> 追溯型 plan（事后补档）。记录已落地实现的技术决策与架构。

## Technology Stack

### Frontend

- **Framework**: Vue 3.5.42（已存在，沿用 Composition API + `<script setup>`）
- **Build**: Vite 6.4.3（已存在）
- **动效引擎**: `motion-v@2.4.0`
  - 选型理由：Framer Motion 范式的 Vue 移植，API 一致（`motion.div` / `whileInView` / `AnimatePresence` / `whileHover` / spring transition），peerDeps `vue>=3.0` + `@vueuse/core>=10`，与项目栈兼容。
  - 备选 `@vueuse/motion` 未选，因其 API 范式更 directive 化，与 Framer 习惯偏差大。
  - 已知风险：motion-v 非 Framer 官方，build 通过 ≠ 运行时 100% 无 bug，需浏览器烟雾测试（本次受 MCP playwright 断连限制未真跑，留 P2）。
- **3D 引擎**: `three@0.185.1`（裸 import，非 TresJS）
  - 选型理由：更可控。TresJS（`@tresjs/core@5.8.3`）虽已安装（package.json 列出），但实际 `Hero3D.vue` 用裸 `import('three')` + `BufferGeometry` + `PointsMaterial`，避免声明式封装层的抽象泄漏。
  - 已知风险：three gzipped 189.60kb 超 landing JS 预算 150kb，但懒加载（动态 import）不进 LCP 关键路径，属可接受取舍。
- **响应式工具**: `@vueuse/core@14.4.0`
  - 用途：`useMediaQuery`（reduced-motion / 小屏检测）、`useScroll`（nav 滚动收缩）

### 未用但已声明

- `@tresjs/core@5.8.3`：已安装但未实际 import。保留在 dependencies 以便未来切换声明式 3D。**诚实标注**：这是冗余依赖，可在后续清理（P3）。

## Architecture

### 层级结构（z-index 从底到顶）

```
z=0  .bg-field         全屏 3D 粒子流场（TresJS/three canvas，pointer-events:none）
z=0  .aura             顶部品牌光晕（CSS radial-gradient，blur）
z=0  .glow-cursor      鼠标跟随玻璃光晕（CSS radial-gradient 跟随 --mx/--my）
z=1  .main             玻璃内容层（Section 们）
z=50 .nav              sticky 导航（液态玻璃，滚动加深 blur）
```

### 组件依赖图

```
App.vue
├─ Hero3D.vue (defineAsyncComponent 懒加载)
│   └─ import('three') 动态
├─ useReveal.js (封装 motion-v whileInView 预设)
├─ SectionStatus.vue    (motion.div stagger chips)
├─ SectionProviders.vue (motion.article stagger + hover)
├─ SectionUsage.vue    (motion.div reveal)
├─ SectionCode.vue     (motion.div reveal + motion.button hover/tap)
├─ SectionFaq.vue      (motion stagger + AnimatePresence height)
├─ SectionChangelog.vue(motion reveal + AnimatePresence height)
└─ SectionCta.vue      (motion spring 磁吸 hover)
```

### 数据流（未改动）

- `useStats` / `useMeta` / `useProviders` / `useModels` / `useChatUsage` composables 继续从 `/v1/stats` `/v1/meta` `/v1/providers` `/v1/models` `/v1/chat/usage` 拉取实时数据，motion 仅包裹渲染层，不触碰数据层。

## Design Decisions

### D1: 为什么 motion-v 而非 @vueuse/motion

- motion-v API 与 React 生态的 Framer Motion 高度一致（`whileInView` / `AnimatePresence` / spring `type:'spring'`），团队心智模型迁移成本低。
- @vueuse/motion 更 directive 化（`v-motion`），对 `AnimatePresence`（exit 动画）支持弱，FAQ/Changelog 的折叠 height 动画需要 exit。

### D2: 为什么裸 three 而非 TresJS

- TresJS 声明式 `<Points>` `<BufferGeometry>` 封装在自定义 shader/attribute 场景下有抽象泄漏风险。
- 裸 three 对 `BufferAttribute` 的 `position`/`color`/`phase` 直接控制，流场位移算法（`arr[i*3+1] += sin(time*2+phase[i])*0.004`）更直观。
- 代价：`shallowRef<any>` 持有 three 对象（Vue 对 three 的大对象做 reactive 代理会爆），类型安全弱化（P2 建议：加 `@types/three`）。

### D3: 为什么懒加载 3D（defineAsyncComponent + dynamic import）

- three chunk gzipped 189.60kb，若进首屏主 bundle，LCP 关键路径 JS 远超 150kb 预算。
- `defineAsyncComponent(() => import('./Hero3D.vue'))` + `Hero3D.vue` 内 `await import('three')` 双重懒加载，首屏 LCP 候选元素（h1）不被 three 阻塞。
- 代价：3D 首次加载有短暂延迟（~200ms），但它在背景层，不影响内容可见性。

### D4: 降级三档（Defense in Depth，呼应宪法 Core Value 3）

| 触发条件 | 降级行为 | 实现位置 |
|---------|---------|---------|
| WebGL 不可用 | 3D 退 CSS aura 渐变 | `Hero3D.vue:73-75` `ok.value=false` → `<div class="hero3d-fallback">` |
| `prefers-reduced-motion: reduce` | motion 退瞬时、3D 只渲染一帧 | `useReveal.js:12-13` + `Hero3D.vue:149-153` |
| 移动端 (max-width:768px) | backdrop-filter blur 降到 12px、粒子数减半 | `base.css:292-297` + `Hero3D.vue:94` |
| `@supports not (backdrop-filter)` | 玻璃卡片退纯色 | `base.css:283-290` |

### D5: SEO 关键元素不用 motion reveal（审查线程建议）

- 原方案 `motion.h1 v-bind="reveal1"` 会给 h1 内联 `opacity:0`，JS 延迟/失败时 LCP 候选元素不可见。
- **审查线程 P0 建议**：h1 改为默认可见（不用 motion reveal，或 initial 从 opacity:1 起）。
- 本 plan 记录该决策，实际修复在 tasks.md Phase5 的 R5.2。

## Security Considerations

- **零外部 CDN**：所有依赖（three/motion-v/@vueuse）走 npm 本地 bundle，无 `<script src="https://...">`，符合项目"无 CDN"原则。
- **og:image 路径安全**：指向 `/static/logo-md.png`，由 `api/routes/health.py` 的 FileResponse 路由服务，不暴露任意文件遍历。

## Performance Strategy

- **首屏 JS 预算**：≤150kb gzip（实测 90.10kb ✅）
- **three 懒加载**：动态 import，独立 chunk（189.60kb gzip，不进首屏）
- **动画属性**：仅 transform/opacity（compositor-friendly），不触发布局
- **backdrop-filter 节制**：移动端降到 12px，移动端 nav 可进一步退纯色（P2）

## Error Handling

- Hero3D 初始化失败 → `console.warn` + `ok.value=false` → CSS 兜底
- WebGL context 泄漏 → onBeforeUnmount `renderer.dispose()` + `domElement.remove()` + geometry/material dispose（审查线程建议加 `forceContextLoss()`，见 tasks.md Phase5 R5.3）
