# 02 · 功能需求

> 所有需求条目可由 `api/routes/` 与 `api/` 源码验证。编号格式 `FR-<域>-<序号>`。

## 2.1 图像/视频生成(FR-GEN)

### FR-GEN-01 文生图(txt2img)

- **端点**:`POST /v1/generate`(同步等待)、`POST /v1/generate/async`(异步提交)
- **请求**:`GenerateRequest`(`api/models.py`),含 `prompt`(1-2000 字)、`aspect_ratio`(N:N 格式)、`model`(`<提供商>/<模型>`)、`resolution`(1K/2K/4K)、`download`(是否返回 base64)、`priority`(0=admin/1=paid/2=normal)、`idempotency_key`
- **响应**:`TaskInfo`,含 `id`、`status`、`image_url`、`image_base64`、`timings`、`client_ip`、`client_location`、`user_agent`
- **同步语义**:短轮询等待 `IF_SYNC_TIMEOUT`(默认 300s),完成返回 200;仍在排队返回 202 + `Location` 头
- **异步语义**:立即返回 `task_id`,客户端轮询 `GET /v1/tasks/{id}` 或订阅 `GET /v1/tasks/{id}/events`(SSE)
- **实现**:`api/routes/generate.py` → `api/dispatch.py:_dispatch_generate` → worker 池消费

### FR-GEN-02 图生图(img2img)

- **端点**:`POST /v1/edit`(异步提交)、`GET /v1/edit/tasks/{job_id}`(查询)
- **请求**:`EditRequest`,含 `image`(单张 data URI 或 http URL)、`images`(最多 3 张 data URI 数组)、`prompt`(编辑指令)、`model`、`download`
- **能力**:仅声明 `img2img` 能力的模型可用(`api/providers/base.py:CAP_IMG2IMG`)
- **跨进程互斥**:`IF_EDIT_MUTEX_ENABLED`(默认 True),防同账号并发冲突;可选租约 `IF_EDIT_LEASE_ENABLED`
- **代理池**:`IF_EDIT_PROXY_FILE` + `IF_EDIT_PROXY_PARALLEL`,每任务独立出口 IP 绕上游硬并发=1
- **实现**:`api/routes/generate.py:edit_image_route` → `api/dispatch_edit.py:edit_image`

### FR-GEN-03 文生视频/图生视频(txt2vid/img2vid)

- **请求**:在 `GenerateRequest` 中传 `duration`(4/8/12/15 秒)触发 txt2vid;传 `images`(data URI 数组)触发 img2vid
- **模型**:需声明 `txt2vid` 或 `img2vid` 能力(如 fal.ai minimax-H3)
- **分辨率**:视频用 `480p`/`720p`,非 `1K/2K/4K`
- **校验**:`api/dispatch.py:_validate_model` 按 `kind` 校验能力

### FR-GEN-04 模型风格预设

- **预设**:`default/anime/realistic/watercolor/ink/cyberpunk`(`api/config/__init__.py:MODEL_PRESETS`)
- **行为**:`apply_model()` 在 prompt 前注入风格前缀(如 `anime style, ...`)
- **兼容**:旧版无 `/` 的 model id 自动映射为 `imagefree/<id>`

### FR-GEN-05 模型列表

- **端点**:`GET /v1/models`(兼容 `GET /v1/model` 单数别名)
- **契约**:同时返回本服务分组格式(`items`/`count`)与 OpenAI 标准格式(`data`/`object`)
- **用途**:Cherry Studio、OpenAI SDK、Cursor、NextChat 等客户端按 `data` 数组解析模型列表
- **实现**:`api/routes/admin.py:models`

## 2.2 文本对话(FR-CHAT)

### FR-CHAT-01 OpenAI 兼容聊天

- **端点**:`POST /v1/chat/completions`
- **请求**:`ChatCompletionsRequest`(`api/routes/chat.py`),含 `model`、`messages`(role: user/assistant/system/tool)、`stream`、`temperature`、`top_p`、`max_tokens`、`reasoning_effort`(minimal/low/medium/high/max 等,未知值静默落回 balanced)、`tools`、`tool_choice`、`stream_options`
- **流式**:`stream=true` 时返回 SSE,chunk 格式 `{id, object:"chat.completion.chunk", choices:[{delta, finish_reason}]}`
- **usage**:`stream_options.include_usage=true` 时末尾发 usage chunk;provider 未返回 usage 则按 `len(json)//4` 估算
- **思考链**:`reasoning_effort` 映射 `quick/balanced/deep`,delta 含 `reasoning_content` 字段
- **工具调用**:`tool_calls` 在 delta 中按 index 累积

### FR-CHAT-02 Anthropic 兼容消息

- **端点**:`POST /v1/messages`
- **请求**:`MessagesRequest`,含 `model`、`messages`(role: user/assistant)、`system`(顶层字段)、`max_tokens`、`stream`、`tools`
- **流式事件**:`message_start` → `content_block_start` → `content_block_delta`(text_delta/thinking_delta)→ `content_block_stop` → `message_delta` → `message_stop`
- **思考链**:reasoning 映射为 `thinking` content block
- **工具调用**:映射为 `tool_use` content block,`stop_reason="tool_use"`

### FR-CHAT-03 聊天模型目录

- **端点**:`GET /v1/chat/models`
- **响应**:`items` 含 `id`、`display_name`、`upstream_model`、`provider`、`context_window`、`capabilities`、`price_per_mtok`、`message_limit`、`cheaper_fallback_id`
- **动态目录**:tryingopen 等提供商模型目录可动态刷新(`IF_TRYINGOPEN_SYNC_MINUTES=30`),未命中缓存时按前缀委托查询

### FR-CHAT-04 鉴权状态探测

- **端点**:`GET /v1/chat/auth/status`
- **响应**:`enabled`、`admin_enabled`、`key_mask`(脱敏前缀)、`key`(仅管理 Key 通过时返回完整)、`header`、`alt_headers`
- **安全**:匿名只返回脱敏 key_mask,不暴露完整 Key

### FR-CHAT-05 用量统计

- **端点**:`GET /v1/chat/usage?period=1h|24h|7d|30d`、`GET /v1/chat/remaining`
- **记录**:`chat_usage_tracker` 记录 provider/model/tokens/cost_usd/duration/success,落 `chat_usage` 表
- **成本**:`cost_usd` 字段,免费渠道为 0;`IF_USD_PER_CREDIT` 估算图片成本

## 2.3 任务管理(FR-TASK)

### FR-TASK-01 任务列表

- **端点**:`GET /v1/tasks?limit=&offset=&status=&model=&sort=`
- **参数**:`limit`(1-200)、`offset`、`status`(pending/processing/completed/error)、`model`、`sort`(created_at/duration_sec)
- **响应**:`items` + `total` + `limit` + `offset`,字段经 `task_to_public` 脱敏

### FR-TASK-02 任务详情

- **端点**:`GET /v1/tasks/{task_id}`
- **响应**:`TaskInfo`,含 timings/client_ip/client_location/user_agent 等取证字段
- **404**:任务不存在返回 `SYS.003`

### FR-TASK-03 全链路日志串联

- **端点**:`GET /v1/tasks/{task_id}/logs?lines=`
- **聚合**:log_buffer(按 trace_id 精确匹配,无则 task_id 子串)+ slow_log 画像 + SSE 已发布事件 + DB 任务终态
- **校验**:task_id 必须为完整 UUID4,防任意子串误伤其他任务

### FR-TASK-04 SSE 事件流

- **端点**:`GET /v1/tasks/{task_id}/events`(每任务)、`GET /v1/events/tasks`(全局广播,向后兼容)
- **事件**:status/progress/result/error + 15s 心跳 + Last-Event-ID 断线补偿
- **回放**:连接后先回放该任务已产生事件(Last-Event-ID 头 → 只回放 id 之后的),result/error 终态后自动断开
- **实现**:`api/sse_events.py:task_events_generator`

### FR-TASK-05 死信队列

- **端点**:`GET /v1/dead-letter-queue`、`POST /v1/dead-letter-queue/{task_id}/retry`、`DELETE /v1/dead-letter-queue`
- **配置**:`IF_DLQ_ENABLED`(默认 True)、`IF_DLQ_MAX_RETRIES`(3)、`IF_DLQ_RETENTION_DAYS`(7)、`IF_DLQ_REQUEUE`(默认 False)
- **鉴权**:retry/clear 需管理 Key(`IF_ADMIN_KEYS`)

### FR-TASK-06 幂等

- **配置**:`IF_IDEMPOTENCY_ENABLED`(默认 False)、`IF_IDEMPOTENCY_TTL`(900s)
- **行为**:同一 `idempotency_key` 重复提交返回相同 task_id,冲突返回 `SYS.005`(409)

## 2.4 提供商与路由(FR-PROV)

### FR-PROV-01 提供商看板

- **端点**:`GET /v1/providers`
- **响应**:每个 provider 的能力/模型数/账号需求/每请求代理需求/实时余额 + 上游真实探针状态(`provider_probe`)
- **余额**:`provider.credits()` 返回上游实时积分

### FR-PROV-02 自适应路由(MAB-EWMA)

- **实现**:`api/adaptive_router.py` + `api/providers/registry.py:provider_for`
- **策略**:healthy 直接返回请求指定提供商(不做跨商自动路由);degraded 查能力匹配健康备用,多候选用 `select_best` MAB 打分;down 静态回退
- **持久化**:`IF_ROUTING_DB` 独立 SQLite,重启保留路由历史 + warm 冷启动 EWMA
- **记录**:`GET /v1/routing/records?limit=&from_ts=` 返回路由决策历史(内存环形 + 持久化)

### FR-PROV-03 降级与熔断

- **降级**:连续失败达 `IF_PROVIDER_DEGRADE_THRESHOLD`(3)标记 degraded;`IF_PROVIDER_RECOVER_INTERVAL`(300s)后探测恢复
- **熔断**:solver_guard 节点级 + 集群级熔断(429 冷却 60s + 连续失败 5 次熔断 30s + half-open 探测)
- **号池耗尽**:`_exhausted_accounts` 标记已耗尽账号,避免重复借用

### FR-PROV-04 Action 嗅探

- **实现**:`api/providers/action_sniffer.py`
- **场景**:nanobanana 等使用 Next.js Server Action 的上游,站点改版后 Action ID 变化,嗅探失败回退静态兜底值
- **价值**:站点改版无需改代码即可自愈

## 2.5 资源池(FR-POOL)

### FR-POOL-01 号池管理

- **实现**:`api/account_pool.py`,状态机 `AccountStatus`(unregistered/registering/active/working/cooling/dead)
- **操作**:borrow(借号)/release(归还)/mark_dead(封号)/mark_cooling(冷却)
- **自动补号**:`IF_ACCOUNT_AUTO=1` + `IF_NANOBANANA_ACCOUNT_TARGET`(默认 10000)持续注册补号
- **每日签到**:nanobanana 7 天循环 [4,4,8,4,4,4,10],美区时区重置(北京 15:00),积分 2 天过期
- **看板**:`GET /v1/account-pool` 返回分页账号明细(邮箱脱敏)+ 补号速率画像 + 成本聚合
- **持久化**:`data/account_pool.db`(aiosqlite + WAL + busy_timeout)

### FR-POOL-02 邮箱池

- **实现**:`api/email_pool.py` + `api/email_sources/`(9 源适配器)
- **源**:linshi-email、mail.tm、mail.gw、guerrillamail、22.do、temp-mail、temp-mail.io、temp.tf、custom-imap
- **策略**:按优先级、可用性评分、风控状态自适应轮换;429 自动退避切换备用源
- **AI 提取**:`IF_MAIL_AI_EXTRACT=1` 时正则未命中验证码/链接则降级 LLM 提取
- **看板**:`GET /v1/email-sources` 返回各源官网/优先级/可用性/成败计数/最近错误

### FR-POOL-03 代理池

- **实现**:`api/proxy_pool.py`,双源:住宅代理文件 + 免费代理抓取器(`api/free_proxy_fetcher.py`)
- **分配**:优先选从未使用过的 IP(use_count==0);全部用过一轮后选冷却最早结束的
- **冷却**:`IF_PROXY_USE_COOLDOWN_MAP`(默认 `0,30,90,300,900`)递增冷却;24h 后 daily_uses 清零
- **免费源**:`IF_FREE_PROXY=1` 启用,4 源(proxyscrape/geonode/proxy-list.download/proxifly),`IF_FREE_PROXY_REFRESH_MIN=30`
- **trace 探测**:`IF_PROXY_TRACE_ENABLED` 通过 `cdn-cgi/trace` 探测真实出口 IP/colo
- **看板**:`GET /v1/proxy-pool` 只暴露 host:port(不泄住宅代理凭据)、`GET /v1/proxy-pool/subscribe` 一键订阅

### FR-POOL-04 token 池

- **实现**:`api/worker/token_pool.py:TokenPoolManager`
- **双水位**:`IF_TOKEN_TARGET_WATERMARK`(direct 池目标水位,默认 1,生产建议 5)+ `IF_TOKEN_URGENT_WATERMARK`(紧急水位,默认 0)
- **批量填充**:urgent 时 `IF_TOKEN_BATCH_FILL_SIZE` 并发 gather 求解
- **事件驱动**:池空 acquire 置位 need_event 立即唤醒预取,替代 sleep 轮询
- **空闲回收**:per-proxy 池空闲超 `IF_TOKEN_TTL`(90s)自动回收
- **熔断门控**:solver_guard OPEN 期间暂停新求解(快速失败)

## 2.6 可观测性(FR-OBS)

### FR-OBS-01 Prometheus 指标

- **端点**:`GET /metrics`(PlainTextResponse,`text/plain; version=0.0.4`)
- **实现**:`api/metrics_ext.py:imagefree_metrics`,聚合 engine.snapshot + db.stats + solver_guard.snapshot
- **指标**:出图总量、错误码分桶(`imagefree_errors_by_code`)、SSE 事件、solver 成功率、队列水位

### FR-OBS-02 OpenTelemetry 链路

- **配置**:`IF_OTEL_ENABLED`、`IF_OTEL_SERVICE_NAME`(imagefree-api)、`IF_OTEL_EXPORTER_OTLP_ENDPOINT`(localhost:4317)
- **采样**:tail-based,`IF_OTEL_SAMPLE_RATE=0.1`(正常 10%)、`IF_OTEL_ERROR_SAMPLE_RATE=1.0`(错误 100%)
- **traceId 透传**:contextvars 请求上下文中间件(`api/context.py`),worker 后台协程脱离入口 context 仍可串联

### FR-OBS-03 实时日志

- **WebSocket**:`WS /v1/logs/ws`(需管理 Key),`api/log_ws.py` 推送
- **HTTP 快照**:`GET /v1/logs?lines=`(需管理 Key),`api/log_buffer.py` 内存缓冲
- **安全**:`uvicorn.access`/`httpx` 原生日志禁用冒泡,防 `?api_key=xxx` query 泄露;context.py 中间件只记 path 不含 query
- **磁盘落盘**:`IF_LOG_DIR`(默认 data/logs),`IF_LOG_RETENTION_DAYS`(14)滚动清理

### FR-OBS-04 审计日志

- **端点**:`GET /v1/audit?action=&actor=&trace_id=&q=`(需管理 Key)
- **实现**:`api/audit.py:audit_log`,记录写操作(dlq.retry/dlq.clear 等)+ actor + trace_id + detail
- **串联**:trace_id 与 OTel/SSE/日志串联,一个任务 ID 看全链路

### FR-OBS-05 慢日志画像

- **端点**:`GET /v1/slow`(JSON)、`GET /v1/slow/view`(静态看板)
- **配置**:`IF_SLOW_LOG_ENABLED`、`IF_SLOW_REQUEST_MS`(5000)、`IF_SLOW_LOG_SIZE`(500)
- **画像**:queue_ms/wait_token_ms/solve_ms/upstream_ms/retry_ms/total_ms + slowest_stage + trace_id

### FR-OBS-06 统计与画廊

- **统计**:`GET /v1/stats` 返回总量 + 实时并发/排队 + 按日(14)/月(12)拆分 + 平均出图耗时 + base64 GC + solver 画像
- **画廊**:`GET /v1/gallery?limit=&password=`,签名 URL 优先(`IF_GALLERY_SIGNING_SECRET` HMAC + TTL),回退静态密码(`IF_GALLERY_PASSWORD`),皆空开放
- **签发**:`GET /v1/gallery/sign`(管理 Key)返回带 exp+sig 的有限期 URL

### FR-OBS-07 错误聚合

- **后端**:`GET /v1/errors` 最近失败明细、`GET /v1/errors/aggregates` P0-P1 错误码聚合计数
- **前端**:`POST /v1/errors/frontend` 前端错误遥测上报(`window.onerror`/`unhandledrejection`,code 前缀 `FE.`)、`GET /v1/errors/frontend` 聚合查看

### FR-OBS-08 健康检查

- **liveness**:`GET /v1/livez`(进程活即 ok,Docker healthcheck 用)
- **readiness**:`GET /v1/healthz`(聚合 cf_solver + solver_guard + DB + 队列 + 提供商健康 + SLO budget)
- **readyz**:`GET /v1/readyz`(任一关键依赖不 ok → 503,供上游路由探活)
- **体检**:`GET /v1/diagnostics`(DB/队列/worker/token池/代理池/磁盘/慢日志,零副作用只读)

### FR-OBS-09 成本可视化

- **端点**:`GET /v1/cost`
- **口径**:token 成本取 `chat_usage.cost_usd`;图片成本 = 号池累计积分 × `IF_USD_PER_CREDIT`(默认 0 不估算)
- **预算**:`IF_COST_BUDGET_USD`(0 不启用告警),返回 `over_budget`/`burn_rate_warning`/月度趋势/by_provider/by_model

### FR-OBS-10 SSE 事件统计

- **端点**:`GET /v1/sse/stats`(需管理 Key)
- **指标**:事件推送总量、按类型分桶、补偿率(Last-Event-ID 重连 replay)、订阅数、取消率、任务数、每任务平均推送量

## 2.7 管理面与落地页(FR-UI)

### FR-UI-01 管理面板

- **挂载**:`/admin`(React+TS SPA,`frontend/dist`,SPA 深链回退 + `/admin`→`/admin/` 重定向)
- **页面**:Dashboard、Tasks、Providers、Accounts、ChatPlayground、Logs、Costs、Security、Slow、DLQ、Ecosystem、Health、Gallery
- **实现**:`frontend/src/pages/`,API 调用 `frontend/src/api/`

### FR-UI-02 公开落地页

- **挂载**:`/`(Vue3 SPA,`landing/dist`)
- **区块**:SectionUsage(用量)、SectionProviders(提供商)、SectionCode(代码示例)、SectionStatus(状态)、SectionFaq、SectionChangelog、SectionCta、Privacy
- **实现**:`landing/src/components/`,i18n(`useI18n.js`)、轮询(`usePolling.js`)

### FR-UI-03 服务条款与捐赠

- **条款**:`GET /v1/terms`(总览)、`GET /v1/terms/{service|privacy|content|disclaimer}`(细分)、`GET /v1/terms/index`(结构化列表)
- **捐赠**:`GET /v1/honor`(页面)、`GET /v1/honor/data`(数据:消息+赞赏码+微信联系方式+GitHub)
- **静态资源**:`/static/zanshang.jpg`、`/static/logo.png`、`/static/logo-md.png`

## 2.8 生态聚合(FR-ECO)

### FR-ECO-01 TensorFeed AI 生态

- **端点**:`GET /v1/ai-ecosystem`
- **上游**:`https://tensorfeed.ai`(免费无 key)四个端点:`/api/models`、`/api/status/summary`、`/api/today`、`/api/health`
- **归一化**:并发拉取 + 逐段容错,失败段 `available=False`,有旧缓存 stale 回退
- **缓存**:惰性 LRU(`maxsize=8`,`IF_TENSORFEED_CACHE_TTL=900`)+ 防击穿锁
- **实现**:`api/routes/ecosystem.py`

## 2.9 系统与元信息(FR-SYS)

### FR-SYS-01 服务器规格自适应

- **实现**:`api/system_spec.py`,探测 CPU/内存,返回 `ADAPTIVE_WORKERS`/`ADAPTIVE_UPSTREAM_INFLIGHT`/`ADAPTIVE_TOKEN_POOL_SIZE`/`ADAPTIVE_MAX_QUEUE`
- **档位**:2C2G→worker=4/upstream=12/token=3/queue=1000;4C4G→8/32/8/2000;4C8G→16/64/16/5000;8C16G→16(封顶)/64/8/5000
- **端点**:`GET /v1/system`(ETag 协商缓存)

### FR-SYS-02 站点元信息

- **端点**:`GET /v1/meta`(ETag 协商缓存)
- **响应**:`sitekey`、`aspect_ratios`、`supported_resolutions`、`gallery_requires_password`、`auth_enabled`、`api_key_mask`(脱敏)
- **安全**:不返回完整 API Key,仅脱敏前缀
