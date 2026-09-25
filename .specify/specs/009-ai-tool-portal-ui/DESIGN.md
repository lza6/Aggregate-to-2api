# Spec 009 设计文档：AI 工具门户 UI 重构（media.io 范式）

> Status: DRAFT → IMPLEMENTING ｜ Owner: 主控 ｜ 版本目标: v20.3.0

## 1. 设计决策（第一性原理 + 用户命题）

用户原话：「我们想做得像 SaaS 平台那样…我们有 agent 的功能，有生成的功能…你干嘛要搞那么复杂搞什么管理后台…做多租户也可以，但你要搞定清楚」
→ **确定**：首页 = 一站式 AI 创意工具门户（media.io 范式：Hero + 工具卡片网格 + 热门创作瀑布流），
  管理后台 = 独立体验收敛到 /admin（用户路径彻底移除）。

### 技术路线
- 复用现有 Vue3 + Liquid Glass tokens，**不引入重型 UI 框架/状态库**（保持 47kb 依赖体积、首屏 LCP 不劣化）。
- 工具卡片全部「点击即用」：卡片本身即体验面板（点击展开为可操作工具），而不是跳到技术页 —— 这符合 media.io「工具即入口」。
- 真机验收：https://imagefree.hwhcie.bond（生产）与本地 dev server 双轨。

### 分层
| 层 | 模块 | 说明 |
|----|------|------|
| 门户 Hero | HeroPortal.vue | 大标题+副标题+主 CTA+轻量信任元素（保留 Hero3D 背景） |
| 工具卡片 | components/tools/ToolCard.vue + ToolsGrid.vue | 6 张卡：对话/文生图/图生图/视频/PPT/Agent |
| 在线体验 | PortalChat.vue / PortalGenerate.vue / PortalAgent.vue | 点击卡片展开的真实使用面板（对话 SSE、生成轮询/SSE、DAG plan+run） |
| 灵感画廊 | components/gallery/GalleryWall.vue | 真实 /v1/gallery 瀑布流 + 空态 + 懒加载 |
| 页脚 | 简化 | 移除 slow/honor 运维链接 |

### 工具卡片目标映射（链接到真实能力）
| 卡 | 体验 | 后端 |
|----|------|------|
| AI 对话 | PortalChat（SSE 流式） | /v1/chat/completions（tryingopen 真实） |
| 文生图 | PortalGenerate txt | /v1/generate + /v1/tasks/{id}/events |
| 图生图 | PortalGenerate img（上传 base64） | /v1/edit + /v1/edit/tasks/{id} |
| AI 视频 | Beta（Mock 标注） | /v1/video（IF_VIDEO_ENABLED=0 时提示） |
| AI PPT | PortalPpt（大纲→pptx 下载） | /v1/skills/ppt/generate（IF_PPT_GENERATE=1 时可用） |
| AI Agent | PortalAgent（自然语言→DAG plan+run） | /v1/agent/dag/plan + /run |

## 2. 现状能力核验（2026-09-26 已实测）
- /v1/healthz 200（cf_solver up, workers 4, queue_capacity 2200）
- /v1/gallery?limit=60 → total 9, count 9；items 含 image_url（R2 公网可达）
- 生产 .env：IF_API_KEYS=dev-api-key-for-e2e（本地产），服务器 .env 未确认鉴权关闭 → **门户体验不配 Key**（写接口全公开）

## 3. 风险与回滚
| 风险 | 缓解 |
|------|------|
| 服务器未开 PPT/视频开关 | 卡片状态徽章「Beta/敬请期待」，点开给出 502 友好文案 |
| 管理后台入口移除后站长迷路 | /admin 保留 + README 说明；footer GitHub 链接保留 |
| 大改引入构建问题 | 每组件独立 vitest + build；dist 重建后先本地 preview 再部署 |

## 4. 组件清单（新增/修改）
| 文件 | 状态 |
|------|------|
| landing/src/components/tools/ToolCard.vue | 新增 |
| landing/src/components/tools/ToolsGrid.vue | 新增 |
| landing/src/components/gallery/GalleryWall.vue | 新增 |
| landing/src/components/HeroPortal.vue | 新增 |
| landing/src/components/PortalChat.vue | 新增（基于 HomeChat 重构） |
| landing/src/components/PortalGenerate.vue | 新增 |
| landing/src/components/PortalAgent.vue | 新增 |
| landing/src/components/PortalPpt.vue | 新增 |
| landing/src/App.vue | 重写（去 Section*/管理后台/slow/honor） |
| landing/src/composables/useApi.js | 扩展 gallery/models |
| landing/src/composables/useI18n.js | 扩门户字典（原键保留） |
| .specify/specs/009-ai-tool-portal-ui/spec.md | 更新任务进度 |

## 5. 验收矩阵
| 验收项 | 方法 |
|--------|------|
| 构建全绿 | npm.cmd run build |
| 首页无管理后台入口 | rg 断言 App.vue 无 /admin 链接 |
| 移动端 375/768 无横滚 | Playwright 视口检查 |
| 画廊真实数据 | dev server 拉 /v1/gallery 断言 ≥1 图 |
| 在线对话真实 | dev server 提交 chat 断言 SSE 文本 >0 |
| 生产对比 media.io | 截图对比 |

## 6. 交付顺序
1. 设计文档（本文件）→ 2. 实现组件 → 3. vitest/build → 4. 本地真机（dev server + 真实 API）→ 5. 部署服务器 → 6. 截图对比 → 7. 提交 push → 8. Release v20.3.0
