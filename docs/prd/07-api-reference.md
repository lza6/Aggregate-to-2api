# 07 · API 与接口

> 全部端点契约,基于 `api/routes/` 源码。错误响应统一格式 `{"error": {"code": "CATEGORY.NNN", "message": "...", "details": {}}}`。

## 7.1 鉴权

### 7.1.1 业务 Key(写操作)

- **配置**:`IF_API_KEYS=key1,key2`(逗号分隔,空=开放模式)
- **传递方式**(按优先级):
  1. `Authorization: Bearer <key>`
  2. `X-API-Key: <key>`
  3. `?api_key=<key>`
- **强制端点**:生图 `/v1/generate*`、图生图 `/v1/edit`、聊天 `/v1/chat/*`、`/v1/messages`

### 7.1.2 管理 Key(运维操作)

- **配置**:`IF_ADMIN_KEYS=admin_key1`(空则继承业务 Key)
- **开放模式**:仅 `IF_ADMIN_KEY_OPEN=1` 且未配任何 Key 时放行(本地运维)
- **保护端点**:封禁/DLQ retry/clear、审计、日志、SSE 统计、画廊签发

### 7.1.3 鉴权探测

```
GET /v1/chat/auth/status
```
- **响应**:`{enabled, admin_enabled, key_mask, key, header, alt_headers}`
- **安全**:匿名只返回脱敏 `key_mask`;管理 Key 通过时返回完整 `key`(站长自助取)

## 7.2 图像/视频生成

### 7.2.1 文生图(同步等待)

```
POST /v1/generate
```

**请求体**(`GenerateRequest`):
```json
{
  "prompt": "a cat in space",           // 必填,1-2000 字
  "aspect_ratio": "16:9",               // 可选,默认 "1:1",格式 N:N
  "model": "imagefree/anime",            // 可选,默认 imagefree/default
  "resolution": "1K",                   // 可选,1K/2K/4K 或视频 480p/720p
  "duration": 8,                        // 可选,视频时长 4/8/12/15 秒
  "images": [],                         // 可选,图生视频输入图 data URI 数组
  "download": false,                    // 可选,是否返回 base64
  "priority": 2,                        // 可选,0=admin/1=paid/2=normal
  "idempotency_key": "abc123",          // 可选,幂等 key(IF_IDEMPOTENCY_ENABLED=1 时生效)
  "client_ip": null,                    // 服务端自动回填,客户端无需传
  "user_agent": null                    // 服务端自动回填
}
```

**响应**:
- **200**:`TaskInfo`(`{id, status:"completed", image_url, image_base64, timings, ...}`)
- **202**:仍在排队,`TaskInfo`(status=queued)+ `Location` 头
- **422**:`VAL.001` 模型不存在 / `VAL.002` 提示词不符 / `VAL.003` 比例格式错
- **429**:`SYS.002` 队列满 / `RATE.001` 限流
- **401**:`AUTH.001` 未授权(配了 Key 时)
- **408**:`SYS.004` 超时

### 7.2.2 文生图(异步提交)

```
POST /v1/generate/async
```
- **请求**:同 7.2.1
- **响应**:立即返回 `TaskInfo`(含 task_id,status=pending),客户端轮询 `GET /v1/tasks/{id}` 或订阅 `GET /v1/tasks/{id}/events`

### 7.2.3 图生图

```
POST /v1/edit
```

**请求体**(`EditRequest`):
```json
{
  "image": "data:image/png;base64,...", // 单张(向后兼容),data URI 或 http URL
  "images": ["data:image/png;base64,..."], // 数组(最多 3 张)
  "prompt": "make it a watercolor painting", // 必填,编辑指令
  "download": false,
  "model": "imagefree/default"
}
```
- **图片限制**:≤4MB/张(`MAX_IMAGE_BYTES`)
- **SSRF 防护**:http URL 解析,私有/保留 IP 拒绝
- **互斥**:`IF_EDIT_MUTEX_ENABLED` 跨进程互斥防同账号冲突
- **响应**:`TaskInfo`

### 7.2.4 图生图查询

```
GET /v1/edit/tasks/{job_id}
```
- **响应**:`TaskInfo`;404 `SYS.003`

## 7.3 任务管理

### 7.3.1 任务列表

```
GET /v1/tasks?limit=50&offset=0&status=completed&model=imagefree/default&sort=created_at
```
- **参数**:`limit`(1-200)、`offset`、`status`(pending/processing/completed/error)、`model`、`sort`(created_at/duration_sec)
- **响应**:`{items: [TaskInfo], total, limit, offset}`

### 7.3.2 任务详情

```
GET /v1/tasks/{task_id}
```
- **响应**:`TaskInfo`(含 timings/client_ip/client_location/user_agent)

### 7.3.3 全链路日志

```
GET /v1/tasks/{task_id}/logs?lines=200
```
- **校验**:task_id 必须完整 UUID4
- **响应**:
```json
{
  "task_id": "...",
  "trace_id": "...",
  "task": {DB 任务终态},
  "logs": [log_buffer 条目,按 trace_id 精确匹配],
  "slow": [慢日志画像],
  "events": [SSE 已发布事件],
  "count": {"logs": N, "slow": N, "events": N}
}
```

### 7.3.4 SSE 事件流

```
GET /v1/tasks/{task_id}/events
GET /v1/events/tasks   (向后兼容全局广播)
```
- **事件类型**:status / progress / result / error
- **心跳**:15s `: ping`
- **Last-Event-ID**:断线重连补偿,只回放 id 之后的事件
- **终态**:result/error 后自动断开
- **响应头**:`Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`

### 7.3.5 死信队列

```
GET /v1/dead-letter-queue?limit=20
POST /v1/dead-letter-queue/{task_id}/retry   (需管理 Key)
DELETE /v1/dead-letter-queue                  (需管理 Key)
```
- **配置**:`IF_DLQ_ENABLED`(默认 True)、`IF_DLQ_MAX_RETRIES=3`、`IF_DLQ_RETENTION_DAYS=7`、`IF_DLQ_REQUEUE`(默认 False,开启后真重入队)

### 7.3.6 幂等

- **配置**:`IF_IDEMPOTENCY_ENABLED`(默认 False)、`IF_IDEMPOTENCY_TTL=900`
- **行为**:同一 `idempotency_key` 重复提交返回相同 task_id;冲突 `SYS.005`(409)

## 7.4 文本对话

### 7.4.1 OpenAI 兼容聊天

```
POST /v1/chat/completions
```

**请求体**(`ChatCompletionsRequest`):
```json
{
  "model": "tryingopen/glm-4.6",
  "messages": [{"role": "user", "content": "hello"}],
  "stream": false,
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 1000,
  "reasoning_effort": "medium",  // minimal/low/medium/high/max,未知值落回 balanced
  "tools": [...],
  "tool_choice": "auto",
  "stream_options": {"include_usage": true}
}
```

**非流式响应**:
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "...",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "...", "reasoning_content": "...", "tool_calls": [...]}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N, "reasoning_tokens": N}
}
```

**流式响应**(SSE):
```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"...","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"...","choices":[{"index":0,"delta":{"content":"hello"},"finish_reason":null}]}

data: {"...","choices":[{"index":0,"delta":{"reasoning_content":"..."},"finish_reason":null}]}

data: {"...","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_...","type":"function","function":{"name":"...","arguments":"..."}}]},"finish_reason":null}]}

data: {"...","choices":[],"usage":{...}}   (stream_options.include_usage=true 时)

data: [DONE]
```

### 7.4.2 Anthropic 兼容消息

```
POST /v1/messages
```

**请求体**(`MessagesRequest`):
```json
{
  "model": "...",
  "messages": [{"role": "user", "content": "hello"}],
  "system": "You are helpful",  // 顶层字段
  "max_tokens": 1000,
  "stream": true,
  "tools": [...]
}
```

**非流式响应**:
```json
{
  "id": "msg_...",
  "type": "message",
  "role": "assistant",
  "model": "...",
  "content": [{"type": "text", "text": "..."}, {"type": "thinking", "thinking": "..."}, {"type": "tool_use", "id": "toolu_...", "name": "...", "input": {...}}],
  "stop_reason": "end_turn" | "tool_use",
  "usage": {"input_tokens": N, "output_tokens": N}
}
```

**流式响应**(SSE 事件):
```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","type":"message","role":"assistant","model":"...","content":[],"usage":{"input_tokens":N,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":N}}

event: message_stop
data: {"type":"message_stop"}
```

### 7.4.3 聊天模型目录

```
GET /v1/chat/models
```
- **响应**:`{items: [{id, display_name, upstream_model, provider, context_window, capabilities, price_per_mtok, message_limit, cheaper_fallback_id}], count, auth_required}`

### 7.4.4 聊天用量

```
GET /v1/chat/usage?period=24h   # 1h/24h/7d/30d
GET /v1/chat/remaining
```

## 7.5 提供商与管理

### 7.5.1 模型列表

```
GET /v1/models
GET /v1/model   (单数别名)
```
- **响应**:同时返回 OpenAI 标准 `data` 数组 + 本服务 `items` 分组
```json
{
  "object": "list",
  "data": [{"id": "...", "object": "model", "created": 0, "owned_by": "..."}],
  "items": {"imagefree": [...], "nanobanana": [...]},
  "count": N
}
```

### 7.5.2 提供商看板

```
GET /v1/providers
```
- **响应**:每个 provider 的能力/模型数/账号需求/代理需求/实时余额 + 上游探针状态

### 7.5.3 号池看板

```
GET /v1/account-pool?page=1&page_size=20&search=
```
- **响应**:分页账号明细(邮箱脱敏 `abc***@domain`)+ 补号速率 + 成本聚合 + 邮箱池统计 + 实时注册阶段画像

### 7.5.4 统计

```
GET /v1/stats
```
- **响应**:总量 + 实时并发/排队 + 按日(14)/月(12)拆分 + 平均出图耗时 + base64 GC + solver 多节点画像

### 7.5.5 画廊

```
GET /v1/gallery?limit=50&password=<exp:sig>
GET /v1/gallery/sign?limit=50   (管理 Key,签发有限期 URL)
```
- **鉴权**:签名 URL 优先(HMAC + TTL),回退静态密码,皆空开放
- **响应**:`{items: [{image_url, image_mime, prompt, aspect_ratio, duration_sec, finished_at}], count}`

### 7.5.6 代理池

```
GET /v1/proxy-pool?page=1&page_size=20
GET /v1/proxy-pool/subscribe?format=base64   (订阅,include_in_schema=False)
```
- **响应**:代理状态(只暴露 host:port,不泄凭据)

### 7.5.7 邮箱源

```
GET /v1/email-sources
```
- **响应**:各源 `{name, base_url, priority, available, success_count, failure_count, last_error}`

### 7.5.8 路由记录

```
GET /v1/routing/records?limit=50&from_ts=   (include_in_schema=False)
```
- **响应**:`{records: [路由决策], nodes: [节点 EWMA 快照]}`

### 7.5.9 死信队列 / 错误 / 慢请求 / 审计

```
GET /v1/dead-letter-queue?limit=20
GET /v1/errors?limit=20
GET /v1/errors/aggregates   (P0-P1 错误码聚合计数)
POST /v1/errors/frontend    (前端错误遥测上报,code 前缀 FE.)
GET /v1/errors/frontend
GET /v1/slow?limit=50       (慢请求画像)
GET /v1/slow/view           (静态看板)
GET /v1/audit?limit=50&action=&actor=&trace_id=&q=   (需管理 Key)
```

### 7.5.10 成本

```
GET /v1/cost
```
- **响应**:`{month_to_date_usd, today_usd, budget_usd, budget_remaining_pct, over_budget, burn_rate_warning, monthly, by_provider, by_model, image_cost_usd_mtd}`

### 7.5.11 诊断

```
GET /v1/diagnostics
```
- **响应**:DB/队列/worker/token池/solver/慢日志/磁盘/uptime 一键体检

### 7.5.12 日志(需管理 Key)

```
GET /v1/logs?lines=50         (快照)
WS /v1/logs/ws                (实时推送,?api_key= 或子协议头鉴权,失败 close 4401)
```

### 7.5.13 SSE 统计(需管理 Key)

```
GET /v1/sse/stats   (include_in_schema=False)
```

## 7.6 健康检查与元信息

```
GET /v1/healthz    (readiness:聚合 cf_solver + solver + DB + 队列 + 提供商 + SLO)
GET /v1/livez      (liveness:进程活,Docker healthcheck 用)
GET /v1/readyz     (聚合依赖探活,任一不 ok → 503)
GET /v1/system     (服务器规格,ETag 协商缓存)
GET /v1/meta       (站点配置,ETag,api_key_mask 脱敏)
GET /metrics       (Prometheus,include_in_schema=False)
```

## 7.7 服务条款与捐赠

```
GET /v1/terms              (服务条款总览页)
GET /v1/terms/index        (结构化子页面列表)
GET /v1/terms/{service|privacy|content|disclaimer}
GET /v1/honor              (捐赠页)
GET /v1/honor/data        (捐赠数据:消息+赞赏码+微信+GitHub)
GET /static/zanshang.jpg   (赞赏码图片,Cache-Control 1天)
GET /static/logo.png      (Logo 小)
GET /static/logo-md.png   (Logo 中)
```

## 7.8 生态聚合

```
GET /v1/ai-ecosystem
```
- **上游**:`https://tensorfeed.ai` 四端点并发拉取 + 逐段容错归一化
- **缓存**:LRU `maxsize=8` + `IF_TENSORFEED_CACHE_TTL=900` + 防击穿锁 + stale 回退
- **响应**:`{models, status, today, health, cache}`

## 7.9 前端

- **管理面板**:`/admin`(React+TS SPA,SPA 深链回退 + `/admin`→`/admin/` 重定向)
- **落地页**:`/`(Vue3 SPA,仅未命中 API 路由的路径落此)
- **Swagger**:`/docs`(FastAPI 自动生成)

## 7.10 错误码与 HTTP 状态

| HTTP | 错误码 | 场景 |
|------|--------|------|
| 400 | VAL.004 | 通用参数错误 |
| 401 | AUTH.001 | 未授权 |
| 403 | AUTH.003 | 无权/IP 封禁 |
| 404 | SYS.003 | 资源不存在 |
| 408 | SYS.004 | 生成超时 |
| 409 | SYS.005 | 幂等 Key 冲突 |
| 413 | VAL.004 | 图片过大 |
| 422 | VAL.001-003 | 模型/提示词/比例校验 |
| 429 | SYS.002 / RATE.001 / PROV.002 | 队列满/限流/额度耗尽 |
| 500 | SYS.001 | 内部错误 |
| 503 | PROV.001 / PROV.003 | 提供商不可用/求解器熔断 |
| 502 | SYS.006 | 上游第三方不可用 |
