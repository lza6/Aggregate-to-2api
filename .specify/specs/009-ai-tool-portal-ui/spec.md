# Feature Specification: 009 AI 工具门户 UI 重构（media.io 范式）

## Problem Statement

当前落地页（landing/）+ 管理端（frontend/）是**技术演示/运维后台**形态：
Hero 显示状态胶囊、SectionProviders 展示提供商/模型目录、SectionCode 展示 curl API 示例、
导航有「管理后台」入口——全是给开发者/运维看的，不是给终端用户看的。

用户参考 [media.io/ai/zh](https://www.media.io/ai/zh)：**一站式 AI 创意工具门户**——
大 Hero + 工具卡片网格（每个工具=图标+名称+一句话+入口）+ 热门创作展示 + 简洁 CTA。
要求：UI 美观高级、组件/模块划分明确、面向真实用户可操作、不要管理后台入口。

## 现状能力（后端真实可用，2026-09-26 核验）

| 工具 | 端点 | 状态 |
|------|------|------|
| AI 对话 | POST /v1/chat/completions + /v1/messages | ✅ 真实（tryingopen） |
| 文生图 | POST /v1/generate/async（imagefree/aifreeforever） | ✅ 真实出图 R2 |
| 图生图 | POST /v1/edit | ✅ 真实 |
| AI 视频 | POST /v1/video | ⚠️ Mock（falai 下线，待新上游） |
| AI PPT | POST /v1/skills/ppt/generate | ✅ python-pptx 真实产物 |
| 画廊 | GET /v1/gallery | ✅ 分页/搜索/zip |
| Agent 编排 | POST /v1/agent/dag/plan+run | ✅ 真实 tryingopen |

## User Stories

### US1: 工具门户首页（P0）
作为普通用户，打开首页应看到「一站式 AI 创意平台」：
- Hero：大标题 + 副标题 + 主 CTA（如「立即开始创作」滚动到工具区）+ 轻量信任元素
- 工具网格：AI 对话 / 文生图 / 图生图 / AI 视频 / AI PPT / 灵感画廊 —— 每个大卡片
  （图标 + 名称 + 一句话描述 + 状态徽章「免费」/「Beta」+ 点击进入对应体验）
- 热门创作区：画廊真实作品瀑布流（懒加载）
- 去除：SectionProviders 提供商卡片、SectionCode API 示例、SectionUsage 用量、SectionStatus 状态胶囊、
  导航「管理后台」按钮、页脚 /v1/slow/view + /v1/honor 运维链接

### US2: 管理端收敛（P1）
作为站长，管理能力保留但不暴露给终端用户：
- landing 导航不再出现「管理后台」入口（改为无入口或极隐蔽）
- frontend/（React 管理台）保留在 /admin 供站长用，但首页/落地页与它完全分离
- 明确「用户门户 = landing」，「站长后台 = /admin」两个独立体验

### US3: 模块化组件划分（P0）
作为前端，工具卡片/画廊/对话等拆成独立 Vue 组件，样式用 design tokens：
- components/tools/ 工具卡片网格（ToolCard.vue + ToolsGrid.vue）
- components/gallery/ 作品瀑布流（GalleryWall.vue，懒加载 + 空态）
- components/HeroPortal.vue 门户 Hero
- HomeChat 保留但重新设计融入门户（去掉"提供商"气息）
- base.css 扩展 design tokens（色板/圆角/阴影/间距/动效），组件复用

## Non-Functional Requirements

- 移动端 375/768 断点无横滚、触控目标 ≥44px
- 可访问性：对比度、focus-visible、aria-label
- 性能：工具网格/画廊懒加载；首屏 LCP 不因新组件劣化
- 真实数据：画廊用真实 /v1/gallery；工具状态徽章反映真实可用性（视频标 Beta）
- 不改后端 API；landing 独立于 /admin

## Success Metrics

- landing 首页 = media.io 式工具门户（截图对比）
- 管理后台入口从用户路径移除
- 组件模块化：components/{tools,gallery,hero,chat}/ 清晰
- vitest/build 全绿；移动端/无障碍过自查
- 上线 https://imagefree.hwhcie.bond 真机验收

## Out of Scope

- 登录/付费（保持匿名公益）
- 后端能力新增（视频真实上游另立 spec）
- /admin 管理台本身重构（本轮只收敛入口）
