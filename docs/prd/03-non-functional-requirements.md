# 03 · 非功能需求

> 所有指标基于代码实现与部署实测,可由 `deploy/README.deploy.md`、`docs/architecture-evolution.md`、`docker-compose.yml` 验证。编号 `NFR-<类>-<序号>`。

## 3.1 性能(NFR-PERF)

### NFR-PERF-01 入口吞吐

- **目标**:50 RPS 并发瞬时,平均 4ms/请求,0 限流 0 失败
- **依据**:`deploy/README.deploy.md` 压测结果 ≈270 RPS
- **实现**:请求路径仅做 校验 → INSERT(SQLite 毫秒级)→ 入队(内存)→ 返回,不在请求路径同步做慢操作(`api/worker/engine.py` 设计目标)

### NFR-PERF-02 生成吞吐

- **目标**:受 cf_solver 求解速率决定,单槽 ≈5s/token → 理论 ~0.2 图/秒
- **扩展**:给 cf_solver 加浏览器槽(改 `cf_solver/config.json` 的 `thread`/`page_count`,每槽约 +0.3GB RAM)可线性提升
- **依据**:`docs/architecture-evolution.md` 瓶颈画像

### NFR-PERF-03 并发参数自适应

- **目标**:按服务器规格自动设置 worker/upstream/token/queue,无需手动调
- **实现**:`api/config/__init__.py:_apply_adaptive_defaults` + `api/system_spec.py`
- **档位**:2C2G→worker=4;4C4G→8;4C8G→16;8C16G→16(封顶)
- **覆盖**:仅当用户未显式设 `IF_WORKERS`/`IF_UPSTREAM_MAX_INFLIGHT`/`IF_TOKEN_POOL_SIZE`/`IF_MAX_QUEUE` 时生效

### NFR-PERF-04 请求体上限

- **目标**:防恶意大 base64 正文在 4MB/张校验前耗尽内存
- **配置**:`IF_MAX_REQUEST_BODY=8388608`(8MB)
- **实现**:`api/main.py` 注入 `RequestBodyLimitMiddleware`(兼容 starlette 新旧命名)

### NFR-PERF-05 DB 写入

- **目标**:每秒 <10 写,SQLite 富余
- **实现**:WAL 模式 + 批量写(`IF_DB_BATCH_ENABLED`/`IF_DB_BATCH_WINDOW=0.5`)+ aiosqlite 连接池(`IF_DB_POOL_SIZE=5`)+ WAL checkpoint(5 分钟)
- **依据**:`docs/architecture-evolution.md` DB 维度

### NFR-PERF-06 token 池零延迟命中

- **目标**:direct 池无排队时维持目标水位,请求不阻塞在求解
- **配置**:`IF_TOKEN_TARGET_WATERMARK`(默认 1,生产建议 5)+ `IF_TOKEN_URGENT_WATERMARK`(紧急批量)
- **实现**:后台预取协程(per-key)持续补满;事件驱动补池(池空 acquire 置位 need_event 立即唤醒)

### NFR-PERF-07 上游并发隔离

- **目标**:每请求独立出口 IP 绕上游单 IP 限额
- **配置**:`IF_UPSTREAM_MAX_INFLIGHT=30`(信号量,自适应到 64)、`IF_EDIT_PROXY_MAX_INFLIGHT=2`(图生图)
- **实现**:`api/semaphore_manager.py:upstream_semaphore`

### NFR-PERF-08 ETag 协商缓存

- **目标**:低频变更只读端点省带宽
- **端点**:`/v1/system`、`/v1/meta`
- **实现**:响应体哈希作 ETag,客户端带 `If-None-Match` 且匹配 → 304 Not Modified

## 3.2 可用性(NFR-AVAIL)

### NFR-AVAIL-01 健康检查分层

- **liveness**:`/v1/livez` 只看进程活,Docker healthcheck 用,停 solver 时 readiness 降级而 liveness 不误杀容器
- **readiness**:`/v1/healthz` 聚合 cf_solver + solver_guard + DB + 队列 + 提供商 + SLO budget,任一降级返回 `degraded`
- **readyz**:`/v1/readyz` 聚合依赖探活,任一关键依赖不 ok → 503,供上游路由探活

### NFR-AVAIL-02 熔断与快速失败

- **solver_guard**:429 冷却 60s + 连续失败 5 次熔断 30s + half-open 探测恢复;熔断 OPEN 期间暂停新求解(快速失败,不再 30s 干等)
- **provider 熔断**:连续失败 3 次(`IF_PROVIDER_DEGRADE_THRESHOLD`)标记 degraded;300s(`IF_PROVIDER_RECOVER_INTERVAL`)探测恢复
- **跨商降级**:degraded 时查能力匹配健康备用,多候选用 MAB 打分选最优

### NFR-AVAIL-03 多节点容灾

- **solver 联邦**:`IF_CF_SOLVER_URLS` 逗号分隔多节点,solver_guard 加权最少在途调度 + failover;`IF_SOLVER_NODE_WEIGHTS` 调权重;`IF_SOLVER_IDLE_TIMEOUT_SECONDS` 空闲降级备选
- **扩展**:复制 cfsolver service + 加 URL 即可,无需改代码

### NFR-AVAIL-04 优雅关闭

- **实现**:`api/lifespan.py:lifespan` 分阶段有序停止:① 后台任务 → ② DB 写缓冲 → ③ Worker → ④ Provider → ⑤ 代理/号池 → ⑥ 缓存持久化 → ⑥.5 SSE 排空 → ⑦ HTTP 连接池 → ⑧ OTel → ⑨ DB 连接池
- **超时**:每阶段独立超时(2-10s),防卡死

### NFR-AVAIL-05 容器重启策略

- **restart**:`unless-stopped`(`docker-compose.yml`)
- **healthcheck**:cfsolver 等待健康后 api 才启动(`depends_on: condition: service_healthy`);api 用 livez
- **资源**:`mem_limit: 512m`(api)、`1024m`(cfsolver),`cpus: 2`

### NFR-AVAIL-06 持久化与恢复

- **DB**:SQLite + WAL,容器重启不丢(`./data` 卷持久化)
- **缓存恢复**:LRU 画廊缓存从 DB 恢复(`gallery_cache.restore_from_db()`)
- **路由历史**:`IF_ROUTING_DB` 独立 SQLite,重启保留 + warm 冷启动 EWMA
- **IP 封禁表**:启动即加载到内存高速缓存(`sync_blocklist_cache`)

## 3.3 安全(NFR-SEC)

> 详细安全措施见 [08-安全与合规](./08-security-compliance.md),此处仅列非功能指标。

### NFR-SEC-01 鉴权分层

- **业务 Key**:`IF_API_KEYS`(逗号分隔),写操作(生图/图生图/聊天)强制;空=开放模式
- **管理 Key**:`IF_ADMIN_KEYS` 独立池,空则继承业务 Key;管理操作(封禁/DLQ/审计/日志)默认拒绝,仅 `IF_ADMIN_KEY_OPEN=1` 时开放(本地运维)
- **传递**:Authorization: Bearer / X-API-Key / ?api_key=(按优先级)

### NFR-SEC-02 限流四层

- **L1 秒级令牌桶**:`IF_RATE_TOKEN_CAPACITY`(默认取 `IF_REQUESTS_PER_MINUTE`)+ `IF_RATE_TOKEN_REFILL_PER_SEC`
- **L2 滑窗**:`IF_REQUESTS_PER_MINUTE`(每 IP 每分钟,默认 10)
- **L3 每日限额**:每日总量
- **L4 自动封禁**:`IF_AUTO_BLOCK_ENABLED` + 阈值 3 + 窗口 300s + TTL 3600s

### NFR-SEC-03 安全响应头

- **开关**:`IF_SECURITY_HEADERS_ENABLED`(默认 True)
- **头**:X-Content-Type-Options: nosniff / X-Frame-Options: DENY / Referrer-Policy: strict-origin-when-cross-origin / Strict-Transport-Security(仅 HTTPS)
- **CSP**:`IF_CSP_ENABLED`(默认 False,避免误杀面板 inline script / 画廊 CDN 图片)

### NFR-SEC-04 日志脱敏

- **query 泄露防护**:`uvicorn.access`/`httpx` 原生日志禁用冒泡(防 `?api_key=xxx` 完整 Key 泄露);context.py 中间件只记 path 不含 query
- **代理凭据脱敏**:proxy_pool snapshot 只暴露 host:port,不泄住宅代理 user:pass
- **邮箱脱敏**:`/v1/account-pool` 返回 `abc***@domain` 格式
- **Key 脱敏**:`/v1/meta`、`/v1/chat/auth/status` 匿名只返回 `key_mask` 前缀

### NFR-SEC-05 请求体与输入校验

- **请求体上限**:`IF_MAX_REQUEST_BODY=8MB`(`RequestBodyLimitMiddleware`)
- **图片大小**:`MAX_IMAGE_BYTES=4MB`/张
- **prompt 长度**:`MAX_PROMPT_LEN=2000`
- **aspect_ratio**:`^\d+:\d+$` 正则校验
- **model 校验**:存在性 + 能力匹配(`_validate_model`)
- **SSRF 防护**:图生图输入 URL 解析,私有/保留 IP 拒绝(`_parse_input_image`)
- **task_id 校验**:必须完整 UUID4,防任意子串误伤

### NFR-SEC-06 XFF 伪造防护

- **受信代理**:`IF_TRUSTED_PROXIES`(默认 `127.0.0.1,::1`),仅 socket 对端命中才解析 X-Forwarded-For(取最右非代理段)
- **白名单**:`IF_IP_WHITELIST` 绕过封禁与限速(运维/监控探针)

### NFR-SEC-07 画廊签名 URL

- **实现**:`IF_GALLERY_SIGNING_SECRET` HMAC-SHA256 + `IF_GALLERY_SIGNING_TTL=600` 过期
- **防降级**:有签名密钥但 sig 校验失败 → 不再回退静态密码(防降级攻击)
- **不绑 IP**:仅校验 exp(防 CGNAT/代理漂移误杀)

## 3.4 可维护性(NFR-MAINT)

### NFR-MAINT-01 模块化拆分

- **目标**:main.py <300 行(当前 v4.2 拆分后达标)
- **结构**:routes/(按功能域)、dispatch.py/dispatch_edit.py(调度)、worker/(引擎+token池)、providers/(提供商)、config/(子配置类)、db/(数据层)、email_sources/(邮箱源)、storage/(存储适配器)
- **文件大小**:典型 200-400 行,最多 800 行(遵循编码风格)

### NFR-MAINT-02 配置集中管理

- **实现**:pydantic-settings(`api/config/__init__.py`),`IF_` 前缀环境变量,`validation_alias` 映射
- **分组**:DBSettings/HTTPSettings/SolverSettings/CacheSettings/ProviderSettings/PoolSettings/QueueSettings/ObservabilitySettings/EditSettings/SecuritySettings
- **空串容忍**:`_drop_blank_env` 丢弃空字符串环境变量(部署模板 `IF_XXX=` 留空不崩溃)
- **热更新**:`_keys()`/`_admin_keys()` 每次现读,环境热更新友好

### NFR-MAINT-03 测试体系

- **框架**:pytest + pytest-asyncio(`asyncio_mode = "auto"`,`asyncio_default_test_loop_scope = "session"`)
- **覆盖**:单元 + 集成 + E2E + 基准(pytest-benchmark)+ 混沌(fault injection)
- **标记**:`benchmark`/`chaos`/`integration`/`slow`,默认 `-m "not slow"`
- **门禁**:CI 全绿基线;预存卡死勿当回归(MEMORY 记录)
- **目录**:`tests/`(pytest 风格)+ `scripts/`(unittest 文件)

### NFR-MAINT-04 静态检查

- **ruff**:`target-version = "py311"`,`line-length = 120`(中文注释)
- **mypy**:`python_version = "3.11"`,per-module strict(`api.errors`/`api.retry_policy` 先收紧)
- **渐进 strict**:默认宽松,不强制全部注解,避免一次性大面积改造

### NFR-MAINT-05 可观测性闭环

- **一个任务 ID 看全链路**:`GET /v1/tasks/{id}/logs` 聚合 log_buffer + slow_log + SSE events + DB 终态
- **trace_id 串联**:OTel traceId 透传到 worker 后台协程,审计/日志/SSE 共用
- **错误码分层**:CATEGORY.NNN 格式(AUTH/VAL/PROV/SYS/RATE),多语言消息(zh/en)

### NFR-MAINT-06 部署可回滚

- **最小回滚**:`IF_SECURITY_HEADERS_ENABLED=False` 关安全头、`IF_CSP_ENABLED` 关 CSP,不破坏现状
- **配置开关**:所有功能可由环境变量开关(`IF_*_ENABLED`),关闭=不注入
- **DB 备份**:宿主机 crontab 每日 03:00 全量热备(`scripts/backup_db.py`),恢复见 `docs/SOP.md`

## 3.5 可扩展性(NFR-SCALE)

> 基于单机形态评估,详见 `docs/architecture-evolution.md`。公益单机产品,拒绝过度工程。

### NFR-SCALE-01 当前适用项

- **CDN**:Cloudflare 免费层套域名,landing/admin 静态资源全球边缘缓存 + DDoS + WAF
- **Rate Limiting**:L1 令牌桶 + 滑窗 + 每日限额 + 自动封禁 + 分片锁 + 管理 Key 已达标
- **Circuit Breaker**:solver_guard + adaptive_router + provider 降级已达标
- **Health Checks**:livez/healthz/readyz 双口径 + compose healthcheck + solver 心跳已达标
- **Observability**:Prometheus + OTel + WebSocket/SSE 日志 + 审计日志已达标

### NFR-SCALE-02 触发器出现前不做的项(负优化)

- **Load Balancer**:单实例部署,Nginx/HAProxy 只在 ≥2 实例时有意义
- **Database Replication**:SQLite 单文件主从(LiteFS/litestream)用于多活;当前单机+每日备份够 RPO=24h
- **Sharding**:数据量 17k 行不到百万,分表是伪需求
- **Message Queues**:已有 asyncio.PriorityQueue + 持久化队列,Kafka 最小集群 >2GB,比 api 还重
- **Redis**:当前 LRU 内存缓存够用;触发条件:跨实例共享/缓存量超内存/令牌桶限流迁集中式

### NFR-SCALE-03 演进触发器

| 信号 | 触发动作 |
|------|---------|
| 单机 CPU 持续 >80% / 带宽打满 | 先 CDN → 再考虑双实例 + litestream 共享 |
| 数据丢失零容忍 | litestream → R2(RPO 秒级) |
| 需要多地域部署 | Postgres(Supabase 免费层)替换 SQLite |
| 任务量 >1k/天 或需任务编排 | 评估轻量 MQ(Redis Streams,非 Kafka) |
| 上游求解器成为硬瓶颈 | cf_solver 多节点联邦(已有 solver_guard,只差加节点) |

## 3.6 兼容性(NFR-COMPAT)

### NFR-COMPAT-01 OpenAI/Anthropic 客户端兼容

- **`/v1/models`**:同时返回 `items`/`count`(本服务前端)与 `data`/`object`(OpenAI 标准)
- **`/v1/chat/completions`**:chunk 格式 `{id, object:"chat.completion.chunk", choices:[{delta, finish_reason}]}`,含 `reasoning_content`/`tool_calls`
- **`/v1/messages`**:Anthropic 事件流 `message_start`/`content_block_delta`/`message_delta`/`message_stop`
- **reasoning_effort**:宽容接受任意取值,未知值静默落回 balanced(防 Cherry Studio 默认发 max 被 422 拒绝)
- **验证客户端**:Cherry Studio、OpenAI SDK、Cursor、NextChat

### NFR-COMPAT-02 向后兼容

- **错误码**:`_LEGACY_CODE_MAP` 旧版字符串错误码(如 `QUEUE_FULL`)映射为分层格式(`SYS.002`)
- **状态别名**:`AccountStatus` 兼容 ok/active、exhausted/cooling、banned/dead
- **路径别名**:`GET /v1/model`(单数)兼容 `GET /v1/models`
- **SSE 端点**:`/v1/events/tasks`(向后兼容)与 `/v1/tasks/{id}/events`(新)
- **配置**:`from api.config import settings` 与 `get_settings()` 等价;模块级常量 `BASE_URL` 等保留

### NFR-COMPAT-03 starlette 版本兼容

- **RequestBodyLimitMiddleware**:兼容 starlette 1.6(`RequestBodyLimitMiddleware`)与旧版(`BodySizeLimitMiddleware`)
- **SPAStaticFiles**:兼容旧版 `get_response` 返回 Response 与新版 `raise HTTPException(404)`

## 3.7 合规(NFR-COMPLI)

### NFR-COMPLI-01 付费 API 红线

- **预算默认 0**:图像/视频/AI 生成/支付/短信等真实付费 API,即使存在真实 Key 也不发起真实付费请求
- **Mock 验证**:用 Mock/fixture/录制响应验证参数拼装/响应解析/轮询/回调/超时/重试/限流/幂等/取消
- **场景覆盖**:success/timeout/rate_limit/malformed_response/network_interruption/provider_error/retry_exhausted/cancellation

### NFR-COMPLI-02 服务条款

- **页面**:`/v1/terms/service`(服务条款)、`/v1/terms/privacy`(隐私政策)、`/v1/terms/content`(内容政策)、`/v1/terms/disclaimer`(免责声明)
- **结构化**:`/v1/terms/index` 返回子页面列表

### NFR-COMPLI-03 内容审核

- **上游**:依赖各上游(nanobanana/aifreeforever/imagefree)自身的内容审核
- **本地**:`_moderate` 等方法(部分 provider 实现)做基础过滤
- **红线**:不生成违法内容,依赖上游策略 + 本地兜底

## 3.8 国际化(NFR-I18N)

### NFR-I18N-01 错误消息多语言

- **实现**:`api/errors.py:ERROR_MESSAGES`,每个错误码含 `zh`/`en` 模板
- **插值**:`get_error_message(code, lang, **kwargs)` 动态参数插值
- **默认**:zh

### NFR-I18N-02 落地页 i18n

- **实现**:`landing/src/composables/useI18n.js`,Vue3 落地页多语言切换
- **范围**:SectionUsage/SectionProviders/SectionCode/SectionFaq/SectionCta/Privacy
