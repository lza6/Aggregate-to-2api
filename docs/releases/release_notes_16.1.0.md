# v16.1.0 发行说明

> 发布时间：2026-09-17 | 基于 v16.0.0（`557d295`）| 体验闭环 + 效率治理批（P0-4 / P1-5~8 / P2-9~12）

## 主题：从「能用」到「好用」——运行期可视化、双语、桌面深化、数据治理

### 新增（P0-4 任务实时进度 + 幂等取消 + 一键重试）

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **阶段进度事件** | 引擎在 queued/solving/generating/done 各关键点 pub `status_detail` + `progress`（5/30/80/100）阶段徽章事件（旧字段 append-only 兼容） | — |
| **幂等取消** | `POST /v1/tasks/{task_id}/cancel`：pending/processing → cancelled；已完成/已取消 → 200 幂等不落不一致；`mark_finished` 加防覆盖护栏（已取消不可被 worker 完成/异常覆盖）；worker 认领前 + acquire token 前双检查点 | `IF_TASK_CANCEL_ENABLED`(1) |
| **一键重试** | `POST /v1/tasks/{task_id}/retry` 按原参数重投 → 新 task_id（复用主链路 `_prepare`/`_submit` 校验） | — |
| **前端可视化** | Tasks 行 + Generate 运行卡：阶段徽章 + 简化进度条（轮询主路径 + SSE 增强）、运行行「取消」按钮（防重复）、失败行「重试」按钮、cancelled 状态徽章 | — |

### 新增（P1-5 公共配额响应）

| 项 | 内容 |
|---|---|
| **配额头** | `/v1/generate*`、`/v1/edit`、`/v1/chat/*` 恒携带 `X-RateLimit-Limit/Remaining/Reset`（限流关闭时注入默认 0 头）；healthz 等不受影响 |
| **429 人话** | 429 响应 JSON 补 `retry_after_seconds` + `human_hint`（中文「请求太频繁啦，X 秒后再试」）+ Retry-After 头 |
| **前端 Toast** | useApi 对 429 统一拦截 → 右上角 Toast「你太快啦，X 秒后再试」 |

### 新增（P1-6 i18n 双语）

- 零依赖 i18n 模块（`frontend/src/i18n/`）：`t()` / `useT()` / `useLang()`，localStorage + `<html lang>` 同步，en/zh **91 key 完全一致**（key 一致性测试锁定）。
- 接线 Layout 导航（16 项）/ Generate 表单 / Tasks 列表 / Gallery 操作条 / Dashboard 卡片 / ApiGuide；顶栏语言切换按钮（EN/中文）。
- landing 落地页：已有 i18n（P3-7 遗留 zh/en 平行字典），零成本复用。

### 新增（P1-7 桌面深化）

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **全局快捷键** | Ctrl+Shift+T 唤起主窗（show + unminimize + focus），Rust 侧注册无前端依赖 | `IF_DESKTOP_GLOBAL_SHORTCUT`(1) |
| **开机自启** | 托盘菜单「开机自启」CheckMenuItem 一键开关（autostart 插件） | `IF_DESKTOP_AUTOSTART`(1) |
| **通知聚合** | 批量任务终态通知合并为一条（1s 窗口：N 项完成 X 成功 Y 失败） | — |
| **深色跟随系统** | 手动 `localStorage[tf-theme]` 优先 → 未设置跟随系统（matchMedia 监听）→ CSS media 兜底；顶栏三态主题按钮 | — |
| 真机 | `cargo check` 编译通过；tauri build/NSIS 真机行为**待验证** | — |

### 新增（P1-8 历史归档 + 批量导出）

- **冷热归档**：`IF_TASK_RETENTION_DAYS=90` 到期终态任务软归档 `status='archived'`（每日 04:00 retention 流先软归档后物理清理；不物理删，详情可查，列表/统计默认退冷）
- **批量导出**：`POST /v1/admin/export/tasks?format=csv|json`（管理 Key）——时间段/提供商/模型/状态过滤，CSV UTF-8 BOM + 中文表头（Excel 兼容），JSON 完整字段 + meta，10 万行上限超限截断 `X-Truncated`，audit 记录导出动作

### 新增（P2-9/P2-10 治理）

- **成本预警**：`IF_COST_ALERT_PCT=80` 每小时评估日预算消耗 → 超阈值 webhook 推送（幂等：水位升 ≥5pp 才再推，回落复位）
- **健康自诊断报告**：`GET /v1/admin/health-report`（管理 Key）七维聚合（provider 成功率/时延、号池、邮箱池、cf_solver 联邦、队列积压、内存/SSE 连接、成本预测）JSON + Markdown；前端 Health 页「导出报告」按钮；单项失败降级不 500

### 治理（P2-11/P2-12）

- **双预存 flaky 根治**：`autoregister` 抽 `_can_fill()`/`_register_one_now()` 纯函数（脱离无限循环时序）；`llm_real_path_fallback` try/finally + `reset_settings()` 独立收尾（消除 Settings 单例串扰）
- **技术债清理**：历史日志删除、`logs/` 归档 `docs/research/`、参考文档/侦察产物归档（`.ref_scan` → `docs/research/ref-scan`、旧指南 → `docs/archived/`）

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端单测 | `pytest -m "not integration and not chaos and not slow"` | 全量 ×3 exit 0（P2-11 验收：连续 3 次 0 failures） |
| 专项 | test_task_cancel 12 + test_cost_alert 9 + test_health_report 7 + test_admin_export_tasks 5 + test_db_retention 扩展 + test_request_guard_layers 扩展 | 全绿（主控复核 137/26/… EXIT 0） |
| 前端 | `vitest run` | **293 passed / 28 files**（i18n 8 + 主题 13 + 通知聚合 5 + Tasks 4 等） |
| 前端构建 | `tsc --noEmit` + `npm run build` | 0 error；frontend+landing dist 重建 |
| 桌面 | `cd desktop/src-tauri && cargo check` | 0 error / 0 warning |
| Lint | `ruff check`（全部改动文件） | 0 error |
| E2E | `scripts/e2e_v12.py` | **33/33 PASS**（新段 14 取消/重试、15 配额头、16 导出/健康报告全过） |
| 版本 | openapi + mcp serverInfo | 全链 **16.1.0** |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，0 真实付费调用（成本预警/健康报告为本地 DB + 快照聚合）。

### 升级说明

- **取消/重试**：新增端点，前端 Tasks/Generate 已接线；`IF_TASK_CANCEL_ENABLED` 缺省开可回滚。
- **配额头**：行为增强（恒带三头），旧客户端无破坏。
- **i18n**：缺省 zh，默认行为与旧文案完全一致（zh 文案值不变）→ 零视觉回归。
- **归档**：`IF_TASK_RETENTION_DAYS=90` 缺省开启——到期历史任务从默认列表退冷（详情/导出仍可查），物理文件不动。
- **桌面 16.1.0**：快捷键/自启/深色为增量；真机 NSIS 产物待验证（无真机环境）。