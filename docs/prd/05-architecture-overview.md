# 05 · 架构概览

> 基于 `api/main.py`、`api/lifespan.py`、`api/worker/engine.py`、`deploy/docker-compose.yml` 与 `docs/architecture-evolution.md` 绘制。

## 5.1 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        公网调用方                                    │
│  OpenAI SDK · Cherry Studio · Cursor · NextChat · curl · 浏览器      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTPS
                  ┌────────▼─────────┐
                  │   Caddy 反代     │ 自动 HTTPS(Let's Encrypt)
                  │ imagefree.tingfengai.art │
                  └────────┬─────────┘
                           │ 反代 127.0.0.1:8100
┌──────────────────────────▼──────────────────────────────────────────┐
│                    Docker Compose: imagefree-network                 │
│                                                                       │
│  ┌────────────────────────┐         ┌────────────────────────────┐   │
│  │   cfsolver(8001)       │         │   api(8100)                 │   │
│  │   camoufox 无头浏览器   │ ◄───── │   FastAPI + uvicorn          │   │
│  │   Turnstile 求解        │  HTTP  │   asyncio 单进程             │   │
│  │   mem_limit: 1024m     │         │   mem_limit: 512m           │   │
│  │   cpus: 2              │         │   cpus: 2                   │   │
│  └────────────────────────┘         └──────────┬─────────────────┘   │
│                                                 │                     │
│                                     ┌───────────▼──────────────┐     │
│                                     │   路由层 api/routes/       │     │
│                                     │   health/tasks/generate/  │     │
│                                     │   admin/chat/security/    │     │
│                                     │   ecosystem                │     │
│                                     └───────────┬──────────────┘     │
│                                                 │                     │
│                  ┌──────────────────────────────▼──────────────┐     │
│                  │   调度层 dispatch.py / dispatch_edit.py        │     │
│                  │   鉴权 → 校验 → INSERT(SQLite) → 入队 → 返回    │     │
│                  └──────────┬───────────────────────┬───────────┘     │
│                             │                       │                 │
│              ┌──────────────▼──────┐    ┌───────────▼────────────┐    │
│              │ worker/engine.py    │    │  api/db/ 数据层         │    │
│              │ 优先级队列+worker池  │    │  aiosqlite + WAL       │    │
│              │ ┌──────────────────┐│    │  imagefree.db          │    │
│              │ │ token_pool.py    ││    │  account_pool.db      │    │
│              │ │ 双水位+批量填充  ││    │  email_registry.db     │    │
│              │ └────────┬─────────││    │  routing.db           │    │
│              └──────────┼──────────┘    └────────────────────────┘    │
│                         │                                             │
│           ┌─────────────▼──────────────────────────────────┐          │
│           │   providers/ 多提供商网关                        │          │
│           │   ┌────────────┐ ┌──────────────┐ ┌───────────┐│          │
│           │   │ imagefree  │ │ aifreeforever│ │nanobanana ││          │
│           │   │ Turnstile  │ │ 每 IP 限额   │ │ 号池签到  ││          │
│           │   └────────────┘ └──────────────┘ └───────────┘│          │
│           │   ┌────────────┐ ┌──────────────┐               │          │
│           │   │ falai      │ │ tryingopen   │  registry.py  │          │
│           │   │ 视频生成    │ │ 匿名对话     │  MAB-EWMA 路由│          │
│           │   └────────────┘ └──────────────┘               │          │
│           └─────────────────────────────────────────────────┘          │
│                                                                         │
│           ┌─────────────────┐ ┌──────────────┐ ┌──────────────┐       │
│           │ account_pool.py  │ │ email_pool.py│ │ proxy_pool.py│       │
│           │ 号池状态机        │ │ 9 源邮箱池   │ │ 住宅+免费双源│       │
│           └─────────────────┘ └──────────────┘ └──────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
                           │
                  ┌────────▼─────────────────────┐
                  │   上游 AI 生成服务             │
                  │  imagefree.net · nanobanana-  │
                  │  pro.com · aifreeforever.com │
                  │  fal.ai · tryingopen.com     │
                  └──────────────────────────────┘
```

## 5.2 分层架构

项目采用清晰的分层架构,每层职责单一,层间通过明确契约交互:

| 层 | 模块 | 职责 |
|----|------|------|
| **入口层** | `api/main.py` | FastAPI 应用组装:路由挂载、中间件(CORS/安全头/请求上下文/请求体上限)、全局异常处理器、前端管理面板与落地页挂载、生命周期 |
| **路由层** | `api/routes/` | HTTP 端点定义,按功能域拆分(health/tasks/generate/admin/chat/security/ecosystem),不含业务逻辑 |
| **调度层** | `api/dispatch.py`、`api/dispatch_edit.py` | 鉴权 → 校验 → INSERT(SQLite) → 入队 → 返回,统一同步/异步提交前置,图生图跨进程互斥与代理池 |
| **引擎层** | `api/worker/engine.py`、`api/worker/token_pool.py` | 有界优先级队列 + worker 池 + 多 key token 池预取,后台消费任务 |
| **路由引擎** | `api/adaptive_router.py`、`api/providers/registry.py` | MAB-EWMA 自适应路由打分,降级/熔断状态机,跨商能力匹配降级 |
| **提供商层** | `api/providers/` | 上游抽象基类 `Provider`/`ChatProvider` + 各上游实现(imagefree/aifreeforever/nanobanana/falai/tryingopen) + `ActionSniffer` |
| **资源池层** | `api/account_pool.py`、`api/email_pool.py`、`api/proxy_pool.py` | 号池(状态机+签到)、邮箱池(9源)、代理池(住宅+免费双源) |
| **数据层** | `api/db/` | aiosqlite + WAL + 批量写,任务/统计/画廊/DLQ/幂等/路由持久化 |
| **存储适配层** | `api/storage/` | `StorageAdapter` 抽象,SQLite(默认)/Redis(集群)双实现,前瞻能力未接线 |
| **可观测层** | `api/metrics_ext.py`、`api/telemetry.py`、`api/log_ws.py`、`api/audit.py`、`api/slow_log.py`、`api/sse_stats.py` | Prometheus + OTel + WebSocket/SSE 日志 + 审计 + 慢日志 + SSE 统计 |
| **配置层** | `api/config/` | pydantic-settings,IF_ 前缀环境变量,10 个子配置类,服务器规格自适应 |
| **安全层** | `api/auth.py`、`api/request_guard.py`、`api/solver_guard.py` | 鉴权分层、限流四层、IP 风控、solver 熔断联邦 |

## 5.3 核心组件

### 5.3.1 高并发执行引擎(`api/worker/engine.py`)

```
请求路径(毫秒级)                      后台路径(秒级)
─────────────                        ──────────────
POST /v1/generate                     worker 池(IF_WORKERS=10)
  │ _guard(鉴权+限流)                   │ 从优先级队列取任务
  │ _validate(模型/比例校验)              │ acquire token(token_pool)
  │ INSERT tasks(SQLite,毫秒级)          │ provider.generate(调上游)
  │ engine.submit(入队,内存)             │ 轮询上游结果
  │ 立即返回 task_id                     │ 下载图片(可选)
  ▼                                     │ INSERT 结果 + 事件
                                        │ publish SSE event
                                        ▼
                              优先级队列(0=admin/1=high/2=normal)
                              容量:admin=200/high=500/normal=1500
```

**设计要点**:
- **入口快**:请求只做校验+入库+入队,不在请求路径同步做慢操作(50 RPS,4ms/请求)
- **后台慢**:真正生成由 worker 池消费(6-30s/张)
- **优先级队列**:`CountedPriorityQueue` 支持 per-priority 上限,防 admin 挤占 normal
- **token 预取**:后台预取协程(per-key)持续补满 token 池,请求来临时直接拿现成 token
- **事件驱动补池**:池空 acquire 置位 need_event 立即唤醒预取,替代 sleep 轮询

### 5.3.2 Token 池管理器(`api/worker/token_pool.py`)

```
              ┌─────────────────────────────────────┐
              │       TokenPoolManager              │
              │  ┌─────────────┐  ┌──────────────┐  │
              │  │ direct 池   │  │ per-proxy 池 │  │
              │  │ 目标水位 5  │  │ 空闲回收 90s │  │
              │  └──────┬──────┘  └──────┬───────┘  │
              │         │                │           │
              │  ┌──────▼────────────────▼───────┐  │
              │  │   acquire(请求来)              │  │
              │  │   池空 → need_event → 唤醒预取 │  │
              │  └────────────────────────────────┘  │
              │  ┌────────────────────────────────┐  │
              │  │   后台预取协程(per-key)        │  │
              │  │   双水位:                      │  │
              │  │   - target(维持)               │  │
              │  │   - urgent(批量并发填充)       │  │
              │  └──────────────┬─────────────────┘  │
              └─────────────────┼────────────────────┘
                                │
                   ┌────────────▼────────────┐
                   │  solver_guard 熔断门控  │
                   │  OPEN → 暂停新求解      │
                   │  (快速失败,不 30s 干等) │
                   └────────────┬────────────┘
                                │
                   ┌────────────▼────────────┐
                   │  cf_solver 联邦          │
                   │  加权最少在途调度+failover│
                   │  (单槽 ≈5s/token)        │
                   └─────────────────────────┘
```

### 5.3.3 多提供商路由(`api/providers/registry.py` + `api/adaptive_router.py`)

```
                   GET /v1/generate?model=nanobanana/nano-banana-pro
                                │
                                ▼
                   ┌─────────────────────────────┐
                   │ registry.provider_for(model)│
                   │  - spec = _models[model]    │
                   │  - provider = providers[spec]│
                   └────────────┬────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
         healthy            degraded             down
         直接返回           查能力匹配健康备用   静态回退
         (不做跨商路由)     多候选 → select_best  (仅此场景跨商)
                            MAB-EWMA 打分
              │                 │                 │
              └─────────────────┼─────────────────┘
                                ▼
                   ┌─────────────────────────────┐
                   │ adaptive_router              │
                   │  - record_inflight          │
                   │  - record_direct/fallback   │
                   │  - EWMA 打分(成功率/延迟)  │
                   └────────────┬────────────────┘
                                │
                                ▼
                   ┌─────────────────────────────┐
                   │ provider.generate(调上游)   │
                   │  - borrow account(号池)     │
                   │  - get proxy(代理池)        │
                   │  - solve turnstile(token池) │
                   │  - POST 上游 + 轮询结果     │
                   └─────────────────────────────┘
```

### 5.3.4 号池状态机(`api/account_pool.py`)

```
    ┌──────────────┐  register   ┌──────────────┐  success  ┌──────────┐
    │ unregistered │ ─────────► │ registering  │ ────────► │  active  │
    └──────────────┘            └──────┬───────┘           └────┬─────┘
                                       │ fail                   │ borrow
                                       ▼                        ▼
                                  ┌──────────┐            ┌──────────┐
                                  │ (退避重试)│            │ working  │
                                  └──────────┘            └────┬─────┘
                                                               │ release
                                  ┌──────────────────────────┘
                                  │
                                  │ 额度耗尽                  ▼
                                  │ ─────────► ┌──────────┐
                                  │            │ cooling  │
                                  │            └────┬─────┘
                                  │                 │ 满 IF_ACCOUNT_COOLING_PERIOD(20h)
                                  │                 ▼ 自动唤醒签到
                                  │            ┌──────────┐
                                  │            │  active  │ (循环)
                                  │            └──────────┘
                                  │ 封号
                                  ▼
                             ┌──────────┐
                             │   dead   │ (终态,不恢复)
                             └──────────┘
```

## 5.4 数据流

### 5.4.1 同步生成数据流

```
1. 客户端 POST /v1/generate {prompt, model, aspect_ratio}
2. RequestContextMiddleware 填充 client_ip/user_agent/trace_id
3. _guard: auth.guard_generate_request(鉴权) + check_generate_request(限流)
4. _validate_ratio + _validate_model(能力匹配)
5. engine.submit(入优先级队列,INSERT tasks 表 status=pending)
6. 立即返回 task_id(202)
7. 客户端短轮询:engine.wait_result(task_id, SYNC_TIMEOUT=300)
8. worker 从队列取任务:
   a. acquire token(token_pool,池空阻塞 ≤ TOKEN_WAIT_TIMEOUT=30)
   b. provider_for(model) → registry 路由(healthy 直连 / degraded 降级)
   c. provider.borrow_account(号池借号,若 account_required)
   d. provider.get_proxy(代理池取代理,若需代理)
   e. turnstile_client.solve_turnstile(若需 token,经 solver_guard 调度)
   f. httpx POST 上游 + 轮询 GET /api/tasks/{taskId} 至 success
   g. 下载图片(若 download=true)→ base64_store 落盘 + LRU 缓存
   h. INSERT tasks 表 status=completed + image_url
   i. publish SSE event(result)
9. wait_result 收到终态,返回 TaskInfo(200)
10. 若 300s 仍在排队,返回 202 + Location 头
```

### 5.4.2 SSE 事件流数据流

```
1. 客户端 GET /v1/tasks/{task_id}/events
2. task_events_generator:
   a. 解析 Last-Event-ID 头
   b. 回放该任务 id 之后的事件(hub.get_task_events)
   c. 进入实时推送循环:
      - publish_task_event(status/progress/result/error)
      - 15s 心跳(: ping)
      - result/error 终态后自动断开
3. 客户端断线重连:
   - 带 Last-Event-ID: 只回放 id 之后的事件(补偿)
   - 不带: 回放全部
4. sse_stats 统计:推送总量/分桶/补偿率/订阅数/取消率
```

## 5.5 部署架构

```
┌─────────────────────────────────────────────────────────┐
│  腾讯云东京 43.165.173.36(2C2G + 4G swap)              │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  /home/ubuntu/imagefree-api                      │    │
│  │  ├── docker-compose.yml                          │    │
│  │  ├── data/  (SQLite + 备份,卷持久化)             │    │
│  │  │   ├── imagefree.db                             │    │
│  │  │   ├── account_pool.db                          │    │
│  │  │   ├── email_registry.db                       │    │
│  │  │   ├── routing.db                               │    │
│  │  │   ├── imgs/  (base64 文件,TTL 24h)           │    │
│  │  │   ├── logs/  (磁盘日志,保留 14 天)           │    │
│  │  │   └── backups/  (crontab 每日 03:00 热备)     │    │
│  │  ├── frontend/dist/  (React+TS 管理面板,只读挂载)│    │
│  │  ├── landing/dist/  (Vue3 落地页,只读挂载)       │    │
│  │  └── cfsolver/config.json                         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────┐  Caddy 反代  ┌──────────────────┐     │
│  │ DNS: DNSPod  │ ──────────► │ /etc/caddy/       │     │
│  │ imagefree    │             │ Caddyfile         │     │
│  │ → 43.165... │             │ imagefree...:8100 │     │
│  └──────────────┘             └──────────────────┘     │
│                                                          │
│  crontab: 0 3 * * * python scripts/backup_db.py         │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼ 公网
              https://imagefree.tingfengai.art
```

## 5.6 生命周期(`api/lifespan.py`)

启动与关闭分阶段有序进行,防卡死与数据丢失:

### 启动顺序

1. `init_telemetry()`(OTel 追踪)
2. 注入日志处理器(log_buffer + ws_log_handler + 磁盘日志)
3. `engine.start()`(worker 池 + token 预取协程)
4. `gallery_cache.start_reaper()` + `restore_from_db()`
5. `sync_blocklist_cache()`(IP 封禁表预热)
6. `warmup_cache()`(缓存预热)+ `run_background_tasks()`(8 个后台任务)
7. `db.start_batch_timer()` + `start_checkpoint_timer()`
8. `providers_bootstrap()`(注册提供商)
9. `proxy_pool.load_file()` + `free_proxy_fetcher.start()` + `proxy_tracer.start()`
10. `account_pool.start()`(号池自动注册,若 `IF_ACCOUNT_AUTO`)
11. `providers_startup()`(各 provider 启动钩子)
12. `provider_probe.start()`(上游真实探针,180s 间隔)

### 关闭顺序(分阶段超时)

1. ① 后台任务停止(5s)
2. ② DB 写缓冲刷新(3s)
3. ③ Worker 停止(10s)
4. ④ Provider 停止(8s)
5. ⑤ 代理/号池停止(5s)
6. ⑥ 缓存持久化(3s)
7. ⑥.5 SSE 发布任务排空(5s,防终态事件丢失)
8. ⑦ HTTP 连接池关闭(3s)
9. ⑧ OTel 关闭(2s)
10. ⑨ DB 连接池关闭(3s)
