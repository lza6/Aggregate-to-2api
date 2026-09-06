# 外部拨测与告警通道配置

> 目的：用第三方（不在自家服务器/网络内）的拨测服务盯 `/v1/healthz`，避免"机器宕机 + 自家监控同时挂"的盲区。
> 推荐服务：UptimeRobot（免费档 5min 间隔够用）/ 阿里云云监控 / 腾讯云拨测 / better-uptime。
> 本文档**不创建账号、不填真实凭证**，只给配置步骤与告警通道接入方式。

## 1. UptimeRobot 拨测接入

### 1.1 注册与新建监控

1. 注册 [https://uptimerobot.com](https://uptimerobot.com)（免费档 50 个监控、5min 间隔）。
2. Dashboard → **Add New Monitor**。
3. 关键参数：

| 字段 | 值 |
|------|-----|
| Monitor Type | HTTP(s) |
| Friendly Name | imagefree-prod-healthz |
| URL | `https://<你的域名>/v1/healthz` |
| Monitoring Interval | 5 min（免费档下限；付费档可 1min） |
| Monitor Timeout | 30 sec（healthz 含 cf_solver TCP 探活，留宽一点） |
| Custom HTTP Headers | `Accept: application/json` |
| Keyword(s) | `ok` （高级档才支持；免费档只判 HTTP 2xx） |

4. **Alert Contacts To Notify** 勾选邮箱 / 企业微信 webhook（见第 2 节）。
5. 保存。

### 1.2 验证

监控建立后，UptimeRobot 在 5min 内应首次绿。手动验证：

```bash
curl -i https://<域名>/v1/healthz
# 期望 HTTP/1.1 200，body 含 "status":"ok"
```

若 status 为 `degraded`（cf_solver down）也算 HTTP 200，UptimeRobot 不会自动告警——
若要区分 degraded，付费档用 keyword 监控 `ok` 而非 `degraded`。

### 1.3 多端点建议

对生产建议至少 3 个监控：

| 端点 | 阈值 | 含义 |
|------|------|------|
| `/v1/healthz` | 5min / 2xx | 综合健康（含 cf_solver + DB） |
| `/v1/livez` | 1min / 2xx | 进程存活（最严格，挂了立即告警） |
| `/`（落地页） | 5min / 2xx | 前端可达性 |

## 2. 告警通道接入

### 2.1 邮件

UptimeRobot 默认支持邮箱告警，Alert Contacts → Add Contact → Email。

### 2.2 企业微信机器人 webhook

企业微信群 → 群机器人 → 添加 → 自定义机器人 → 复制 webhook URL（形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<KEY>`）。

UptimeRobot → Alert Contacts → Add Contact → **Webhook**：

| 字段 | 值 |
|------|-----|
| Friendly Name | weixin-robot |
| URL | 企业微信 webhook URL |
| Custom HTTP Headers | `Content-Type: application/json` |
| POST Payload Type | `application/json` |
| POST Payload | 见下方模板 |

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "## imagefree 监控告警\n> 监控名: <span>monitorFriendlyName</span>\n> 状态: <span>alertType</span>\n> 时间: <span>alertDateTime</span>\n> 详情: [查看](<span>monitorURL</span>)"
  }
}
```

> UptimeRobot 会把 `<span>...</span>` 占位符替换为实际值（见官方文档"Variables you can use in your webhook"）。

### 2.3 钉钉机器人 webhook（备选）

钉钉自定义机器人 → 安全设置勾"加签"或"自定义关键词"（关键词建议设 `imagefree`）。

POST Payload（钉钉 text 消息）：

```json
{
  "msgtype": "text",
  "text": {
    "content": "imagefree 告警: monitorFriendlyName alertType"
  }
}
```

### 2.4 Telegram Bot（可选）

BotFather 创建 bot，获取 token，邀请 bot 进群。webhook URL：

```
https://api.telegram.org/bot<TOKEN>/sendMessage
```

POST Payload（form-urlencoded，UptimeRobot 支持 JSON 时改 JSON）：

```
chat_id=<群 ID>&text=imagefree 告警: monitorFriendlyName alertType
```

## 3. 故障响应 SOP

| 告警 | 第一步 | 第二步 |
|------|--------|--------|
| `/v1/livez` 非 2xx | SSH 进服务器，`docker compose ps` 看容器状态 | 容器停：`docker compose up -d api`；容器在但 livez 红：看 `docker logs imagefree-api --tail 200` |
| `/v1/healthz` degraded | `docker compose exec api curl -s localhost:8100/v1/healthz \| jq .cf_solver` | cf_solver down：`docker compose restart cfsolver`；仍 down：看 cfsolver 日志 |
| `/` 非 2xx | 反代层（Caddy/nginx）配置或证书问题 | 看 `docker logs <反代>` |

## 4. 已知限制

- UptimeRobot 免费档 5min 间隔意味着 RPO ≤ 5min——宕机最迟 5min 后告警。需更快建议付费档或自建 Blackbox Exporter。
- 拨测 IP 固定，若被自家 IP 黑名单拦截会误报。建议把 UptimeRobot 监控 IP 加入 `IF_IP_WHITELIST`（但 UptimeRobot 不公布固定 IP 段，可改成放行 `IF_REQUESTS_PER_MINUTE` 不限的端点如 `/v1/livez`）。
- HTTPS 证书过期 UptimeRobot 会告警，但 Letsencrypt 自动续期失败要先自查 crontab / certbot timer。
