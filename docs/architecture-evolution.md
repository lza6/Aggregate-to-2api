# 架构演进路线图（高并发/可扩展性评估）

> 基于 v7.2.0 单机形态（docker-compose: cfsolver + api，SQLite，2CPU/512MB 容器档）评估。
> 结论导向：每项给出 ✅适用 / ⚠️有前置 / ❌不适用 + 最小落地路径。公益单机产品，拒绝过度工程。

## 1. 当前瓶颈画像（先测再优）

| 维度 | 现状 | 真实瓶颈 |
|------|------|---------|
| API 吞吐 | uvicorn 单进程 asyncio，worker 池 4-16 | 上游生成 6-30s/张，本机并发上限≈worker 数，远未到框架瓶颈 |
| DB 写入 | SQLite WAL + 批量写 + aiosqlite | 每秒 <10 写，SQLite 富余 |
| Token 获取 | cf_solver 6.13s 均（thread=2, page=1） | **真瓶颈**：求解速率决定 token 池水位 |
| 静态资源 | landing/admin 由 FastAPI 静态出 | 单节点带宽 |
| 内存 | 512m 容器 | LRU 画廊缓存 + SSE 连接数 |

**结论：瓶颈在上游求解器与上游生成速度，不在本服务框架/DB 层。任何「换 Postgres/上 MQ/分库分表」当前都是负优化。**

## 2. 逐项评估（用户关注清单）

### Load Balancer（流量分发）
**❌ 当前不适用**。单实例部署，Nginx/HAProxy 只在 ≥2 api 实例时有意义。
触发条件：单机 CPU 持续 >80% 或需要零宕机滚动发布（当前 SSH compose up 已够）。
前置路径：api 无状态化核查（全部状态在 SQLite/内存，双实例会写冲突）→ 先解决 DB 才能水平扩。

### Caching（Redis + Cache Aside）
**⚠️ 有前置**。当前 LRU 内存缓存（画廊/模型列表）够用。
- 可先做（零成本）：模型列表/提供商状态加 5-10s 内存 TTL 缓存（已有 healthz 5s 缓存先例）
- Redis 触发条件：需要跨实例共享缓存 / 缓存量超内存 / 令牌桶限流迁集中式
- 引入成本：+30MB 内存常驻、新依赖、故障面。**单机形态不建议**。

> **P0-3 (v7.3) 标注——`api/storage/` 已实现未接入**：RedisStorageAdapter（分布式锁 SET NX EX + token 校验释放 + ZSET Lua 滑动窗口限流）**代码完整且质量合格**（单测兜底 `tests/test_redis_adapter.py`），但主链路零消费——`get_storage_adapter()` 无调用方。属"造好未接线"的前瞻能力，**不是死代码，勿删**。触发条件（CPU 持续 >80% 需双实例 / 需集中式限流）出现时，在 `lifespan` startup 挂 `get_storage_adapter()` + `IF_STORAGE_BACKEND=redis` 即可启用，无需重写。

### CDN（静态内容加速）
**✅ 立即可做（免费）**：Cloudflare 免费层套域名，landing/admin 静态资源全球边缘缓存，源站带宽压力骤降，还附赠 DDoS 防护 + WAF 免费规则。
最小落地：域名 NS 托管 CF → 开代理（橙云）→ Cache Rules：`/assets/*` cache everything。
注意：API 路径（/v1/*）设 bypass 不缓存；SSE 端点需确认 CF 代理不缓冲（免费层支持）。

### Database Replication（高可用）
**❌ 不适用**。SQLite 单文件主从复制（LiteFS/litestream）用于多活；当前单机+每日备份已够 RPO=24h。
可选项（低成本高价值）：**litestream** 实时把 WAL 流式推到 R2/S3（单二进制，~10MB 内存），把 RPO 从 24h 降到秒级。触发条件：数据丢失不可接受时。

### Sharding（水平扩展）
**❌ 不适用**。数据量 17k 行不到百万，SQLite 单文件轻松扛到 10 年。分表是伪需求。

### Message Queues（Kafka/RabbitMQ）
**❌ 不适用**。已有 asyncio.PriorityQueue + 持久化队列开关（IF_PERSISTENT_QUEUE_ENABLED），任务量级（百级/天）远不需要独立 MQ。Kafka 最小集群内存 >2GB，比 api 本身还重。

### Rate Limiting（接口保护）
**✅ 已达标**：L1 令牌桶 + 滑窗 + 每日限额 + 自动封禁 + 分片锁 + 管理 Key 鉴权。
可选增强：Cloudflare 免费层 Rate Limiting Rules（边缘拦截，源站零消耗）——与 CDN 同一步落地。

### Circuit Breaker（故障隔离）
**✅ 已达标**：solver_guard 熔断（连续失败阈值+探测恢复）+ adaptive_router 熔断 + 提供商降级。无需新增。

### Health Checks（服务探活）
**✅ 已达标**：livez（进程活）+ healthz（readiness）双口径 + compose healthcheck + solver 心跳。
可增强：外部拨测（UptimeRobot 免费层 5min 间隔监控 /v1/healthz，宕机邮件告警）——10 分钟接入。

### Observability（Logs+Metrics+Traces）
**✅ 已达标**：Prometheus /v1/metrics + OTel（可选 tail-based 采样）+ WebSocket/SSE 日志 + 审计日志。
可增强（按需）：
- Grafana Cloud 免费层接 /v1/metrics remote write（托管面板，零运维）
- 或本机 Prometheus+Grafana 单容器（+150MB 内存，公益形态可选）

## 3. 演进触发器（何时重新评估本表）

| 信号 | 触发动作 |
|------|---------|
| 单机 CPU 持续 >80% / 带宽打满 | 先 CDN → 再考虑双实例 + litestream 共享 |
| 数据丢失零容忍 | litestream → R2（RPO 秒级） |
| 需要多地域部署 | Postgres（Supabase 免费层）替换 SQLite |
| 任务量 >1k/天 或需任务编排 | 评估轻量 MQ（如 Redis Streams，非 Kafka） |
| 上游求解器成为硬瓶颈 | P0-1 cf_solver 多节点联邦（已有 solver_guard 多节点支持，只差加节点） |

## 4. 一句话总结
**当前最划算的三步：Cloudflare 免费层（CDN+WAF+限流）→ UptimeRobot 拨测 → litestream 异地备份。全部免费，零架构改动。其余项在触发器出现前都是负优化。**
