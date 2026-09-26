# Workflow Status — 终局闭环总审计 / 生产化补强（Spec 008）→ Spec 009 门户重构

> 更新：2026-09-26 ｜ 上一版本：Phase A 参考项目对标（2026-09-22，已归档 docs/archived/）
> 主项目：`C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\imagefree-2ai`（听风AI，v20.3.2（已发布 v20.3.0/v20.3.1））
> 生产：20.204.27.154（ARM64 2C/4G）nginx 443 → imagefree-api 8100 + cfsolver 8001（camoufox）+ 代理池 1130
> 编排：Spec Kit 009/010 + 主控工作流

## 当前状态（2026-09-26）

| 域 | 状态 | 证据 |
|----|------|------|
| 提供商收敛 | ✅ imagefree/aifreeforever + tryingopen（nanobanana/falai 已下线） | registry=[imagefree,aifreeforever]+[tryingopen] |
| 首页在线使用 | ✅ 门户 6 工具卡（对话/文生图/图生图/视频/PPT/Agent） | Playwright 真机验证全绿 |
| tryingopen 真实调用 | ✅ IF_MOCK_UPSTREAM=0，chat SSE / agent plan 真实 | 实测回复真实文本 + 4 节点 DAG |
| 代理池高并发 | ✅ IF_FREE_PROXY=1 启用，并发 4/4 completed | v20.2 fix `_is_upstream_ip_busy` |
| cf_solver | ✅ camoufox ARM64 单次 ~3s | solve_success |
| 管理后台收敛 | ✅ 首页 0 管理入口 + 0 运维链接；/admin 保留 | Playwright 断言 adminLinks=0 |
| 画廊 | ✅ 9 张真实 R2 图瀑布流 | /v1/gallery count=9 |
| 版本/Release | 🔄 v20.3.0 待发 | 见下 |

## 本轮子任务工作流（Spec 010 生产加固，v20.3.2）

> 依据 verification-log 避免重做已闭环项（图生图 TLS/日志脱敏/模型缓存/PPT 开关/Agent E2E）。

| 子任务 | 状态 | 产出/证据 |
|--------|------|----------|
| C0 Spec 010 规范 | ✅ DONE | .specify/specs/010-production-hardening-ngx/spec.md |
| C1 nginx 静态缓存头 + gzip | ✅ DONE | /assets immutable + gzip -62%；首页 no-cache；备份 .bak-2031 |
| C2 高并发只读探针 | ✅ DONE | 100 并发 100% ok 无错误；服务端 3ms 无瓶颈；scripts/probe_concurrency.py |
| C3 契约防坑审计 | ✅ DONE | 前端 Key 冗余 + 后端匿名开放兼容；无隐藏不一致 |
| C4 文档同步 | 🔄 进行中 | verification-log + workflow_status + README |

## 已验证勿重做（避免重复优化，来自 verification-log）
- 图生图 TLS（R2 SNI IP直连冲突）→ 已修复 v20.3.1 ✅
- /v1/logs 脱敏、/v1/models 60s 缓存、MCP generate_image 真实透传 → 已闭环 ✅
- PPT/视频开关检测（meta ppt_enabled/video_enabled）→ 已闭环 ✅
- Agent 真实 LLM plan+run（glm-5.3-flash 4 节点 succeeded）→ 已闭环 ✅
- frontend Tasks/GalleryAlbum flaky（clearAllMocks）→ 已根治 ✅

## 本轮子任务工作流（Spec 009 门户重构）

| 子任务 | Agent | 状态 | 产出 |
|--------|-------|------|------|
| D1 设计文档 | 主控 | ✅ DONE | .specify/specs/009-ai-tool-portal-ui/DESIGN.md |
| D2 门户组件（Hero/工具卡/画廊/对话/生图/Agent/PPT/视频） | 主控 | ✅ DONE | components/{tools,gallery}/ + PortalXxx |
| D3 App.vue 门户化（去管理后台/去运维链接/简化页脚） | 主控 | ✅ DONE | App.vue 重写 |
| D4 i18n 门户字典 + SEO | 主控 | ✅ DONE | useI18n.js + index.html |
| D5 真机 E2E（对话/生图/Agent/画廊/移动端） | 主控 | ✅ DONE | Playwright 证据（见下） |
| D6 构建 + 部署生产 | 主控 | 🔄 进行中 | dist 重建 → git pull + restart |
| D7 提交 push + Release v20.3.0 | 主控 | ⏳ 排队 | 主题 commit + gh release |

## 铁律（本工作流强制）

1. 验证记录防重跑：docs/verification-log.md 持续追加；"验证过勿重跑"结论维护
2. 真实性：每项验收附命令输出/证据，禁止"跑过=完成"
3. 可回滚：所有改动主题 commit + push；不强行上重架构（单机成本现实）
4. 节点验收：每子任务产出独立验收（单测/E2E/真实输出），主控汇总后统一 commit/release

## Spec 009 真机 E2E 证据（2026-09-26）

| 验收项 | 方法 | 结果 |
|--------|------|------|
| 首页门户结构 | Playwright 1440 | 6 卡片 / 9 画廊图 / 0 admin / 0 slow+honor |
| AI 对话真实 SSE | tryingopen deepseek-v4-flash | 回复真实文本（"我是运行在 Tryingopen 上的 AI 助手…"），0 error |
| 文生图真实出图 | /v1/generate → R2 | 27s 出图，image_url 渲染成功 |
| 图生图卡 | /v1/edit 上传 | 上传按钮 + 模型加载正常 |
| Agent 真实规划 | /v1/agent/dag/plan | 4 节点 DAG（意象→创作→critic→润色） |
| 移动端 | 375/768 Playwright | 无横向滚动，触控目标 77px（≥44） |
| 管理收敛 | Playwright 断言 | adminLinks=0 slowLinks=0 |

## 历史（Phase A 参考项目对标，2026-09-22，已归档）
--- 以下保留原历史 ---
