# 08 · 安全与合规

> 基于 `api/auth.py`、`api/request_guard.py`、`api/solver_guard.py`、`api/main.py`(安全头中间件)、`api/config/security.py`。

## 8.1 鉴权体系

### 8.1.1 业务 Key(防滥用)

- **配置**:`IF_API_KEYS=key1,key2`(逗号分隔,空=开放模式)
- **传递方式**(按优先级):
  1. `Authorization: Bearer <key>`
  2. `X-API-Key: <key>`
  3. `?api_key=<key>`
- **强制端点**:写操作(生图 `/v1/generate*`、图生图 `/v1/edit`、聊天 `/v1/chat/*`、`/v1/messages`)
- **只读端点**:公开(`/v1/stats`、`/v1/providers`、`/v1/models`、`/v1/meta`、`/v1/healthz`)
- **实现**:`api/auth.py:guard_generate_request`、`guard_chat_request`
- **热更新**:`_keys()` 每次现读,环境热更新友好

### 8.1.2 管理 Key(运维操作)

- **配置**:`IF_ADMIN_KEYS=admin_key1`(空则继承业务 Key 池)
- **默认拒绝**:未配管理 Key 时管理操作默认拒绝
- **开放模式**:仅 `IF_ADMIN_KEY_OPEN=1` 且未配任何 Key 时放行(本地运维/内网)
- **保护端点**:
  - DLQ retry/clear(`/v1/dead-letter-queue/*`)
  - 审计搜索(`/v1/audit`)
  - 日志拉取(`/v1/logs`、`WS /v1/logs/ws`)
  - SSE 统计(`/v1/sse/stats`)
  - 画廊签发(`/v1/gallery/sign`)
- **实现**:`api/auth.py:check_admin_key`

### 8.1.3 Key 脱敏

- **`public_keymask()`**:返回脱敏前缀(如 `sk-abc...`),不暴露完整 Key
- **公开端点**:`/v1/meta`、`/v1/chat/auth/status` 匿名只返回 `key_mask`
- **站长自助取**:`/v1/chat/auth/status` 携带管理 Key 时返回完整 Key(供站长面板「一键复制」)
- **安全**:捕获 AppError(401/403 = 鉴权未通过),full_key 保持空 → 匿名不泄完整 key;非 AppError 真实内部错误不放行到 500

## 8.2 限流体系

### 8.2.1 L1 秒级令牌桶

- **配置**:`IF_RATE_TOKEN_CAPACITY`(默认取 `IF_REQUESTS_PER_MINUTE`,`<=0` 关闭 L1)
- **回填**:`IF_RATE_TOKEN_REFILL_PER_SEC`(默认 0=纯突发桶),走墙上时钟
- **用途**:突发并发上限,平滑短时尖峰

### 8.2.2 L2 滑窗(每 IP 每分钟)

- **配置**:`IF_REQUESTS_PER_MINUTE`(默认 10,0=关闭)
- **实现**:`api/request_guard.py`,deque 时间窗口 60s
- **用途**:每 IP 每分钟生成提交次数

### 8.2.3 L3 每日限额

- **用途**:每日总量上限

### 8.2.4 L4 自动封禁

- **配置**:
  - `IF_AUTO_BLOCK_ENABLED=True`
  - `IF_AUTO_BLOCK_THRESHOLD=3`(连续超限次数)
  - `IF_AUTO_BLOCK_WINDOW_SECONDS=300`(窗口)
  - `IF_AUTO_BLOCK_TTL_SECONDS=3600`(封禁 TTL)
- **行为**:窗口内连续超限达阈值 → 自动入黑名单 TTL 秒
- **持久化**:`data/imagefree.db`,启动即加载到内存高速缓存(`sync_blocklist_cache`)

### 8.2.5 白名单与受信代理

- **白名单**:`IF_IP_WHITELIST`(逗号分隔 IP,绕过封禁与限速,运维/监控探针)
- **受信代理**:`IF_TRUSTED_PROXIES`(默认 `127.0.0.1,::1`)
  - 仅 socket 对端命中受信代理时才解析 `X-Forwarded-For`(取最右非代理段)
  - 否则一律以 socket 对端为准(防 XFF 伪造绕过封禁/限流)

### 8.2.6 聊天独立限流

- **配置**:`IF_CHAT_RATE_LIMIT=60`(每 IP 每分钟)
- **实现**:`api/auth.py:check_chat_rate_limit`,`_chat_buckets` deque

## 8.3 安全响应头

### 8.3.1 注入开关

- **总开关**:`IF_SECURITY_HEADERS_ENABLED=True`(默认开启,关闭=最小回滚不注入任何头)
- **CSP 开关**:`IF_CSP_ENABLED=False`(默认关闭,避免误杀面板 inline script / 画廊 CDN 图片)

### 8.3.2 注入头

| 头 | 值 | 说明 |
|----|----|------|
| X-Content-Type-Options | nosniff | 防 MIME 嗅探 |
| X-Frame-Options | DENY | 禁止他页 iframe 嵌入(不影响自身面板渲染) |
| Referrer-Policy | strict-origin-when-cross-origin | 跨源只发 origin |
| Strict-Transport-Security | max-age=31536000; includeSubDomains | 仅 HTTPS 请求 |
| Content-Security-Policy | (宽松,`IF_CSP_ENABLED=True` 时) | default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' |

### 8.3.3 实现特点

- **纯 ASGI 中间件**:`SecurityHeadersMiddleware`(`api/main.py`)
- **按需注入**:只在 `http.response.start` 时追加,避免 head/错误响应膨胀
- **不覆盖已设头**:`existing` 检查,避免与 FastAPI 自带头冲突
- **HSTS 仅 HTTPS**:`scope["scheme"] == "https"` 判断

## 8.4 请求体与输入校验

### 8.4.1 请求体上限

- **配置**:`IF_MAX_REQUEST_BODY=8388608`(8MB)
- **实现**:`api/main.py` 注入 `RequestBodyLimitMiddleware`(兼容 starlette 新旧命名)
- **用途**:防恶意大 base64 正文在 4MB/张校验前耗尽内存

### 8.4.2 图片大小

- **限制**:`MAX_IMAGE_BYTES=4194304`(4MB/张)
- **校验**:`api/dispatch_edit.py` 图生图输入解析

### 8.4.3 prompt 长度

- **限制**:`MAX_PROMPT_LEN=2000`
- **校验**:`GenerateRequest.prompt = Field(min_length=1, max_length=2000)`

### 8.4.4 aspect_ratio 格式

- **校验**:`^\d+:\d+$` 正则(`_validate_ratio`)
- **支持**:1:1、3:4、4:3、9:16、16:9

### 8.4.5 model 校验

- **存在性**:`registry.model(model)` 未找到 → `VAL.001`(422)
- **能力匹配**:`_validate_model` 按 `kind`(txt2img/img2img/txt2vid/img2vid)校验能力
- **归一化**:无 `/` 的 model id 自动映射为 `imagefree/<id>`

### 8.4.6 SSRF 防护

- **实现**:`api/dispatch_edit.py:_parse_input_image`
- **行为**:图生图输入 http URL 解析,私有/保留 IP 拒绝
- **data URI**:支持 `data:image/*;base64,...`,解码后校验大小

### 8.4.7 task_id 校验

- **校验**:必须完整 UUID4(`GET /v1/tasks/{task_id}/logs`)
- **用途**:防任意子串误伤其他任务日志
- **实现**:`uuid.UUID(task_id)` 解析失败 → `VAL.004`(422)

## 8.5 日志脱敏

### 8.5.1 query 泄露防护

- **问题**:`uvicorn.access` 原生日志会输出完整 URL 含 query,`?api_key=xxx` 传入时完整 Key 泄露进 `log_buffer`
- **措施**:
  - `logging.getLogger("uvicorn.access").propagate = False`(禁用冒泡)
  - `logging.getLogger("httpx").propagate = False`(防出站日志泄露)
- **替代**:context.py 中间件自定义访问日志,只记 path 不含 query

### 8.5.2 代理凭据脱敏

- **实现**:`api/worker/engine.py:_safe_proxy_label`
- **行为**:proxy URL 含 `user:pass` 凭据,healthz/metrics 只暴露 `host:port`;解析失败回退 sha256 截断(不泄完整 URL)

### 8.5.3 邮箱脱敏

- **端点**:`GET /v1/account-pool`
- **行为**:邮箱 `abc***@domain` 格式(`parts[0][:3] + "***@" + parts[1]`)

### 8.5.4 Key 脱敏

- **端点**:`/v1/meta`、`/v1/chat/auth/status`
- **行为**:匿名只返回 `key_mask` 前缀;管理 Key 通过时返回完整 Key(站长自助)

## 8.6 画廊签名 URL

### 8.6.1 签名机制

- **配置**:`IF_GALLERY_SIGNING_SECRET`(HMAC-SHA256 密钥)、`IF_GALLERY_SIGNING_TTL=600`(过期秒)
- **签发**:`GET /v1/gallery/sign`(管理 Key),返回 `?limit=N&password=<exp>:<sig>` 完整 URL
- **校验**:`_gallery_verify_sig`
  - 解析 `<exp>:<sig>`,`exp` 过期即拒
  - `hmac.compare_digest` 常数时间比较 sig(防时序攻击)
  - 仅校验 exp(防无限期重放);limit 不入签(范围 1-100 非敏感,允许改 limit 重用 token)

### 8.6.2 鉴权优先级

1. **签名 URL 优先**:配 `IF_GALLERY_SIGNING_SECRET` 且 password 含签名 token → 校验 sig
2. **静态密码回退**:未配签名密钥但配 `IF_GALLERY_PASSWORD` → `hmac.compare_digest` 比较
3. **皆空开放**:两者皆空时画廊开放(向后兼容)

### 8.6.3 防降级攻击

- **行为**:有签名密钥但 sig 校验失败 → **不再回退静态密码**(防降级攻击)
- **响应**:`AUTH.001`(403)「画廊链接已过期或签名无效」
- **不绑 IP**:仅校验 exp(防 CGNAT/代理下 IP 漂移误杀)

## 8.7 CORS

- **配置**:`IF_CORS_ORIGINS`(逗号分隔,默认 `*` 全放行向后兼容)
- **实现**:`api/main.py` `CORSMiddleware`,`allow_methods=["*"]`、`allow_headers=["*"]`
- **安全权衡**:公益开放服务默认全放行;需收紧时配具体域名

## 8.8 付费 API 红线(硬性)

### 8.8.1 预算默认为 0

- **规则**:真实付费 API 调用预算默认为 **0**(图像/视频/AI 生成/支付/短信等),即使存在真实 Key 也不发起真实付费请求
- **仅用户明确批准并给预算后才可真实调用**,批准后仍先本地验证 + 最小调用次数

### 8.8.2 Mock 验证

- **覆盖场景**:success / timeout / rate_limit / malformed_response / network_interruption / provider_error / retry_exhausted / cancellation
- **验证项**:参数拼装、响应解析、轮询、回调、超时、重试、限流、幂等、取消

### 8.8.3 上游调用边界

- **逆向免费额度**:本项目上游调用均为逆向免费额度(imagefree.net/nanobanana-pro/aifreeforever/fal.ai/tryingopen 的免费积分),不发起真实付费
- **Mock 开关**:`IF_MOCK_UPSTREAM=0`(生产留空)、`IF_MOCK_REGISTER=0`(生产留空,防测试期 mock-session cookie 泄漏到线上当真实账号)

## 8.9 安全响应协议

发现安全问题时的处理流程:

1. **立即停止**当前操作
2. 使用 **security-reviewer** 代理分析
3. 在继续之前修复 CRITICAL 问题
4. 轮换任何可能已暴露的密钥
5. 审查整个代码库中的类似问题

## 8.10 提交前强制检查

- [ ] 无硬编码密钥(API keys、密码、tokens)
- [ ] 所有用户输入已验证
- [ ] SQL 注入防护(参数化查询,aiosqlite 自动参数化)
- [ ] XSS 防护(JSON API 响应无 inline HTML,CSP 可选)
- [ ] CSRF 防护(无 cookie 会话依赖,API Key 鉴权,无 CSRF 风险)
- [ ] 认证/授权验证(API Key + 管理 Key 分层)
- [ ] 所有端点启用速率限制(L1-L4 四层)
- [ ] 错误消息不泄露敏感数据(脱敏 + 分层错误码)

## 8.11 已知限制与风险

### 8.11.1 公益开放模式风险

- **默认无鉴权**:`IF_API_KEYS` 为空时写操作开放,防滥用靠有界队列 429 限流
- **缓解**:被刷严重时可降 `IF_MAX_QUEUE` 或加 `IF_API_KEYS` + IP 限流

### 8.11.2 上游凭据存储

- **风险**:号池需存储上游 cookie/密码用于调用
- **缓解**:
  - 仅用于调用上游,不对外暴露(`/v1/account-pool` 邮箱脱敏,凭据不返回)
  - 生产 `IF_MOCK_REGISTER=0` 过滤 mock 残留账号
  - DB 文件权限控制(容器内 `/app/data`)

### 8.11.3 代理凭据

- **风险**:住宅代理 URL 含 `user:pass` 凭据
- **缓解**:`proxy_pool.snapshot` 只暴露 host:port;`_safe_proxy_label` 脱敏;日志不记录完整 URL

### 8.11.4 上游风控对抗

- **风险**:批量注册/同 IP 调用被上游 429/封禁
- **缓解**:代理池轮换 + 号池状态机 + 退避重试 + ActionSniffer 动态嗅探(站点改版自愈)
- **边界**:本项目不提供绕过法律保护的风控对抗,仅工程化使用免费额度
