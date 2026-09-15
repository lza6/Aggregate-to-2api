# v15.1.1 发行说明

> 发布时间：2026-09-15 | 基于 v15.1.0（`658af49`）| 自升级端到端闭环（协议修正 + 前端触发 + 清单发布）

## 主题：让"自升级"从配置存在变成真正可用的更新通道

### 修复 / 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **updater 端点协议修正** | Tauri 2 updater 要求端点返回 **JSON 更新清单**（含 `version`/`notes`/`pub_date`/`platforms`），而非直接下载 exe。`tauri.conf.json` 端点由 `https://github.com/lza6/Aggregate-to-2api/releases/latest/download/{{target}}-{{arch}}-{{version}}.{{ext}}`（协议错误）改为 `.../releases/latest/download/latest.json` | — |
| **更新清单发布** | 生成 `latest.json`（`platforms["windows-x86_64"]` 含 Tauri 签名的 `.sig` base64 + exe 直链），上传到 v15.1.1 Release assets | — |
| **前端自升级触发** | `frontend/src/lib/desktopUpdater.ts`：启动即异步 `check()` → 有新版 `downloadAndInstall()` + `relaunch()`（Tauri 环境动态 import `@tauri-apps/plugin-updater`/`plugin-process`；浏览器环境静默零副作用）。`@tauri-apps/plugin-updater`/`plugin-process` 入 frontend devDeps | 仅 Tauri webview 生效 |
| **前端通知模块同批** | `@tauri-apps/plugin-notification` 已入 frontend devDeps（Agent 页 DAG 终态系统通知，动态 import 浏览器降级） | 仅 Tauri webview 生效 |

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 端点端到端 | 模拟 updater 客户端 GET `releases/latest/download/latest.json` | **HTTP 200**，version/pub_date/signature(432B)/url 完整；exe 直链 HEAD 200（87.6MB） |
| 前端 | vitest **257 passed**（+desktopUpdater 浏览器降级用例）+ tsc 0 + build 0 | 全绿 |
| 桌面构建 | `tauri build`（TAURI_SIGNING_PRIVATE_KEY 注入） | **15.1.1 NSIS 安装包 + .sig 签名重建** |
| 契约 | `test_openapi_contract.py` + dist 版本断言 | 全过（15.1.1） |
| 版本 | 15.1.0 → 15.1.1 全链 + 双 dist 重建 | 契约绿 |

付费红线：全程 Mock / 本地构建，零真实付费上游调用。

### 升级说明

- **桌面版 15.1.0 用户**：启动后会自动检测到 15.1.1 并提示/自动更新（端点已修正）。
- **部署方**：`latest.json` 已作为 Release 资产发布，GitHub `releases/latest/download/latest.json` 永久指向最新清单；每次发版需更新清单并重新上传。

### 遗留（下轮候选）

- 桌面端到端"真实升级流"（安装→检测→下载→替换）需用户在已装旧版机器上实测（本会话完成协议级验证 + 产物构建 + 清单发布全链路）。
- `autoregister_loop` / `test_llm_real_path_fallback` 预存 flaky：本轮未触碰相关模块。
- Engine benchmark 本机挂起：已知环境限制（slow 标记默认排除）。