# 听风AI v6.7.0 发布说明

## 概述

v6.7.0 聚焦 **前端体验升级（M4）**，落地 D1–D5 五项前端闭环任务，并新增前端错误遥测后端端点。本次发版纯前端体验与可观测性增强，不涉及出图/聊天核心链路行为变更。

## D1 · 动作化错误提示（P0）

错误提示从「文案」升级为「行动」，在用户遇到错误时直接给出可点击的降级路径：

- **429 限流** → 错误卡片内联「切备用 provider」下拉/胶囊（调 `/v1/providers` 拉取健康备用引擎，一键切换）。
- **401 / 未配置 Key** → 自动生成 curl 命令 + 一键复制（`navigator.clipboard` 优先，HTTP/非安全上下文降级 `execCommand`）。
- **502 / provider down** → 显示备用 provider 列表可一键用（筛 `health_status != "down"`，优先 `healthy`）。
- 落点：`frontend/src/components/Feedback.tsx`（`classifyError` / `copyToClipboard` / `ProviderOption` / `ErrorRetry` 重构）、`Generate.tsx`、`ChatPlayground.tsx`。

## D2 · ChatPlayground 会话化（P1）

- 会话列表持久化到 `localStorage`（`chatPlaygroundHistory`，增量存消息，**密钥不落盘**）。
- 多轮上下文编辑（回填 messages，`MAX_CONTEXT_MESSAGES=30`）。
- 成本/耗时展示：前端读 `/v1/chat/usage?period=1h` 渲染「近 1h 用量」行（调用数 / 成功 / 均耗时 / 成本 / 今日 tokens）。
- 切换模型保留上下文（model 仅影响请求，messages 不重置）。

## D3 · 面板移动端 / 可访问性补齐（P2）

- `Layout.tsx` 重构为移动端抽屉式侧栏：`@media (max-width: 860px)` 默认收起，`is-open` 滑入；菜单按钮 `aria-label` / `aria-expanded` / `aria-controls` 齐全。
- 导航项 `:focus-visible` 焦点态可见；点击导航项自动关闭抽屉。
- 375px / 390px 单列网格收紧；3 个断点（320/768/1440）截图无横向溢出。
- 落点：`frontend/src/components/Layout.tsx`、`index.css`。

## D4 · 落地页扩展（P2）

Vue3 落地页新增两个区：

- **FAQ 区 + 手到即用 curl**（`SectionFaq.vue`）：4 条常见问题可展开/折叠 + 一键复制完整 curl 模板（健康检查 / 同步生成 / 聊天）。
- **更新日志区 + 实时状态**（`SectionChangelog.vue`）：读 `/v1/healthz` 渲染 6 个状态胶囊（服务状态 / CF 求解 / Worker / 并发 / 排队 / DB 行数）；读静态 `/release/index.json` 渲染最近 6 个版本更新日志，可展开预览 + 跳转完整说明。
- release notes 通过 `landing/public/release/`（Vite `public/` 原路径拷贝到 dist 根）+ `index.json` 索引提供，运行时落在 `/` StaticFiles 下。

## D5 · 前端遥测（P3）

- 新增 `frontend/src/lib/telemetry.ts`：`window.onerror` / `unhandledrejection` 浅层低噪声上报，`sendBeacon` 优先 + `fetch(keepalive)` 兜底，5s 同类去重，长度截断防滥用。
- `main.tsx` 启动即安装全局监听。
- 新增后端端点：
  - `POST /v1/errors/frontend`（公开，不要求鉴权）：前端任何访客运行时错误可上报；落账于 `error_tracker.record_frontend_error`（独立计数 + ring buffer，**与后端 P0-P1 聚合隔离**，不冲淡 AUTH.001/RATE.001 口径）。
  - `GET /v1/errors/frontend`（验收用）：返回 `FE.*` 计数 + 最近 50 条明细 + 总数。
- 落点：`api/error_tracker.py`、`api/routes/admin.py`、`frontend/src/lib/telemetry.ts`、`frontend/src/main.tsx`。

## 验收

- 前端 `tsc -b` 0 错误；`vite build` 0 错误（admin + landing 双产物构建通过）。
- 新增真实 E2E `frontend/e2e-m4.cjs`（基于 playwright-core + 本地 chromium）覆盖 D1–D5 全链路：
  - D1：Generate 错误态渲染 + ChatPlayground 429 错误气泡含切备用 provider 行动（chips=4）。
  - D2：刷新会话保留 + 会话存储不含密钥 + `/v1/chat/usage?period=1h` 返回 + usage 行渲染。
  - D3：移动端菜单按钮可见 + 抽屉打开/关闭 + aria-label + 320/768/1440 截图无溢出。
  - D4：landing 无 JS 错误 + FAQ 4 条 + 更新日志区 + healthz 状态胶囊 6 + release notes 6 + curl 复制反馈「已复制 ✓」。
  - D5：onerror 上报后 `/v1/errors/frontend` 出现 `FE.RUNTIME` + error_tracker 总数增长。
  - 结果：**32 通过 / 0 失败**。
- 既有回归门禁 `npm run smoke`（e2e-smoke）：**13 通过 / 0 失败**（含新增 /security 路由懒加载）。
- 后端 `ruff check`（F/E9）`api/error_tracker.py` `api/routes/admin.py` 全部 All checks passed。
- `scripts/sync_deploy.py check`：`OK api/ 与 deploy/api/ 完全一致`（无漂移）。

## 版本统一

- `frontend/package.json` 6.7.0、`landing/package.json` 6.7.0。
- 源码注释中以 `v6.7.0` 标注的特性文档属历史特性命名，非版本号，保持不动以免误改特性追溯链。
