# 06 · 技术规格

> 技术栈、配置体系、数据模型、状态机。基于 `pyproject.toml`、`api/config/__init__.py`、`api/db/`、`api/account_pool.py` 等。

## 6.1 技术栈

### 6.1.1 后端

| 类别 | 技术 | 版本要求 | 用途 |
|------|------|---------|------|
| 语言 | Python | ≥3.11 | `requires-python = ">=3.11"`,用 ExceptionGroup/3.11 内置 |
| Web 框架 | FastAPI | ≥0.100 | `api/main.py`,路由+中间件+异常处理器 |
| ASGI 服务器 | uvicorn | ≥0.20 | 单进程 asyncio |
| HTTP 客户端 | httpx | ≥0.24 | 异步调上游,共享连接池 |
| 数据校验 | pydantic | ≥2.0 | `BaseModel` 请求/响应模型 |
| 配置管理 | pydantic-settings | ≥2.0 | `IF_` 前缀环境变量集中管理 |
| 数据库 | SQLite + aiosqlite | aiosqlite≥0.20 | WAL 模式,异步非阻塞 |
| 指标 | prometheus-client | ≥0.21 | `/metrics` 端点 |
| 链路追踪 | OpenTelemetry | (SDK 1.44) | OTLP gRPC 导出,tail-based 采样 |
| 测试 | pytest + pytest-asyncio | pytest≥8.0, asyncio≥0.23 | `asyncio_mode="auto"`,session loop |
| Lint | ruff | (0.6.x) | `target-version="py311"`,`line-length=120` |
| 类型检查 | mypy | (latest) | `python_version="3.11"`,per-module strict |
| 浏览器自动化 | Playwright(camoufox) | - | `cf_solver` 无头浏览器求解 Turnstile |
| 容器 | Docker | compose | `deploy/docker-compose.yml` |

### 6.1.2 前端

| 类别 | 技术 | 用途 |
|------|------|------|
| 管理面板 | React + TypeScript | `/admin`,Vite 构建,`frontend/` |
| 落地页 | Vue3 | `/`,Vite 构建,`landing/` |
| 构建工具 | Vite | 两套独立构建 |
| 图表 | (BarChart 等组件) | `frontend/src/components/` |
| 测试 | Vitest + Testing Library | `frontend/src/test/` |

### 6.1.3 部署

| 类别 | 技术 | 用途 |
|------|------|------|
| 编排 | Docker Compose | cfsolver + api 双服务,`deploy/docker-compose.yml` |
| 反代 | Caddy | 自动 HTTPS(Let's Encrypt),`/etc/caddy/Caddyfile` |
| DNS | DNSPod | `imagefree` A 记录 → 43.165.173.36 |
| CI/CD | GitHub Actions | 自动测试 + 构建 + GHCR 镜像 push |
| 备份 | crontab + `scripts/backup_db.py` | 每日 03:00 全量热备 |

## 6.2 配置体系(`api/config/`)

### 6.2.1 配置组织

pydantic-settings 集中管理,`IF_` 前缀环境变量,10 个子配置类:

| 子配置类 | 模块 | 覆盖范围 |
|---------|------|---------|
| `DBSettings` | `config/db.py` | 数据库文件/保留/批量写/连接池/base64/幂等 |
| `HTTPSettings` | `config/http.py` | host/port/proxy/UA/连接数/keepalive/上游在途 |
| `SolverSettings` | `config/solver.py` | base_url/sitekey/cf_solver_urls/节点权重/熔断/token预取 |
| `CacheSettings` | `config/cache.py` | LRU 大小/TTL/Redis |
| `ProviderSettings` | `config/provider.py` | 代理文件/免费代理/号池目标/降级阈值/falai |
| `PoolSettings` | `config/pool.py` | token 池大小/TTL/等待超时 |
| `QueueSettings` | `config/queue.py` | 队列上限/worker/自动伸缩/DLQ |
| `ObservabilitySettings` | `config/observability.py` | 健康检查/告警/日志 |
| `EditSettings` | `config/edit.py` | 图生图超时/互斥/租约/重试/代理 |
| `SecuritySettings` | `config/security.py` | 画廊密码/IP白名单/受信代理/自动封禁/CORS/安全头/API Key |

### 6.2.2 配置特性

- **空串容忍**:`_drop_blank_env` model_validator 丢弃空字符串环境变量(部署模板 `IF_XXX=` 留空不崩溃)
- **字符串布尔强转**:`_bool_str_coerce` 支持 `'1'/'true'/'yes'/'on'` → True
- **空代理归一化**:`_normalize_empty_proxy` 空串代理 → None(防 httpx `Unknown scheme` 报错)
- **代理 fallback**:未配 `IF_PROXY` 时读 `HTTPS_PROXY`/`HTTP_PROXY` 环境变量
- **服务器规格自适应**:`_apply_adaptive_defaults` 仅当用户未显式设对应环境变量时生效
- **Solver URLs 规范化**:支持字符串/列表/JSON,`IF_CF_SOLVER_URLS` 优先,单 URL fallback
- **热更新**:`_keys()`/`_admin_keys()` 每次现读,环境热更新友好
- **工厂 + 测试钩子**:`get_settings()`(lru_cache 单例)+ `reset_settings()`(测试重置)

### 6.2.3 核心配置项(节选)

> 完整列表见 `api/config/__init__.py` 的 `Settings` 类,此处仅列关键项。

#### Solver / Turnstile
- `IF_BASE_URL=https://imagefree.net`(上游)
- `IF_SITEKEY=0x4AAAAAACE-XLGoQUckKKm_`(Turnstile sitekey)
- `IF_CF_SOLVER_URL=http://127.0.0.1:8001`(单节点)
- `IF_CF_SOLVER_URLS=http://cfsolver:8001`(多节点联邦)
- `IF_SOLVER_NODE_WEIGHTS`(JSON 或 `url1=1,url2=2`)
- `IF_SOLVER_IDLE_TIMEOUT_SECONDS=0`(空闲降级备选)
- `IF_TURNSTILE_TIMEOUT=90`、`IF_TURNSTILE_POLL_INTERVAL=2.0`
- `IF_SOLVE_CIRCUIT_THRESHOLD=5`、`IF_SOLVE_CIRCUIT_PROBE_SECONDS=30`
- `IF_TOKEN_POOL_SIZE=6`、`IF_TOKEN_TARGET_WATERMARK=1`、`IF_TOKEN_URGENT_WATERMARK=0`、`IF_TOKEN_BATCH_FILL_SIZE=1`

#### HTTP / 请求体
- `IF_HOST=127.0.0.1`、`IF_PORT=8100`
- `IF_PROXY`(空=直连)
- `IF_HTTP_MAX_CONNECTIONS=100`、`IF_HTTP_KEEPALIVE=20`
- `IF_UPSTREAM_MAX_INFLIGHT=30`(自适应)
- `IF_MAX_REQUEST_BODY=8388608`(8MB)

#### 队列 / Worker
- `IF_MAX_QUEUE=2000`、`IF_ADMIN_QUEUE_MAX=200`、`IF_HIGH_QUEUE_MAX=500`、`IF_NORMAL_QUEUE_MAX=1500`
- `IF_WORKERS=10`(自适应:2C2G→4,4C8G→16)
- `IF_WORKER_AUTO=False`(默认关闭,不动态伸缩)
- `IF_WORKERS_MIN=4`、`IF_WORKERS_MAX=16`
- `IF_PERSISTENT_QUEUE_ENABLED=False`、`IF_PERSISTENT_QUEUE_DB=data/queue.db`

#### DB
- `IF_DB_FILE=data/imagefree.db`、`IF_ACCOUNT_DB_FILE=data/account_pool.db`、`IF_EMAIL_DB_FILE=data/email_registry.db`
- `IF_ROUTING_DB`(空=关闭路由持久化)
- `IF_DB_RETENTION_DAYS=365`、`IF_DB_CLEANUP_INTERVAL=21600`
- `IF_DB_BATCH_ENABLED=True`、`IF_DB_BATCH_WINDOW=0.5`、`IF_DB_POOL_SIZE=5`
- `IF_BASE64_DIR=data/imgs`、`IF_BASE64_FILE_TTL=86400`、`IF_IMG_MAX_GB=5.0`

#### Provider / 代理池 / 号池
- `IF_PROXY_FILE`(住宅代理文件)、`IF_FREE_PROXY=False`、`IF_FREE_PROXY_REFRESH_MIN=30`
- `IF_PROXY_USE_COOLDOWN_MAP=0,30,90,300,900`、`IF_PROXY_MAX_USE_PER_DAY=1`
- `IF_PROXY_TRACE_ENABLED=False`、`IF_PROXY_TRACE_TTL=3600`
- `IF_NANOBANANA_ACCOUNT_TARGET=10000`、`IF_ACCOUNT_AUTO=True`
- `IF_MOCK_REGISTER=False`、`IF_MAIL_AI_EXTRACT=False`
- `IF_PROVIDER_DEGRADE_THRESHOLD=3`、`IF_PROVIDER_RECOVER_INTERVAL=300`

#### 限流 / 安全
- `IF_API_KEYS`(空=开放)、`IF_ADMIN_KEYS`(空=继承业务)、`IF_ADMIN_KEY_OPEN=False`
- `IF_REQUESTS_PER_MINUTE=10`、`IF_RATE_TOKEN_CAPACITY=None`、`IF_RATE_TOKEN_REFILL_PER_SEC=0.0`
- `IF_IP_WHITELIST`、`IF_TRUSTED_PROXIES=127.0.0.1,::1`
- `IF_AUTO_BLOCK_ENABLED=True`、`IF_AUTO_BLOCK_THRESHOLD=3`、`IF_AUTO_BLOCK_WINDOW_SECONDS=300`、`IF_AUTO_BLOCK_TTL_SECONDS=3600`
- `IF_SECURITY_HEADERS_ENABLED=True`、`IF_CSP_ENABLED=False`
- `IF_GALLERY_PASSWORD`、`IF_GALLERY_SIGNING_SECRET`、`IF_GALLERY_SIGNING_TTL=600`
- `IF_CORS_ORIGINS=*`

#### 可观测性
- `IF_HEALTH_CHECK_INTERVAL=60`、`IF_ALERT_CHECK_INTERVAL=60`、`IF_ALERT_WEBHOOK_URL`
- `IF_LOG_DIR=data/logs`、`IF_LOG_RETENTION_DAYS=14`
- `IF_OTEL_ENABLED`、`IF_OTEL_SERVICE_NAME=imagefree-api`、`IF_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
- `IF_OTEL_SAMPLE_RATE=0.1`、`IF_OTEL_ERROR_SAMPLE_RATE=1.0`
- `IF_SLOW_LOG_ENABLED=True`、`IF_SLOW_REQUEST_MS=5000`、`IF_SLOW_LOG_SIZE=500`

#### 成本 / 预算
- `IF_USD_PER_CREDIT=0.0`(图片成本估算,0=不估算)
- `IF_COST_BUDGET_USD=0.0`(0=不启用告警)

## 6.3 数据模型

### 6.3.1 主数据库(`data/imagefree.db`)

由 `api/db/core.py` 管理,aiosqlite + WAL + busy_timeout。

| 表 | 用途 | 关键字段 |
|----|------|---------|
| `tasks` | 任务记录 | id(uuid4)、status(pending/processing/completed/error)、prompt、image_url、image_mime、duration_sec、created_at、trace_id、client_ip、user_agent、model、aspect_ratio |
| `stats_overview` | 总量统计 | 总请求/总出图/总失败/平均耗时 |
| `stats_daily` | 按日统计 | 日期/计数 |
| `stats_monthly` | 按月统计 | 月份/计数 |
| `errors` | 失败明细 | id/status/error/prompt_preview/aspect_ratio/duration_sec/created_at |
| `dlq` | 死信队列 | task_id/retries/last_error/created_at |
| `gallery`(缓存持久化) | LRU 画廊缓存持久化 | key/value/expire_at |
| `idempotency` | 幂等 key | idempotency_key/task_id/created_at(若 `IF_IDEMPOTENCY_ENABLED`) |

### 6.3.2 号池数据库(`data/account_pool.db`)

由 `api/account_pool.py` 管理。

| 字段 | 用途 |
|------|------|
| email | 账号邮箱(主键) |
| provider | 提供商前缀(nanobanana 等) |
| status | 状态(active/working/cooling/dead/registering) |
| cookie | 上游会话 cookie(better-auth session_token 等) |
| password | 注册密码(加密存储) |
| credits | 当前积分 |
| credits_used_total | 累计消耗积分 |
| images_used | 累计出图次数 |
| last_used_at | 最近借出时间 |
| checkin_at | 最近签到时间 |
| checkin_total | 累计签到次数 |
| checkin_cycle_day | 签到循环天数(1-7) |
| credits_earned_total | 累计签到积分 |
| next_claim_at | 下次可领取时间 |
| register_ip | 注册 IP |
| created_at | 创建时间 |
| cooling_until | 冷却到期时间 |
| borrow_at | 借出时间(租约) |

### 6.3.3 邮箱注册库(`data/email_registry.db`)

由 `api/email_pool.py` 管理,记录邮箱与域名注册历史。

### 6.3.4 路由持久化(`data/routing.db`,可选)

由 `api/adaptive_router.py` 管理,独立轻量 SQLite,不侵入主 DB schema。
- `IF_ROUTING_DB` 空时关闭(默认),开启后重启保留路由历史 + warm 冷启动 EWMA。

## 6.4 状态机

### 6.4.1 账号状态机(`AccountStatus`)

```
unregistered → registering → active(ok) ⇄ working
                                 ↑           │
                                 │           │ release
                                 │           ▼
                                 └── cooling(exhausted)
                                       │ 满 IF_ACCOUNT_COOLING_PERIOD(20h)
                                       ▼ 自动唤醒签到
                                     active(循环)

dead(banned):封号终态,不恢复
```

**状态别名**(兼容历史):
- `ok` ≡ `active`
- `exhausted` ≡ `cooling`
- `banned` ≡ `dead`

### 6.4.2 任务状态机

```
pending → processing → completed
                │            │
                │ timeout    │ error
                ▼            ▼
            (retry 或 DLQ) error
```

- `pending`:已入库入队,等待 worker
- `processing`:worker 取走,调用上游中
- `completed`:成功,有 `image_url`
- `error`:失败,有 `error` 字段
- 超时:`IF_TASK_HARD_TIMEOUT=480` 硬超时;`IF_GENERATE_TIMEOUT=300` 生成超时
- 重试:`IF_GENERATE_MAX_ATTEMPTS=2`,token 被拒(`Human verification failed`)自动换新 token 重试
- DLQ:重试耗尽入死信队列(`IF_DLQ_MAX_RETRIES=3`)

### 6.4.3 Solver 节点状态机(`solver_guard.SolverNodeState`)

```
CLOSED(正常) ──连续失败 threshold(5)──► OPEN(熔断 30s)
   ▲                                       │
   │                                       │ probe_interval 到
   │                                       ▼
   └──探测成功──────────────── HALF-OPEN(放行一个探测)
                                       │
                                       │ 探测失败
                                       ▼
                                     OPEN(继续熔断)

429 → RATE_LIMITED 冷却(60s)
```

- **集群级**:所有节点不可用 → 集群 OPEN,按周期放行探测
- **节点级**:单节点独立状态机,加权最少在途调度优先非 idle 节点
- **失败原因分类**:timeout/transport/http_error/rate_limit/solver_rejected/other

### 6.4.4 提供商健康状态机

```
healthy ──连续失败 IF_PROVIDER_DEGRADE_THRESHOLD(3)──► degraded
   ▲                                                  │
   │                                                  │ IF_PROVIDER_RECOVER_INTERVAL(300s) 探测
   │                                                  ▼
   └───────────────── 探测成功 ──────────────── (恢复探测中)

down:provider.health_status == "down",静态回退到能力匹配备用
```

## 6.5 风格预设与模型映射

### 6.5.1 模型风格预设(`MODEL_PRESETS`)

| 预设 | 名称 | 前缀注入 | 适用 |
|------|------|---------|------|
| default | 默认 | (无) | txt2img, img2img |
| anime | 动漫 | `anime style, high quality anime illustration, vibrant colors, detailed lineart, ` | txt2img |
| realistic | 写实摄影 | `photorealistic, ultra detailed, 8k, cinematic lighting, sharp focus, ` | txt2img |
| watercolor | 水彩 | `watercolor painting style, soft washes, delicate brushwork, translucent layers, ` | txt2img, img2img |
| ink | 水墨 | `traditional chinese ink wash painting style, minimalist, elegant negative space, ` | txt2img |
| cyberpunk | 赛博朋克 | `cyberpunk neon style, futuristic city, neon glow, high contrast, ` | txt2img, img2img |

- **应用**:`apply_model(prompt, model)` 在 prompt 前注入前缀
- **兼容**:旧版无 `/` 的 model id 自动映射为 `imagefree/<id>`

### 6.5.2 比例映射(`ASPECT_RATIOS`)

| 比例 | 分辨率 |
|------|--------|
| 1:1 | 1024x1024 |
| 3:4 | 768x1024 |
| 4:3 | 1024x768 |
| 9:16 | 576x1024 |
| 16:9 | 1024x576 |

### 6.5.3 模型命名契约

- **外部 id**:`<provider前缀>/<上游真实模型名>`,如 `nanobanana/nano-banana-pro`、`aifreeforever/gpt-image-2`、`imagefree/default`
- **能力**:`ModelSpec.capabilities` 声明 `txt2img/img2img/txt2vid/img2vid`
- **积分费率**:`ModelSpec.credits`(上游每图消耗,如 nano-banana-pro:4,4K:14)

## 6.6 错误码体系(`api/errors.py`)

分层格式 `CATEGORY.NNN`,多语言消息(zh/en),动态参数插值。

| 类别 | 错误码 | HTTP | 含义 |
|------|--------|------|------|
| AUTH | AUTH.001 | 401 | 未授权 |
| AUTH | AUTH.002 | 401 | API Key 过期 |
| AUTH | AUTH.003 | 403 | 无权(IP 封禁/风控) |
| VAL | VAL.001 | 422 | 模型不存在 |
| VAL | VAL.002 | 422 | 提示词不符合 |
| VAL | VAL.003 | 422 | 比例格式错误 |
| VAL | VAL.004 | 400 | 通用参数错误 |
| PROV | PROV.001 | 503 | 提供商不可用 |
| PROV | PROV.002 | 429 | 提供商额度耗尽 |
| PROV | PROV.003 | 503 | 求解器熔断 |
| SYS | SYS.001 | 500 | 服务器内部错误 |
| SYS | SYS.002 | 429 | 队列满 |
| SYS | SYS.003 | 404 | 资源不存在 |
| SYS | SYS.004 | 408 | 生成超时 |
| SYS | SYS.005 | 409 | 幂等 Key 冲突 |
| SYS | SYS.006 | 502 | 上游第三方不可用 |
| RATE | RATE.001 | 429 | 限流 |

- **旧版兼容**:`_LEGACY_CODE_MAP` 映射(如 `QUEUE_FULL` → `SYS.002`)
- **HTTP 状态码映射**:`STATUS_CODE_ERROR_MAP` 供异常处理器复用
- **响应格式**:`{"error": {"code": "...", "message": "...", "details": {}}}`
