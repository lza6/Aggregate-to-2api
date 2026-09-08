# 听风AI 桌面版（Tauri 2.x + React19 复用）—— 构建与运行

## 方案

**Tauri 2.x sidecar 托管 Python 后端**（已授权）：
- 桌面壳只管 UI（复用 `frontend/` React19 构建产物 `dist/`），请求 `127.0.0.1:8100`
- 后端（uvicorn + 号池/代理池/solver）在启动时由 Tauri 自动拉起（sidecar 或系统 python），关闭时回收子进程
- CSP 仅允许 `connect-src http://127.0.0.1:8100`，无 Node 渗透面

## 前置（一次性）

```bash
# 1) 安装 Rust 工具链（本机当前缺 cargo/rustc）
#    https://rustup.rs 或 winget install Rustlang.Rustup
rustup default stable
cargo install tauri-cli --locked   # 提供 `tauri` 命令

# 2) 前端 dist 需存在（Tauri 引用 frontend/dist）
cd frontend && npm run build
```

## 本地运行（开发）

```bash
cd desktop
npm install
npm run dev        # tauri dev：自动起 uvicorn:8100 + 前端 dev server:5173
```

## 打包（生产）

```bash
cd desktop
npm run build      # tauri build → 产出 NSIS 安装包（Windows）
```

可选：把后端打成 sidecar exe（免用户装 Python）：

```bash
pip install pyinstaller
pyinstaller --onefile --name uvicorn --add-data "api;api" api/main.py
# 产物放 desktop/backend/uvicorn.exe + 设 IF_DESKTOP_USE_PYINSTALLER=1
```

## 环境变量（见 .env.example）

| 变量 | 默认 | 说明 |
|---|---|---|
| `IF_DESKTOP_USE_PYINSTALLER` | 0 | 1=用 sidecar exe；0=系统 python |
| `IF_DESKTOP_MOCK_UPSTREAM` | 1 | 1=后端以 Mock 上游启动（零真实付费） |
| `IF_DESKTOP_NO_SOLVER` | 0 | 1=不拉起 cf_solver（纯聊天/DAG Mock 场景） |

## `backend_status` 命令

前端经 `@tauri-apps/api` 调用：

```ts
import { invoke } from '@tauri-apps/api/core';
const st = await invoke('backend_status');
// { ready: boolean, backend_pid?: number, solver_pid?: number, detail: string }
```