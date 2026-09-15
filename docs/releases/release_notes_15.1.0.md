# v15.1.0 发行说明

> 发布时间：2026-09-15 | 基于 v15.0.0（`f2d71a8`）| 工具调用安全护栏 + 桌面版三件套（托盘/通知/自升级）

## 主题：让"会用工具"变成"安全用工具"，让桌面版"有体面感"

### 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **P1-8 工具调用安全护栏** | `api/routes/agent_dag_exec.py` 双闸口：① `_exec_tool` 入口 + LLM 工具循环 `[tool:名]` 提取处过 `is_destructive_command` **PreToolUse 硬门禁**（`rm -rf /`、`git reset --hard`、`git push --force`、`DELETE FROM accounts`、`DROP TABLE`、`VACUUM INTO` 路径遍历等 11 类破坏性模式→明确拒绝文本不执行，LLM 循环快速拒绝不回调 provider）；② 真实工具调用前过 `budget_guard.check_can_spend("tool")` **预算门禁**（enforce 超限返回 BUDGET_EXCEEDED/402 拒绝文本）。`tests/test_agent_tool_guard.py` 14 用例（参数化破坏性样本/LLM 循环快速拒绝/enforce/observe/off 三态） | 复用 `IF_BUDGET_GUARD_MODE`（off 零行为变化） |
| **P1-11 桌面版三件套** | ① **托盘**：`tauri.conf.json` trayIcon + `lib.rs` 托盘菜单（显示主窗口/退出）；`IF_DESKTOP_CLOSE_TO_TRAY=1` 关窗进托盘（应用驻留、后端存活）；② **系统通知**：`tauri-plugin-notification` Rust 注册 + capability `notification:default` + 前端 Agent.tsx DAG 终态发送系统通知（动态 import 浏览器静默降级，`@tauri-apps/plugin-notification`）；③ **自升级**：`tauri-plugin-updater` + GitHub Release 静态端点 + 签名公钥 + `createUpdaterArtifacts` + capability `updater:default` | `IF_DESKTOP_CLOSE_TO_TRAY`（0）/ `TAURI_SIGNING_PRIVATE_KEY`（构建注入） |
| **P3-18 性能水线复核** | DB + Config benchmark 真实通过；Engine benchmark 本机挂起（已知环境限制，属 slow 标记默认排除，非本轮引入） | — |
| **P1-14 视觉探针复核** | Playwright 真实浏览器（API 8100 在线）：Agent 页 DAG 渲染 + 明暗主题切换 1 passed，截图 `frontend/artifacts/agent-light/dark.png`（不入库） | — |

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `pytest -m "not integration and not chaos and not slow"` | **2141 tests / 0 failures / 0 errors / 1 skipped**（+14 新用例） |
| P1-8 关联 | `test_agent_tool_guard.py + test_agent_v121::TestLLMToolLoop + test_agent_dag_exec` | 30 用例全绿 |
| ruff | `ruff check api/routes/agent_dag_exec.py tests/test_agent_tool_guard.py` | 0 error |
| 集成+混沌 | `pytest tests/integration/ + tests/chaos/`（mock cf_solver） | **49+5 passed / 0 failed** |
| 真实 E2E | `python scripts/e2e_v12.py`（全程 Mock） | **14/14 PASS** |
| 桌面编译 | `cd desktop/src-tauri && cargo check` | **编译通过**（updater/notification/tray 插件全编译，12.2s） |
| 前端 | vitest **256 passed**（+1 通知降级用例）+ tsc 0 + build 0 | 全绿 |
| 版本 | 15.0.0 → 15.1.0 全链 + dist 重建 + landing lock 8.2.3→15.1.0 修复 | 契约绿 |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，零真实付费上游调用。

### 升级说明

- **桌面版用户**：新包需签名密钥 `TAURI_SIGNING_PRIVATE_KEY` 才可构建带自升级能力的产物；托盘/通知开箱即用；`IF_DESKTOP_CLOSE_TO_TRAY=1` 可选启用关窗进托盘。
- **后端**：P1-8 前置 `IF_BUDGET_GUARD_MODE` 缺省 off（零行为变化）；生产环境建议先 `observe` 观察再 `enforce`。

### 遗留（下轮候选）

- `autoregister_loop 时序 flaky`：cerebrum 已知预存（代理池每日限额时序），本轮未触碰 account_pool/proxy_pool
- Engine benchmark 本机挂起：依赖完整引擎/求解器环境，属已知环境限制（slow 标记默认排除）
- Graft 图谱缓存待 `graft build` 刷新（本轮改动大块代码后未入库刷新）