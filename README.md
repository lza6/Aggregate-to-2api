# 听风AI · 多提供商 AI 图像生成网关

> **逆向号池 + 自动注册 + 免费代理池 + 高并发异步队列** — 聚合多家 AI 图像生成站，统一 OpenAI 风格 API。

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-brightgreen.svg" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/docker-compose-orange.svg" alt="Docker"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-7.7.17-brightgreen.svg" alt="Version"></a>
</p>

---

## 📋 概述

听风AI 是一个**生产级 AI 图像生成 API 网关**，将多家上游 AI 图像服务（imagefree.net、aifreeforever.com、nanobanana-pro.com 等）聚合为统一的 OpenAI 风格 `/v1/*` 接口。核心能力包括：

- **🔄 多提供商自适应路由** — MAB-EWMA 引擎结合成功率/时延/负载实时打分，自动降级/熔断
- **👥 号池自动化** — 自动注册 + 每日签到，管理 1000+ 账号无需人工干预
- **🌐 代理池轮换** — 住宅代理 + 免费代理双源，每 IP 递增冷却 + 24h 每日限额重置
- **⚡ 高并发架构** — 有界优先级队列 + Worker 池（4-16 自适应）+ Turnstile token 预取，扛 270+ RPS
- **🖥️ React 管理面板** — 独立 React 前端（/admin），图表化监控任务、提供商、号池、死信队列与实时日志
- **🔍 深度可观测性** — Prometheus 指标 + 审计日志 + 内置告警引擎 + WebSocket 实时日志 + OTel 分布式追踪
- **📡 SSE 每任务事件流** — `/v1/tasks/{id}/events` 实时推送 status/progress/result + Last-Event-ID 断线补偿
- **💬 文本对话与智能体网关 (v4.4)** — 整合 TryingOpen 匿名多模型，提供标准 OpenAI `/v1/chat/completions` 与 Anthropic `/v1/messages` 兼容端点，支持思考链、工具调用（Function Calling）与多模态 Vision，自动代理轮换突破单 IP 频控。

> 📌 **线上演示**：https://imagefree.tingfengai.art（腾讯云东京，公益开放）

---

## 🚀 快速启动

### 前置依赖

- Python 3.11+ 或 Docker
- Node.js 18+（仅构建 React 管理面板时需要）
- 网络代理（访问 imagefree.net 等上游需能直连或通过代理）
- **cf_solver（Turnstile 求解器，端口 8001）** — 见下方「外部前置依赖说明」

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/lza6/Aggregate-to-2api.git
cd Aggregate-to-2api

# ⚠ 前端产物 dist/ 不入 git（.gitignore），compose 挂载的是宿主机目录 —— 必须先在宿主机构建：
cd frontend && npm ci && npm run build && cd ..
cd landing && npm ci && npm run build && cd ..

cd deploy
# 编辑 deploy/.env（或 cp .env.production.example .env 按生产模板收紧；v7.7 起 env_file 会全量注入容器）
docker compose up -d
```

### 方式二：本地启动

```bash
pip install -r requirements.txt

# 两个前端产物都要构建（landing 挂 /，frontend 挂 /admin；缺 landing 则根路径 404）
cd frontend && npm install && npm run build && cd ..
cd landing && npm install && npm run build && cd ..

# 启动 cf_solver（独立复用的 Turnstile 求解服务；脚本位于 deploy/cf_solver/）
python deploy/cf_solver/boterdrop_wrapper.py &

uvicorn api.main:app --host 0.0.0.0 --port 8100
```

访问 `http://localhost:8100` 查看落地页，`http://localhost:8100/admin` 查看 React 管理面板。

---

## 🏗️ 架构（v4.2 拆分后）

```
调用方 ──POST /v1/generate ──► ┌────────────────────────────────────────────────┐
   (同步/异步)                  │  api/main.py（72 行组装，仅挂载路由/中间件）     │
                               │    ├─ api/routes/        （health/tasks/generate/admin）│
                               │    ├─ api/dispatch.py    （路由调度+路由记录全覆盖）│
                               │    ├─ api/dispatch_edit.py（图生图双层互斥锁）      │
                               │    ├─ api/sse_events.py  （每任务 SSE 事件流）      │
                               │    ├─ api/adaptive_router.py（MAB-EWMA 路由引擎）  │
                               │    ├─ api/lifespan.py    （9 阶段优雅关闭）         │
                               │    ├─ api/worker/        （引擎/队列/token 池/健康）    │
                               │    ├─ api/account_pool.py（号池 aiosqlite）       │
                               │    ├─ api/email_pool.py  （邮箱池+email_sources/）│
                               └──────────────────────────────────────────────────┘
```

### 核心设计

| 特性 | 说明 |
|------|------|
| **入口 50 RPS** | 请求仅做「校验→SQLite 入库→入队→返回」毫秒级 |
| **MAB-EWMA 路由** | Score=(成功率/log10时延)×负载惩罚，10% 探索率 + 熔断器 |
| **SSE 事件流** | 每任务 subscribe/publish/replay，Last-Event-ID 断线补偿 |
| **DB 批量写** | 0.2s 窗口合并 commit |
| **防护** | SSRF IP 绑定、CORS 白名单可配、画廊密码不硬编码 |
| **数据安全 (v7.1)** | SQLite 在线热备（VACUUM INTO）+ 恢复脚本 + 备份演练 SOP |
| **全链路可观测 (v7.2)** | OTel tail-based 采样（错误 100%+正常 10%）+ SSE 事件流指标看板 + per-IP 分片锁限流 |
| **生产收紧模板 (v7.3)** | deploy/.env.production.example：CORS 白名单/独立管理 Key/CSP/防滥用限流一键收紧 |
| **公开合规 (v7.2)** | landing 中英双语 + 隐私声明/DPA 页（#/privacy） |

---

## 🔌 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /` | — | 中文仪表盘首页 |
| `GET /admin` | — | React 管理面板 |
| `POST /v1/generate` | 同步 | 文生图/文生视频，阻塞到出图 |
| `POST /v1/generate/async` | 异步 | 立即返回 task_id，轮询查结果 |
| `POST /v1/edit` | 异步 | 图生图（AI 照片编辑） |
| `GET /v1/tasks` | — | 任务列表（分页/筛选/排序） |
| `GET /v1/tasks/{id}` | — | 查询单任务结果 |
| `GET /v1/tasks/{id}/events` | SSE | **每任务事件流（status/progress/result/error + 心跳 + Last-Event-ID）** |
| `GET /v1/events/tasks` | SSE | 全局任务广播（向后兼容） |
| `GET /v1/models` | — | 全提供商模型列表（生图 + 文本对话） |
| `POST /v1/chat/completions` | 同步/SSE | **OpenAI 兼容对话补全（支持流式/非流式/思考链/工具调用/多模态）** |
| `POST /v1/messages` | 同步/SSE | **Anthropic 协议端点（Claude Code / Continue / Cursor 直接接入）** |
| `GET /v1/chat/models` | — | **聊天模型目录（含上下文长度、Token单价、工具/图片能力标签）** |
| `GET /v1/chat/auth/status` | — | **鉴权状态探测（是否需要 Key，不泄露 Key 本体）** |
| `GET /v1/chat/usage` | — | **全站聊天实时用量（Token消耗、调用量、时延、各模型分布）** |
| `GET /v1/chat/remaining` | — | **基于代理池多出口自动推算的实时可用额度预测** |

### 🔑 鉴权与开放策略（v7.7.17）

- **生图 / 聊天**：公益开放，**不限 Key**（仅 per-IP 限速防刷）。`IF_API_KEYS` 配置后可用于 `/v1/stats` 等可选鉴权场景，但不限制生图/聊天调用。
- **管理面写操作**（封禁/解封、DLQ 清空/重试、日志 WS）：需独立**管理 Key**（`IF_ADMIN_KEYS`），与业务 Key 分离轮换。站长在管理面板「📖 API 指南」页或「🛡️ 安全风控」页顶部横幅保存一次管理 Key，全站写操作自动携带 Bearer 头。

```
业务 Key（IF_API_KEYS）：生图/聊天可选鉴权（v7.7.17 起不限 Key）
管理 Key（IF_ADMIN_KEYS）：面板写操作强制鉴权（封禁/DLQ/日志）
```

**curl 示例（生图无需 Key）：**

```bash
# OpenAI 兼容
curl -X POST https://imagefree.tingfengai.art/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"tryingopen/z-ai/glm-5.3-flash","messages":[{"role":"user","content":"你好"}],"stream":true}'

# Anthropic 兼容（Claude Code）——聊天不限 Key，API_KEY 可填任意占位
export ANTHROPIC_BASE_URL=https://imagefree.tingfengai.art/v1
export ANTHROPIC_API_KEY=any-placeholder
```

> 📖 **内置 API 调用指南页**：管理面板 `/admin/api-guide` 提供 Base URL + 一键复制的 curl/Python/JS 示例，新接入方可直接照抄。

> 🌐 **生产真实 IP 恢复**（v7.7+）：`deploy/docker-compose.yml` 固定子网 `172.28.0.0/16` + `Dockerfile.api` 的 uvicorn `--proxy-headers --forwarded-allow-ips=172.28.0.0/16` + `.env` 的 `IF_TRUSTED_PROXIES=172.28.0.1` 三者配合，让 Caddy 反代追加的 `X-Forwarded-For` 被正确解析，任务列表显示真实公网 IP 而非"内网私有地址"。
| `GET /v1/providers` | — | 提供商状态看板 |
| `GET /v1/stats` | — | 用量统计（按日/月拆分） |
| `GET /v1/gallery` | — | 最近作品画廊（支持密码保护） |
| `GET /v1/healthz` | — | 健康检查 + solver 求解质量指标 |
| `GET /v1/diagnostics` | — | 只读一键体检 |
| `GET /v1/routing/records` | — | **自适应路由记录 + 节点评分快照** |
| `GET /v1/proxy-pool` | — | 代理池实时状态 |
| `GET /v1/proxy-pool/subscribe` | — | 代理订阅导出（ss:// + socks5:// + vmess://，无 http://） |
| `GET /v1/account-pool` | — | 号池看板 |
| `GET /v1/dead-letter-queue` | — | 死信队列（查询/重试/清空） |
| `GET /v1/meta` | — | sitekey / aspect_ratios / gallery_requires_password |
| `GET /v1/logs` / `GET /v1/logs/ws` | — / WS | 日志快照 + WebSocket 实时日志 |
| `GET /v1/slow` / `/v1/slow/view` | — | 慢请求画像 + 静态看板 |
| `GET /metrics` | — | Prometheus 指标 |
| `GET /docs` | — | Swagger 交互文档 |

---

## 🧩 提供商清单

| 提供商 | 上游 | 能力 | 认证 | 风控 |
|--------|------|------|------|------|
| `imagefree` | imagefree.net | txt2img / img2img | Turnstile token | 直连 |
| `aifreeforever` | aifreeforever.com | txt2img / img2img（≤3 参考图） | 匿名 + Turnstile | **每 IP 每日限额 → 每请求轮换代理** |
| `nanobanana` | nanobanana-pro.com | txt2img / img2img | better-auth cookie + 号池 | 每日签到续额 |
| `tryingopen` | tryingopen.com | **chat / chat_tools / chat_vision** | **完全匿名（13+ 开源大模型）** | **单 IP 限流 20次/h → 代理池自动故障轮换** |
| `falai` | fal.ai | **txt2vid / img2vid（minimax-h3-max）** | 匿名 + Kasada x-is-human（纯算） | **每 IP 每天 5 次免费 → 代理池轮换** |

---

## ⚙️ 关键配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `IF_HOST` / `IF_PORT` | `127.0.0.1` / `8100` | 监听地址 |
| `IF_CF_SOLVER_URL` | `http://127.0.0.1:8001` | cf_solver 地址 |
| `IF_CORS_ORIGINS` | `*` | CORS 白名单（逗号分隔） |
| `IF_GALLERY_PASSWORD` | 空 | 画廊密码（前端不硬编码） |
| `IF_KOOKEEY_*` | — | **已废弃**（v6.8.0 kookeey 移除，配置不生效） |

> **完整环境变量**：见 [`deploy/.env.example`](deploy/.env.example)（160+ 项模板）、[`api/config/`](api/config/)（分组配置包，全部 IF_ 前缀）与 [`deploy/.env.production.example`](deploy/.env.production.example)（生产收紧模板）。注意：仅出现在模板中但 `api/config/` 无 `validation_alias` 映射的变量不生效（模板尾部有废弃变量清单）。

---

## 🧪 测试

> **门禁口径**：`pyproject.toml` 的 `addopts` 内置 `-m "not slow"`，所以不带 `-m` 的 `pytest` 只排除 `slow` 标记，但**仍会收集并运行 `integration`/`chaos` 标记的测试**——这两类需要先启动 mock cf_solver，否则失败。因此新开发者首跑推荐用下方第 1 条的完整 `-m` 过滤口径（等价于 CI 单测口径，无需 mock cfsolver）。注意：命令行 `-m` 会**覆盖**（而非合并）`addopts` 的 `-m "not slow"`，所以需要把 `not slow` 一并写进 CLI `-m`，不能省略。

```bash
# 1. 默认门禁（CI 单测口径，无需 mock cfsolver，推荐新开发者先跑这个）
pytest -m "not integration and not chaos and not slow"

# 2. 显式指定目录（与第 1 条等价，亦可 -q）
pytest tests/ -q -m "not integration and not chaos and not slow"

# 3. CI 全量口径（单测 + 集成 + 混沌，不含 slow）——包含 integration/chaos，需先启动 mock cf_solver（见第 4 条）
pytest tests/ -q -m "not slow"

# 4. 集成测试（需先启动 mock cf_solver，见 CI 流程）
python scripts/mock_cfsolver.py --port 8001 &
pytest tests/integration/ -q

# 5. 慢速/真实网络用例（默认跳过，按需显式放行）
pytest -m slow -q
```

> **CI 参考**：[`.github/workflows/ci.yml`](.github/workflows/ci.yml) — 单测 `-m "not integration and not chaos and not slow"`（覆盖门禁 80%）、集成与混沌分轮 `-m "integration"` / `-m "chaos"`（v7.7 起拆分，防组合串扰）、`ruff check api/`、frontend 门禁（tsc+vitest+build）。`sync_deploy.py` 已于 v6.8.0 废除（build context 改为仓库根），CI 不再运行。

### 前端（管理面板）开发与测试

```bash
cd frontend
npm install          # 首次
npm run dev          # 开发模式（Vite HMR，代理 /v1 与 /metrics 到 127.0.0.1:8100）
npm run build        # tsc -b && vite build（CI frontend-gate 同口径）
npm run test         # Vitest 全量单测（CI 门禁之一）
npm run test:watch   # 监听模式
npm run smoke        # E2E 冒烟（需先 npm run build + npm run preview 或本地 API）
node resp-audit.cjs  # 响应式 4 断点审计（375/768/1024/1440，截图归档 .benchmarks/）
```

> **E2E 前置**：`npm run smoke` 默认打 `http://localhost:4510`（`vite preview`）。先 `npm run build && npm run preview -- --port 4510`，或设 `E2E_BASE` 指向运行中的服务（如 `E2E_BASE=https://imagefree.tingfengai.art node e2e-smoke.cjs`）。

---

## 🧯 故障排查

- **健康检查降级**：`GET /v1/healthz` 看 `cf_solver`/`solver_status`，详见表。
- **任务 pending**：`GET /v1/diagnostics` 看 worker `stale`、队列深度、磁盘。
- **号池空**：`GET /v1/account-pool` 看账号数；nanobanana 依赖每日签到续额。

---

## 📄 许可证
[MIT License](LICENSE)

---

> **免责声明**：本项目仅供学习和研究目的。使用本项目时请遵守相关法律法规和上游服务条款。
