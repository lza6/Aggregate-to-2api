# ADR: 架构演进 — 单机生产 → 成熟 SaaS（分阶段）

> 2026-09-26 ｜ Spec 008 US6 ｜ 现状基线：ARM64 单机 2C/4G，nginx→FastAPI 8100 + cfsolver 8001 + SQLite(aiosqlite) + 内置队列/token 池/代理池(2076)

## 决策原则

- **成本现实**：单机 4G 内存，不做重架构（K8s/Kafka/微服务）除非收益明确
- **渐进**：P0 免费高收益先落地；P1 有界投入；P2 保持方案不实施
- **Truth**：SQLite 单写者模型在单机下正确且够用；"复制/分片"只在流量证明需要时迁移

---

## 1. Load Balancer（流量分发）

| 项 | 内容 |
|----|------|
| 现状 | 单机 nginx :443 直接反代 8100，无 LB |
| 演进 | 阶段1：Cloudflare 免费层（DNS 代理 + CDN + 基础 DDoS）；阶段2：多节点时 nginx upstream + 会话粘性；阶段3：地域多活才上真实 LB |
| 收益 | CF 免费抗 DDoS + TLS 卸载 + 静态缓存 |
| 成本 | 域名接管（DNS 改 CF NS）+ 免费额度内 0 元 |
| 风险 | CF 中转可能影响代理池出口识别（需测 turnstile 是否仍过） |
| 优先级 | **P1** |
| 落地 | 1) 域名 NS 迁 CF 2) 开橙色云代理 3) 验证 chat/生成/turnstile 全链路 |

## 2. Caching（Redis Cache-Aside）

| 项 | 内容 |
|----|------|
| 现状 | 无 Redis；gallery 列表用内存 LRU + SQLite；/v1/models、/v1/chat/models 每次查询 |
| 演进 | 阶段1：**热读缓存**（/v1/models /v1/chat/models /v1/providers 短 TTL 60s）— 用现有 cache_store 或直接 redis；阶段2：会话/用量计数异步写 |
| 收益 | 模型目录读路径 P95 降 ~10 倍；token 池/健康快照可缓存 |
| 成本 | Redis 7-alpine 内存 ~50MB（compose 已有 profile，裸机 apt/pip 起一个也行） |
| 风险 | 缓存失效一致性（模型目录低频变，60s TTL 足够） |
| 优先级 | **P0（模型目录缓存）** / P1（全量接 Redis） |
| 落地 | 1) 裸机起 redis-server（或 apt install redis）2) IF_REDIS_ENABLED=1 + IF_REDIS_URL 3) models 端点 cache-aside 4) 压测对比 |

## 3. CDN（静态内容加速）

| 项 | 内容 |
|----|------|
| 现状 | landing/admin dist 由 nginx 直接出，无缓存头、无 CDN |
| 演进 | 阶段1：nginx 给 /admin/assets + /assets 加 immutable 缓存头（文件名带 content-hash）；阶段2：Cloudflare CDN 缓存静态 |
| 收益 | 首屏 TTFB 降；带宽省；全球访问快 |
| 成本 | 0（加 headers 即可） |
| 风险 | 低（hash 文件名天然防缓存击穿） |
| 优先级 | **P0（缓存头）** |
| 落地 | nginx location 加 `add_header Cache-Control "public, max-age=31536000, immutable"` 于 assets |

## 4. Database Replication / Sharding

| 项 | 内容 |
|----|------|
| 现状 | SQLite 单文件（imagefree.db），WAL 模式，aiosqlite 单写者 |
| 演进 | 阶段1：**Litestream 异地备份**（compose 已有 profile：秒级 WAL 复制到对象存储）；阶段2：读量爆增才迁 PostgreSQL（只读副本）；阶段3：分片（多租户/时序才需要） |
| 收益 | SQLite 单机正确性最高；Litestream 解决备份/恢复 |
| 成本 | Litestream 免费（需对象存储 bucket）；Postgres 迁移成本高 |
| 风险 | SQLite 写并发上限（单写者）——当前入口已串行化队列，够用 |
| 优先级 | **P1（Litestream 备份立即做）**；P2（Postgres 方案保留） |
| 落地 | 1) 开 backup profile / 配 S3 2) 每日备份 cron 3) 恢复演练记录 |

## 5. Message Queues（Kafka/RabbitMQ）

| 项 | 内容 |
|----|------|
| 现状 | 内置 asyncio 有界队列 + worker 池（engine.py），无外部队列 |
| 演进 | 结论：**不需要**。单机吞吐由 worker 池 + token 池 + 代理池决定，外部 MQ 只增加运维面 |
| 收益 | 0（当前规模） |
| 成本 | Kafka/RabbitMQ 内存/运维高 |
| 优先级 | **P2（不实施，保持方案）** |
| 落地 | 流量 10x 或需跨进程可靠投递时再评估 |

## 6. Rate Limiting（接口保护）

| 项 | 内容 |
|----|------|
| 现状 | L1 令牌桶（IF_RATE_TOKEN_*）+ L2 滑窗（IF_REQUESTS_PER_MINUTE）+ IP 封禁 |
| 演进 | 缺口核对：/v1/chat/completions 限流（现有 chat 有 IP 限额）、上传/编辑路径、管理端点；补 X-RateLimit-* 响应头一致性 |
| 收益 | 防滥用 + 调用方可见配额 |
| 成本 | 低 |
| 优先级 | **P1** |
| 落地 | 1) 审计限流覆盖端点清单 2) 补缺口 3) 压测验证 429 语义 |

## 7. Circuit Breaker（故障隔离）

| 项 | 内容 |
|----|------|
| 现状 | solver_guard（turnstile 熔断）+ 代理池熔断（连续失败降级）+ registry provider health |
| 演进 | 缺口：上游生成失败率熔断（imagefree 连续 429 → 降级 aifreeforever）；聊天 provider 熔断 |
| 收益 | 上游抖动不拖垮全站 |
| 成本 | 低（复用 registry.degrade/mark_down） |
| 优先级 | **P1** |
| 落地 | provider health 已具备，补聊天 provider 熔断阈值 |

## 8. Health Checks / Observability

| 项 | 内容 |
|----|------|
| 现状 | /v1/livez + /v1/healthz（solver/worker/queue/providers）+ /metrics（Prometheus）+ WebSocket 日志 |
| 演进 | 缺口：结构化日志字段（trace_id 已有）、告警 webhook（IF_COST_ALERT 已有成本告警）、关键路径 APM trace 抽样 |
| 收益 | 排障快、告警早 |
| 成本 | 低（Prometheus profile 已有） |
| 优先级 | **P1（告警 webhook + trace 抽样配置）** |
| 落地 | 1) 起 obs profile（Prometheus+Grafana）2) 配 Alertmanager webhook 3) 验证 /metrics 抓取 |

---

## 建议立即落地项（低成本高收益 ≤3）

1. **nginx 静态缓存头**（CDN 前置，0 成本，P0）
2. **模型目录缓存**（/v1/models + /v1/chat/models cache-aside 60s TTL，读路径 P95 大降）
3. **Litestream 异地备份**（数据安全，compose profile 现成）
