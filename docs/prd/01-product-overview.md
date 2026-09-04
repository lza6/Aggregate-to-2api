# 01 · 产品概述

## 1.1 简介

**听风AI(imagefree-2ai)** 是一个公益运行的**多提供商 AI 图像/视频/对话生成开放网关**。项目通过逆向工程与系统工程化手段,将多个免费或积分制的上游 AI 生成服务聚合为统一的 OpenAI/Anthropic 兼容接口,对外提供免费、开放、高并发的生成能力。

项目代码入口 `api/main.py` 组装 FastAPI 应用(`version="7.2.0"`),核心特征:

- **多提供商网关**:imagefree.net、aifreeforever、nanobanana-pro、fal.ai(minimax-H3 视频)、tryingopen(匿名对话)等上游经统一抽象(`api/providers/base.py`)后对外暴露一致接口
- **Cloudflare Turnstile 自动求解**:通过 `cf_solver` 联邦(camoufox 无头浏览器)自动求解人机验证,调用方无感
- **逆向号池**:自动注册账号、每日签到续额、状态机管理生命周期(unregistered → registering → active → working → cooling → dead)
- **高并发引擎**:有界优先级队列 + worker 池 + 多 key token 池预取,入口仅做校验+入库+入队,慢操作由后台 worker 消费
- **邮箱池**:9 源临时邮箱(linshi/mail.tm/mail.gw/guerrilla/22.do/temp-mail/temp-mail.io/temp.tf/custom-imap)自动注册
- **代理池**:住宅代理 + 免费代理双源,每 IP 24h 冷却重置,429 递增退避
- **可观测性**:Prometheus 指标 + OpenTelemetry 链路 + SSE 实时日志 + 审计日志 + 慢日志画像
- **双前端**:React+TS 管理面板(`/admin`)与 Vue3 公开落地页(`/`)

## 1.2 问题陈述

### 用户侧痛点

1. **免费 AI 生成服务零散且不稳定**:各上游站点(imagefree.net、nanobanana-pro 等)单独使用时,受限于单账号积分额度、每日签到、Cloudflare 人机验证、单 IP 限额,普通用户难以稳定调用
2. **接入门槛高**:各上游接口非标准、需自行处理 Turnstile 求解、cookie 会话、RSC Server Action 编码、Next-Action ID 嗅探,普通开发者难以集成
3. **无统一标准接口**:上游既有 REST、又有 Next.js Server Action、又有 OpenAI 兼容,客户端(Cherry Studio、Cursor、NextChat、OpenAI SDK)需要标准 `/v1/chat/completions`、`/v1/models` 契约才能接入

### 供给侧痛点

4. **额度碎片化**:nanobanana 每日签到续额(7 天循环 [4,4,8,4,4,4,10],积分 2 天过期);aifreeforever 每 IP 每日限额;imagefree 需 Turnstile token。单账号单 IP 均无法持续供给
5. **风控对抗**:批量注册被 Cloudflare/邮箱源 429 限流;同 IP 批量注册必被风控;Turnstile 求解是串行瓶颈(单槽 ≈5s/token)
6. **运维成本**:个人公益项目预算有限(2C2G/512MB 容器档),无法上 Postgres/Kafka/Redis 集群,需在单机 SQLite 形态下扛住公益流量

### 项目解决的核问题

> **把零散、不稳定、难集成的免费上游,工程化为一个稳定、标准、高并发的开放网关,让调用方一行 API 即可生成,无需感知 Turnstile/号池/代理/签到。**

## 1.3 目标

### 核心目标

1. **统一接口**:对外暴露 OpenAI/Anthropic 兼容的 `/v1/models`、`/v1/generate`、`/v1/chat/completions`、`/v1/messages`,客户端零改造接入
2. **无感求解**:调用方无需处理 Cloudflare Turnstile,由 `cf_solver` 联邦自动求解并预取 token 池
3. **持续供给**:号池每日签到续额 + 自动补号 + 多 IP 代理轮换,绕开单账号/单 IP 额度限制
4. **高并发**:入口扛 50 RPS,请求路径仅做校验+入库+入队(毫秒级),生成由后台 worker 池消费
5. **公益开放**:默认无鉴权(可配 `IF_API_KEYS` 启用)、CORS 全开、提供免费落地页与管理面板

### 可量化目标(基于实测)

| 指标 | 目标 | 实测依据 |
|------|------|---------|
| 入口吞吐 | 50 RPS 并发瞬时 | `deploy/README.deploy.md`:50 并发 ≈270 RPS,平均 4ms/请求 |
| 生成吞吐 | 受 cf_solver 限制 | 单槽 ≈5s/token → 理论 ~0.2 图/秒;加浏览器槽可线性提升 |
| 队列容量 | 2000(默认) | `IF_MAX_QUEUE=2000`,满则 429 |
| worker 并发 | 10(默认,自适应) | `IF_WORKERS=10`;2C2G→4,4C8G→16 |
| token 池 | 6(默认) | `IF_TOKEN_POOL_SIZE=6`,双水位+批量并发填充 |
| DB 写入 | <10 写/秒 | SQLite WAL + 批量写,富余 |
| 容器内存 | 512MB | `docker-compose.yml`:`mem_limit: 512m` |

### 非目标(明确不做)

- **不商业化**:公益运行,不收费、不打广告(赞赏码自愿支持)
- **不追求集群化**:单机 SQLite 形态够用,Postgres/Kafka/Redis 集群在当前量级是负优化(见 `docs/architecture-evolution.md`)
- **不提供 SLA**:无可用性保证,上游风控/域名封禁/求解器故障会导致间歇不可用
- **不存储敏感信息**:号池 cookie/密码仅用于调用上游,不对外暴露;日志脱敏

## 1.4 范围

### 包含(In Scope)

- 图像生成:文生图(txt2img)、图生图(img2img)、文生视频(txt2vid)、图生视频(img2vid)
- 文本对话:OpenAI `/v1/chat/completions` 兼容、Anthropic `/v1/messages` 兼容、流式 SSE、思考链(reasoning)、工具调用(tool_calls)
- 多提供商路由:imagefree、aifreeforever、nanobanana、fal.ai、tryingopen,含 MAB-EWMA 自适应路由与跨商降级
- 资源池:号池(注册/签到/借还/状态机)、邮箱池(9 源)、代理池(住宅+免费双源)、token 池(双水位+批量填充)
- 任务管理:同步等待、异步提交、SSE 事件流、死信队列(DLQ)、幂等
- 可观测性:Prometheus `/metrics`、OTel 链路、SSE 实时日志、WebSocket 日志、审计日志、慢日志画像、成本可视化
- 健康检查:`/v1/healthz`(readiness)、`/v1/livez`(liveness)、`/v1/readyz`、`/v1/diagnostics` 体检
- 管理面板:React+TS SPA(`/admin`),含 Dashboard/Tasks/Providers/Accounts/Chat/Logs/Costs/Security 等页面
- 落地页:Vue3 SPA(`/`),含服务条款、隐私政策、捐赠页
- 部署:Docker Compose(cfsolver + api),Caddy 反代自动 HTTPS,服务器规格自适应并发

### 不包含(Out of Scope)

- 用户账号体系:无终端用户注册/登录,调用方用 API Key(可选)或匿名访问
- 付费 API 真实调用:遵循付费 API 红线(预算默认 0),上游调用均为逆向免费额度,不发起真实付费请求
- 多租户隔离:单实例单租户,不提供数据隔离
- 移动端 App:仅 Web 落地页 + 管理面板(响应式),不提供原生 App
- 模型微调/训练:仅消费上游已有模型,不做训练
- 持久化作品存储:画廊仅缓存最近 N 条(`IF_GALLERY_LIMIT=50`),base64 文件 TTL 24h 清理
- 水平扩展(当前):单实例部署,水平扩展在触发器出现前是负优化(见架构演进路线图)

## 1.5 术语表

| 术语 | 含义 |
|------|------|
| **提供商(Provider)** | 上游 AI 生成服务,实现 `api/providers/base.py:Provider` 抽象基类 |
| **号池(Account Pool)** | 积分制提供商的账号池,含注册/签到/借还/状态机,见 `api/account_pool.py` |
| **邮箱池(Email Pool)** | 多源临时邮箱管理器,为自动注册分配邮箱,见 `api/email_pool.py` |
| **代理池(Proxy Pool)** | 住宅+免费双源代理,每 IP 24h 冷却,见 `api/proxy_pool.py` |
| **token 池(Token Pool)** | Cloudflare Turnstile token 预取池,见 `api/worker/token_pool.py` |
| **cf_solver** | Turnstile 求解服务(camoufox 无头浏览器),独立容器,见 `deploy/cf_solver/` |
| **solver_guard** | 求解质量观测 + 集群节点熔断调度,见 `api/solver_guard.py` |
| **DLQ** | 死信队列(Dead Letter Queue),失败任务最终落地,见 `api/db/` |
| **SSE** | Server-Sent Events,任务事件流与聊天流式输出 |
| **MAB-EWMA** | 多臂老虎机 + 指数加权移动平均,自适应路由打分,见 `api/adaptive_router.py` |
| **RSC** | React Server Components,Next.js Server Action 编码(nanobanana 上游使用) |
| **ActionSniffer** | 动态嗅探 Next.js Server Action ID,见 `api/providers/action_sniffer.py` |
| **livez/healthz/readyz** | 存活/就绪探针(Kubernetes 约定),liveness 只看进程,readiness 聚合依赖 |
| **IF_ 前缀** | 所有环境变量前缀(imagefree),pydantic-settings 集中管理 |
| **公益开放模式** | 未配 `IF_API_KEYS` 时写操作开放,配则强制 Key |
