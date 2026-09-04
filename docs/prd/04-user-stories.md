# 04 · 用户故事

> 典型用户旅程与使用场景。角色画像基于项目公益开放定位。

## 4.1 用户角色

| 角色 | 画像 | 核心诉求 |
|------|------|---------|
| **接入开发者** | 用 OpenAI SDK / Cherry Studio / Cursor / NextChat 的开发者 | 一行 API 生成图片,不处理 Turnstile/号池 |
| **公益使用者** | 想免费用 AI 生成图/视频的普通用户 | 公网落地页直接用,无需注册 |
| **站长/运维** | 部署维护本服务的个人(听风) | 部署简单、监控完善、可扩展 |
| **贡献者** | 逆向新上游或改进本项目的开发者 | 架构清晰、可扩展、有测试 |

## 4.2 用户故事

### US-01:接入开发者用 OpenAI SDK 生成图片

**作为** 一个用 OpenAI Python SDK 的开发者,
**我想** 调用 `POST /v1/generate` 生成一张 16:9 的动漫风格图片,
**以便** 在我的应用里集成 AI 出图能力,无需自己处理 Cloudflare Turnstile。

**验收标准**:
- [ ] `GET /v1/models` 返回 OpenAI 标准 `data` 数组,客户端能解析模型列表
- [ ] `POST /v1/generate` 接受 `{prompt, aspect_ratio:"16:9", model:"imagefree/anime"}`,返回 `TaskInfo` 含 `image_url`
- [ ] 调用方无需传 Turnstile token,由后端 token 池自动供给
- [ ] 同步等待模式(`POST /v1/generate`)在 `IF_SYNC_TIMEOUT`(300s)内完成返回 200;仍在排队返回 202 + `Location` 头
- [ ] 错误返回分层错误码(如 `VAL.003` 比例格式错误),含 zh 消息

### US-02:接入开发者用 Anthropic SDK 对话

**作为** 一个用 Anthropic SDK 的开发者,
**我想** 调用 `POST /v1/messages` 进行流式对话,含思考链,
**以便** 在我的应用里集成带 reasoning 的 AI 对话。

**验收标准**:
- [ ] `POST /v1/messages` 接受 `{model, messages, stream:true}`,返回 SSE 事件流
- [ ] 事件序列:`message_start` → `content_block_start` → `content_block_delta`(text_delta)→ `content_block_stop` → `message_delta` → `message_stop`
- [ ] 思考链映射为 `thinking` content block,`thinking_delta` 事件
- [ ] 工具调用映射为 `tool_use` content block,`stop_reason="tool_use"`
- [ ] `reasoning_effort` 任意取值都被接受,未知值静默落回 balanced(不 422)

### US-03:接入开发者异步提交 + SSE 订阅

**作为** 一个需要生成多张图的开发者,
**我想** 异步提交任务后用 SSE 订阅进度,
**以便** 不阻塞主流程,实时看到生成状态。

**验收标准**:
- [ ] `POST /v1/generate/async` 立即返回 `task_id`(202)
- [ ] `GET /v1/tasks/{task_id}/events` 返回 SSE,15s 心跳保活
- [ ] 连接后先回放该任务已产生事件(`Last-Event-ID` 头 → 只回放 id 之后的)
- [ ] 事件类型:status/progress/result/error;result/error 终态后自动断开
- [ ] 客户端断线重连后用 `Last-Event-ID` 补偿,不丢事件

### US-04:接入开发者图生图编辑照片

**作为** 一个想把照片转成水彩画的用户,
**我想** 提交一张图 + 编辑指令,获得编辑后的图,
**以便** 做 AI 照片编辑。

**验收标准**:
- [ ] `POST /v1/edit` 接受 `{image: "data:image/png;base64,...", prompt:"make it a watercolor painting", model:"imagefree/default"}`
- [ ] 图片大小 ≤ 4MB(`MAX_IMAGE_BYTES`),超过返回 `VAL.004`(413)
- [ ] 输入 http URL 时做 SSRF 防护,私有/保留 IP 拒绝
- [ ] 跨进程互斥(`IF_EDIT_MUTEX_ENABLED`)防同账号并发冲突
- [ ] `GET /v1/edit/tasks/{job_id}` 查询结果

### US-05:公益使用者访问落地页

**作为** 一个想免费用 AI 生图的普通用户,
**我想** 访问公网落地页看到用量、提供商、代码示例,
**以便** 了解服务并快速上手。

**验收标准**:
- [ ] 访问 `https://imagefree.tingfengai.art/` 加载 Vue3 落地页
- [ ] SectionUsage 展示实时出图量/并发/排队(每 15s 轮询)
- [ ] SectionProviders 展示各上游提供商能力/余额
- [ ] SectionCode 展示 curl/Python/JS 调用示例
- [ ] SectionStatus 展示服务健康状态(健康/降级)
- [ ] SectionFaq 展示常见问题,SectionCta 引导使用
- [ ] 落地页响应式,移动端可用

### US-06:公益使用者浏览画廊

**作为** 一个想看看生成效果的用户,
**我想** 访问画廊看到最近生成的作品,
**以便** 决定是否使用。

**验收标准**:
- [ ] `GET /v1/gallery?limit=50` 返回最近完成的 N 条作品(image_url/prompt/aspect_ratio/duration_sec/finished_at)
- [ ] 配置 `IF_GALLERY_SIGNING_SECRET` 时,需签名 URL(`<exp>:<sig>` 作 password);过期或签名无效返回 403
- [ ] 未配签名密钥但配 `IF_GALLERY_PASSWORD` 时走静态密码(向后兼容)
- [ ] 两者皆空时画廊开放(向后兼容)
- [ ] 站长用 `GET /v1/gallery/sign`(管理 Key)签发有限期 URL 分享

### US-07:站长部署服务

**作为** 站长,
**我想** 用 docker compose 一键部署 cfsolver + api,
**以便** 快速上线,无需手动配置环境。

**验收标准**:
- [ ] `cd deploy && docker compose up -d` 启动 cfsolver(8001 内部)+ api(8100 公网)
- [ ] api 等待 cfsolver 健康后才启动(`depends_on: condition: service_healthy`)
- [ ] 容器 healthcheck 用 livez,停 solver 时 readiness 降级但容器不被误杀重启
- [ ] `curl http://127.0.0.1:8100/v1/healthz` 返回 `{"status":"ok","cf_solver":"up",...}`
- [ ] `curl http://127.0.0.1:8100/v1/models` 返回多提供商模型列表
- [ ] 服务器规格自适应并发(2C2G→worker=4 等),无需手动调

### US-08:站长监控运维

**作为** 站长,
**我想** 通过管理面板和 metrics 监控服务状态,
**以便** 及时发现故障并处理。

**验收标准**:
- [ ] 访问 `/admin` 加载 React+TS 管理面板
- [ ] Dashboard 展示实时并发/排队/solver 成功率/错误码分桶
- [ ] `/metrics` 暴露 Prometheus 指标,可接 Grafana Cloud 免费层
- [ ] `GET /v1/tasks/{id}/logs` 一个任务 ID 看全链路(log_buffer + slow_log + SSE events + DB 终态)
- [ ] `GET /v1/diagnostics` 一键体检(DB/队列/worker/token池/代理池/磁盘/慢日志)
- [ ] WebSocket `/v1/logs/ws` 实时日志推送(需管理 Key)
- [ ] 异常时 `IF_ALERT_WEBHOOK_URL` 外发企业微信/钉钉/Slack

### US-09:站长扩展求解器容量

**作为** 站长,
**我想** 在生成吞吐不足时加 cf_solver 节点,
**以便** 线性提升出图速率。

**验收标准**:
- [ ] 复制 `cfsolver` service(cfsolver2/cfsolver3...)
- [ ] api 的 `IF_CF_SOLVER_URLS` 改为逗号分隔多 URL
- [ ] solver_guard 自动加权最少在途调度 + failover
- [ ] `IF_SOLVER_NODE_WEIGHTS` 可调权重(JSON 或 `url1=1,url2=2` 格式)
- [ ] `IF_SOLVER_IDLE_TIMEOUT_SECONDS` 让空闲节点降级备选
- [ ] `GET /v1/stats` 的 `solver` 字段透出多节点明细

### US-10:站长启用号池自动注册

**作为** 站长,
**我想** 启用号池自动注册 + 每日签到,
**以便** 持续供给 nanobanana 等积分制提供商额度。

**验收标准**:
- [ ] 配 `IF_ACCOUNT_AUTO=1` + `IF_NANOBANANA_ACCOUNT_TARGET=500`
- [ ] 号池自动注册(linshi/mail.tm 等 9 源邮箱),7x24h 每成功 1 个休息 90s
- [ ] nanobanana 每日签到(7 天循环 [4,4,8,4,4,4,10],美区时区北京 15:00 重置)
- [ ] `GET /v1/account-pool` 返回分页账号(邮箱脱敏)+ 补号速率 + 成本聚合
- [ ] 账号状态机:unregistered → registering → active → working → cooling → dead
- [ ] cooling 满 `IF_ACCOUNT_COOLING_PERIOD`(20h)自动唤醒签到/恢复

### US-11:站长启用免费代理池

**作为** 站长,
**我想** 启用免费代理池,
**以便** aifreeforever 等 每 IP 每日限额场景绕开限制。

**验收标准**:
- [ ] 配 `IF_FREE_PROXY=1` + `IF_FREE_PROXY_REFRESH_MIN=30`
- [ ] 4 源抓取(proxyscrape/geonode/proxy-list.download/proxifly)
- [ ] 每 IP 24h 冷却重置,429 递增退避(0/30/90/300/900s)
- [ ] `GET /v1/proxy-pool` 返回代理状态(只暴露 host:port,不泄凭据)
- [ ] `IF_PROXY_TRACE_ENABLED=1` 时通过 `cdn-cgi/trace` 探测真实出口 IP/colo

### US-12:贡献者逆向新上游

**作为** 贡献者,
**我想** 添加一个新的上游提供商,
**以便** 扩展网关能力。

**验收标准**:
- [ ] 实现 `api/providers/base.py:Provider` 抽象基类(generate/credits/health 等)
- [ ] 声明 `prefix`、`models`(`ModelSpec`,id = `<prefix>/<真实模型名>`)
- [ ] 声明能力 `capabilities`(txt2img/img2img/txt2vid/img2vid)
- [ ] 在 `api/providers/registry.py:bootstrap` 注册
- [ ] 自动享受 MAB-EWMA 路由、降级熔断、号池/代理池接入(若 `account_required=True`)
- [ ] 自动出现在 `GET /v1/models`、`GET /v1/providers` 看板
- [ ] 参考 `docs/PROVIDER_INTEGRATION_GUIDE.md`

### US-13:接入开发者查看文档与调试

**作为** 接入开发者,
**我想** 访问 Swagger 文档和错误码说明,
**以便** 快速调试集成问题。

**验收标准**:
- [ ] 访问 `/docs` 加载 Swagger UI(FastAPI 自动生成)
- [ ] 错误响应含分层错误码(`CATEGORY.NNN`)+ zh/en 消息 + details
- [ ] `GET /v1/meta` 返回站点配置(sitekey/aspect_ratios/auth_enabled/api_key_mask 脱敏)
- [ ] `GET /v1/chat/auth/status` 探测是否需要 Key(匿名只返回脱敏 key_mask)
- [ ] 422 错误含具体字段校验信息(如 prompt 长度、aspect_ratio 格式)

### US-14:站长启用鉴权防滥用

**作为** 站长,
**我想** 在被刷严重时启用 API Key 鉴权,
**以便** 防止滥用。

**验收标准**:
- [ ] 配 `IF_API_KEYS=key1,key2`(逗号分隔),写操作(生图/图生图/聊天)强制 Key
- [ ] 三种传递方式:Authorization: Bearer / X-API-Key / ?api_key=
- [ ] 配 `IF_ADMIN_KEYS=admin_key1`(独立管理 Key),管理操作(封禁/DLQ/审计/日志)默认拒绝
- [ ] 未配管理 Key 时继承业务 Key;两者皆空且 `IF_ADMIN_KEY_OPEN=1` 时开放(本地运维)
- [ ] `IF_REQUESTS_PER_MINUTE` 调整限速(默认 10,被刷可降到更低)
- [ ] `IF_AUTO_BLOCK_ENABLED=1` 频繁超限自动入黑名单(阈值 3,窗口 300s,TTL 3600s)

### US-15:站长查看成本

**作为** 站长,
**我想** 查看月度成本与预算余量,
**以便** 控制公益运行成本。

**验收标准**:
- [ ] `GET /v1/cost` 返回月度/今日成本 + 预算余量 + 燃烧率 + 月度趋势 + by_provider + by_model
- [ ] token 成本取 `chat_usage.cost_usd` 聚合
- [ ] 图片成本 = 号池累计积分 × `IF_USD_PER_CREDIT`(默认 0 不估算)
- [ ] `IF_COST_BUDGET_USD` 配预算,返回 `over_budget`/`burn_rate_warning`(80% 预警)
- [ ] 管理面板 Costs 页可视化趋势图
