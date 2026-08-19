---
name: imagefree-workflow
description: 听风AI imagefree_api 项目开发工作流指南。涉及本仓库任何开发任务（改后端 api/、加提供商 providers/、改前端 frontend/src/、写测试 tests/、部署 deploy/）时先加载本技能，获取项目结构、开发/测试/部署流程与关键文件索引。Windows 环境，Python 3.11 + FastAPI + React。
---

# imagefree-workflow — 听风AI 项目开发指南

## 1. 项目概述

**听风AI（imagefree_api）是一个生产级 AI 图像生成 API 网关**，将多家上游 AI 图像服务（imagefree.net、aifreeforever.com、minimaxh3.ai、nanobanana-pro.com）聚合为统一的 OpenAI 风格 `/v1/*` 接口。

核心能力：

- **多提供商路由** — 按 `model` 参数自动路由到对应上游，自动降级/熔断
- **号池自动化** — 自动注册 + 每日签到，管理 1000+ 账号
- **代理池轮换** — 住宅代理 + 免费代理双源，每 IP 递增冷却 + 24h 每日限额重置
- **高并发架构** — 有界优先级队列 + Worker 池（4-16 自适应）+ Turnstile token 预取，扛 270+ RPS
- **零鉴权部署** — 开箱即用；Docker Compose 一键部署

技术栈：Python 3.11+ / FastAPI / uvicorn / SQLite / httpx / pydantic-v2 / React 18 + Vite + TS。

线上演示：https://imagefree.tingfengai.art （腾讯云东京，公益开放）

## 2. 代码结构说明

```
imagefree-2ai/
├── api/                        # 后端源码（核心）
│   ├── main.py                 # FastAPI 入口 + 全部端点（/v1/*）
│   ├── config.py               # Settings（pydantic-settings，IF_* 环境变量前缀）
│   ├── worker.py               # 高并发引擎：优先级队列 + worker 池 + token 预取
│   ├── db.py                   # SQLite 持久化 + 0.2s 批量写合并 + 连接池
│   ├── errors.py               # 分层错误码（CATEGORY.NNN）+ AppError
│   ├── providers/              # 多提供商适配器
│   │   ├── base.py             # Provider 抽象基类 + ModelSpec + GenerationResult
│   │   ├── registry.py         # 提供商注册、路由、健康检查
│   │   ├── imagefree.py        # imagefree.net（Turnstile token 认证）
│   │   ├── aifreeforever.py    # 每 IP 每日限额 → 每请求轮换代理
│   │   ├── minimaxh3.py        # Auth.js cookie + 号池，用完即弃
│   │   └── nanobanana.py       # better-auth cookie + 号池，每日签到
│   ├── turnstile_client.py     # cf_solver 客户端（:8001）
│   ├── solver_guard.py         # 熔断器 + 求解质量统计
│   ├── proxy_pool.py           # 住宅代理池 + 冷却策略
│   ├── free_proxy_fetcher.py   # 免费代理池抓取
│   ├── account_pool.py         # 号池管理（账号多路复用）
│   ├── registerer.py           # 自动注册（minimaxh3 / nanobanana）
│   ├── email_pool.py           # 邮箱池
│   ├── cache.py                # LRU 缓存
│   ├── retry_policy.py         # 重试策略（指数退避 + jitter）
│   ├── base64_store.py         # base64 文件缓存（图片与 DB 分离）
│   ├── semaphore_manager.py    # 并发信号量管理
│   ├── audit.py / alerting.py / telemetry.py / metrics_ext.py / log_ws.py / log_buffer.py
│   ├── health.py / context.py / cache_warmup.py
│   └── docs.html               # 中文仪表盘首页（后端直出）
├── frontend/src/               # React 仪表盘（Vite + TS）
│   ├── App.tsx / main.tsx / api.ts
│   ├── pages/                  # Dashboard / Tasks / Providers / Accounts / DLQ / Logs
│   └── components/             # StatCard / ProviderCard / Gallery / BarChart / Layout
├── tests/                      # 300+ 测试用例
│   ├── test_*.py               # 单元测试（顶层）
│   ├── integration/            # 集成测试（全流程/熔断/DLQ/编辑流/限流/超时）
│   ├── chaos/                  # 故障注入（test_fault_injection.py）
│   └── performance/            # 压测（test_benchmark / test_stress）
├── scripts/                    # 运维/验证脚本
│   ├── e2e_validate.py         # E2E 验证（--mode mock / real）
│   ├── sync_deploy.py          # 同步代码到 deploy/ 目录
│   ├── inject_accounts.py / loadtest.py / verify_chain.py / 等
├── deploy/                     # 生产部署资产
│   ├── docker-compose.yml      # cfsolver(8001) + api(8100)
│   ├── Dockerfile.api / Dockerfile.cfsolver
│   └── api/                    # 部署用后端副本（由 api/ 同步）
├── data/                       # 运行时数据（*.db、imgs/、.deploy/）
├── cf_solver/                  # Turnstile 求解服务（boterdrop_wrapper.py）
├── start.ps1 / start.bat       # Windows 一键启动
└── pyproject.toml              # pytest 配置（asyncio_mode=auto）
```

### 代码流关键路径

1. **请求入口**：`POST /v1/generate` → `main.py:generate_sync` → 校验模型/比例 → SQLite 入库 → 入优先级队列 → 立即返回 task_id
2. **后台执行**：`worker.py:Engine`（worker 池 4-16 自适应）→ 取队列 → 从 `TokenPoolManager` 取 token → 路由 provider → 上游调用 → `db.mark_finished`
3. **异步任务**：`/v1/generate/async` 立即返回 task_id，客户端轮询 `/v1/tasks/{id}`

## 3. 开发工作流

```
1. 理解现状 → 验证: 用 graft/codegraph 查符号、调用链，读相关测试
2. 规划    → 验证: 明确改动范围，列出影响文件
3. 实现    → 验证: 改动最小化（KISS / 不重构没坏的东西）
4. 测试    → 验证: pytest 全绿 + 相关测试通过
5. 审查    → 验证: 自审 checklist（错误处理/命名/不可变性）
6. 提交    → 验证: 约定式提交（feat/fix/refactor/docs/test/chore/perf/ci）
```

### 规则

- **先思考再编码**：不假设，不隐藏困惑，展示权衡。
- **简洁优先**：最少代码解决问题，不做推测性工作。
- **精准修改**：只改必须改的，不重构没坏的东西；发现无关死代码只提一下，不要删。
- **组织方式**：按领域/功能组织（providers/、tests/integration/），多小文件优于大文件（文件 <800 行）。
- **参考文档**：改动前查 `docs/`、`graft/INDEX.md`、`.wolf/cerebrum.md`（含 Do-Not-Repeat 与 Key Learnings）。

### 常见改动模式

- **新增提供商**：新建 `api/providers/<name>.py` 继承 `Provider` 基类 → 在 `registry.py` `bootstrap()` 注册 → 加模型规格 → 写 `tests/test_providers.py` 用例 → 同步到 `deploy/api/`。
- **新增端点**：在 `api/main.py` 添加 handler + `GenerateRequest`/`EditRequest` 模型 → 校验走 `errors.py` 的 `AppError`/`error_response` → 补测试。
- **新增配置项**：在 `api/config.py` 对应 Settings 分组加字段（`IF_*` 前缀）→ `.env.example` 同步 → `config.py:validate()` 校验。
- **前端改动**：改 `frontend/src/` → `npm run build` 产出 `frontend/dist/` → 让后端 `docs.html` 载入（静态资源走 `api/static/`）。

## 4. 测试指南

```bash
# 全量单元测试
pytest tests/ -q

# 覆盖率（CI 门槛 70%）
pytest tests/ -q --cov=api --cov-report=term --cov-fail-under=70

# 单文件
pytest tests/test_worker_auto_scale.py -q

# 异步测试：pyproject 已配置 asyncio_mode=auto，测试函数直接 async def 即可
```

- 测试目录约定：单元测试放 `tests/test_*.py` 顶层；集成走 `tests/integration/`；故障注入 `tests/chaos/`；压测 `tests/performance/`（pytest-benchmark marker）。
- Mock E2E（零真实求解消耗）：`python scripts/e2e_validate.py --mode mock`
- 真实 E2E（需 cf_solver :8001 + 代理）：`python scripts/e2e_validate.py --mode real`
- **注意**：E2E 倾向于真实上游接口；本地开发善用 `--mode mock` 避免消耗上游额度。
- 新增功能必须有对应测试，TDD（先写测试 RED → 实现 GREEN → 重构 IMPROVE）。

## 5. 部署指南

### 线上环境（腾讯云东京，公益开放）

```
imagefree.tingfengai.art ──> Caddy(Caddyfile) ──> api:8100 (Docker)
                                             └──> cfsolver:8001 (Docker，仅内网)
```

### 方式一：Docker Compose（生产推荐）

```bash
cd deploy
# 编辑 docker-compose.yml 按需配置（示例值已在文件中）
docker compose up -d --build
```

- `cfsolver` 服务不暴露公网端口，仅 compose 内网供 `api` 访问；`api` 通过 `depends_on: condition: service_healthy` 等待 solver 就绪。
- 数据卷 `./data:/app/data` 挂载 SQLite 与图片。
- 健康检查：`GET /v1/healthz` 返回 `status in (ok, degraded)` 视为健康。

### 方式二：本地/Windows 启动

```powershell
# PowerShell（推荐，含 .venv 自动检测）
.\start.ps1

# 或手动两步
python cf_solver/boterdrop_wrapper.py &   # cf_solver :8001
uvicorn api.main:app --host 0.0.0.0 --port 8100
```

### 部署前检查清单

- [ ] `pytest tests/ -q --cov=api --cov-fail-under=70` 通过
- [ ] `.env.example` 中新增的配置项已同步
- [ ] 后端改动已用 `python scripts/sync_deploy.py` 同步到 `deploy/api/`
- [ ] `docker compose build` 无报错（或至少 import 校验通过）
- [ ] 密钥/代理地址无硬编码（用 `IF_*` 环境变量）

## 6. 常见问题

| 问题 | 排查 |
|------|------|
| 生成任务一直 pending | 查 worker 是否运行；`GET /v1/healthz` 看 solver 质量；`GET /v1/tasks` 任务状态；查 `data/*.db` 或 `/v1/logs` |
| Turnstile 求解熔断（solver OPEN） | `GET /v1/healthz` 看 `solver` 段；连续失败达阈值后熔断自动恢复（`solver_guard.py`）；检查 cf_solver :8001 可达性 |
| 提供商倍率/限额（rate limited） | 查看熔断/降级是否触发；aifreeforever 需免费代理池（`IF_FREE_PROXY=1`）；minimaxh3/nanobanana 需号池 |
| 某 provider 突然不可用 | `GET /v1/providers` 看状态；registry 自动降级到可用 provider；确认上游面额/风控 |
| 重启后任务中断 | 持久化队列 → 重启后 `db.recover_stale_tasks` 续跑；死信入 `GET /v1/dead-letter-queue` |
| SQLite 锁/"database is locked" | 是否同时开了多进程写同一个 db；写走 `db.py` 批量写合并（0.2s 窗口）；`_create_conn` timeout 默认 5s |
| 前端改了不生效 | 重新 `npm run build`（dist 由后端托管）；确认静态路径指向 `frontend/dist` |
| Windows curl 走代理 https 报 SSL | `curl --ssl-no-revoke`；参考 memory 中 windows-curl-ssl-revoke |

## 7. 关键文件索引

| 关注点 | 文件 |
|--------|------|
| 全部 HTTP 端点 | `api/main.py` |
| 配置项（环境变量） | `api/config.py` + `.env.example` |
| 队列/worker/token 池 | `api/worker.py` |
| SQLite/批量写/查询 | `api/db.py` |
| 错误码/异常 | `api/errors.py` |
| 提供商抽象与注册 | `api/providers/base.py`、`api/providers/registry.py` |
| 上游客户端（imagefree） | `api/imagefree_client.py`、`api/providers/imagefree.py` |
| Turnstile 求解与熔断 | `api/turnstile_client.py`、`api/solver_guard.py` |
| 代理池 | `api/proxy_pool.py`、`api/free_proxy_fetcher.py` |
| 号池/注册 | `api/account_pool.py`、`api/registerer.py`、`api/email_pool.py` |
| 缓存/文件分离 | `api/cache.py`、`api/base64_store.py` |
| 可观测性 | `api/telemetry.py`、`api/metrics_ext.py`、`api/alerting.py`、`api/audit.py`、`api/log_ws.py` |
| 前端仪表盘 | `frontend/src/App.tsx`、`frontend/src/pages/*`、`frontend/src/components/*` |
| 测试配置 | `pyproject.toml`（pytest asyncio_mode=auto） |
| 部署资产 | `deploy/docker-compose.yml` |
| 上线演示/文档 | `README.md`、`docs/`、`workflow_status.md` |
| 运行时数据 | `data/*.db`、`data/imgs/` |

### 快速定位建议

- **结构性问题**（"X 是怎么工作的"、"改 X 会影响谁"）：优先 graft / codegraph 工具（本仓库已索引），比 grep+read 少一个数量级 token，且包含调用链与 file:line。
- **字面问题**（找某个字符串、统计出现位置）：用 Grep。
- **具体符号源码**：`graft ask --source` / codegraph node / Read 单文件对应行段。

## 附：imagefree-rules.md

代码规范、命名约定、错误处理模式、测试要求详见同目录 [imagefree-rules.md](./imagefree-rules.md)。