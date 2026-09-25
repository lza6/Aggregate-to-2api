# v20.3.0 发行说明 — AI 工具门户 UI 重构（Spec 009）

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🎉 亮点：一站式 AI 创意平台（media.io 范式）

首页从「技术演示页」重构为 **SaaS 式 AI 工具门户**，用户可直接在线使用：

| 工具 | 体验 | 后端真实能力 |
|------|------|--------------|
| 💬 AI 对话 | 流式 SSE，24 模型可选 | tryingopen 真实 |
| 🎨 文生图 | 一句话出图，8 画幅 | imagefree/aifreeforever 真实 |
| 🖌️ 图生图 | 上传参考图改写 | /v1/edit 真实 |
| 🎬 AI 视频 | Beta 标注（新上游待接入） | Mock |
| 📊 AI PPT | 大纲→PPTX 下载 | python-pptx 真实 |
| 🤖 AI 智能体 | 自然语言→DAG 计划+执行 | tryingopen 真实 |

## 🏗️ 结构性变更

- **移除用户路径中的管理后台**：导航不再出现「进入管理台」；/admin 保留给站长
- **移除开发者向内容**：SectionProviders（提供商卡片）、SectionCode（curl 示例）、SectionUsage（用量）、SectionStatus（状态胶囊）、页脚 /v1/slow/view + /v1/honor 运维链接
- **模块化组件**：components/tools/（ToolCard + ToolsGrid）、components/gallery/（GalleryWall）、HeroPortal、PortalChat/Generate/Video/Ppt/Agent
- **灵感画廊**：真实 /v1/gallery 作品瀑布流（懒加载 + 空态 + 错误态）

## ✅ 验证（真实 E2E）

| 项 | 结果 |
|----|------|
| 首页结构 | 6 工具卡 + 9 画廊真实 R2 图 + 0 管理入口 + 0 运维链接 |
| AI 对话 | tryingopen deepseek 真实 SSE 回复 |
| 文生图 | 真实出图 R2（27s） |
| Agent | 自然语言 → 4 节点 DAG（tryingopen 真实规划） |
| 移动端 | 375/768 无横滚，触控目标 77px |
| 构建 | vite build 44 模块全绿 |

## 📋 文件清单

- landing/src/App.vue（门户化重写）
- landing/src/components/{HeroPortal,PortalChat,PortalGenerate,PortalVideo,PortalPpt,PortalAgent}.vue
- landing/src/components/tools/{ToolCard,ToolsGrid}.vue
- landing/src/components/gallery/GalleryWall.vue
- landing/src/composables/{useApi,useI18n}.js
- landing/vite.config.js（dev /v1 代理 + Python 转发）
- landing/index.html（SEO 门户化）
- .specify/specs/009-ai-tool-portal-ui/{DESIGN.md,spec.md,.progress.md}
- workflow_status.md（Spec 009 看板 + E2E 证据）
- 版本全链 bump 20.3.0
