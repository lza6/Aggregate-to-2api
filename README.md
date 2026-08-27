# 听风AI · 多提供商 AI 图像生成网关

> **逆向号池 + 自动注册 + 免费代理池 + 高并发异步队列** — 聚合多家 AI 图像生成站，统一 OpenAI 风格 API。

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-brightgreen.svg" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/docker-compose-orange.svg" alt="Docker"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-5.1.0-brightgreen.svg" alt="Version"></a>
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
git clone https://github.com/lza6/Image-to-2api.git
cd Image-to-2api/deploy

# 编辑 docker-compose.yml 按需配置（含 IF_SITEKEY / IF_FREE_PROXY 等）
docker compose up -d
```

### 方式二：本地启动

```bash
pip install -r requirements.txt

cd frontend
npm install && npm run build
cd ..

# 启动 cf_solver（独立复用的 Turnstile 求解服务）
python cf_solver/boterdrop_wrapper.py &

uvicorn api.main:app --host 0.0.0.0 --port 8100
```

访问 `http://localhost:8100` 查看首页仪表盘，`http://localhost:8100/admin` 查看 React 管理面板。

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
                               │    └─ api/worker.py      （引擎/队列/token 池）     │
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

### 🔑 聊天 API 鉴权（防滥用）

聊天端点（`/v1/chat/completions`、`/v1/messages`）受固定 Key 保护：
服务端配置环境变量 `IF_API_KEYS=<key1>,<key2>` 即启用；为空则开放。客户端三种传法任选其一：

```
Authorization: Bearer <key>
X-API-Key: <key>
?url参数 ?api_key=<key>
```

未携带/错误 Key 返回 `401 {"error":{"code":"AUTH.001",...}}`。生图主链路 `/v1/generate*` 保持公益开放不受影响。

**curl 示例：**

```bash
# OpenAI 兼容
curl -X POST https://imagefree.tingfengai.art/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TFAI_KEY" \
  -d '{"model":"tryingopen/z-ai/glm-5.3-flash","messages":[{"role":"user","content":"你好"}],"stream":true}'

# Anthropic 兼容（Claude Code）
export ANTHROPIC_BASE_URL=https://imagefree.tingfengai.art/v1
export ANTHROPIC_API_KEY=$TFAI_KEY
```
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

---

## ⚙️ 关键配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `IF_HOST` / `IF_PORT` | `127.0.0.1` / `8100` | 监听地址 |
| `IF_CF_SOLVER_URL` | `http://127.0.0.1:8001` | cf_solver 地址 |
| `IF_CORS_ORIGINS` | `*` | CORS 白名单（逗号分隔） |
| `IF_GALLERY_PASSWORD` | 空 | 画廊密码（前端不硬编码） |
| `IF_KOOKEEY_*` | 空 | Kookeey 住宅代理凭据（从环境注入，不入库） |

> **完整环境变量**：见 [`deploy/.env.example`](deploy/.env.example)（109 项模板）与 [`api/config.py`](api/config.py)（98+ 项，全部 IF_ 前缀）。

---

## 🧪 测试

```bash
# 单元测试
pytest tests/ -q

# 集成测试（需 mock cfsolver）
pytest tests/integration/ -q
```

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