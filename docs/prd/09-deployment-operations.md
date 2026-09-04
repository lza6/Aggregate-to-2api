# 09 · 部署与运维

> 基于 `deploy/docker-compose.yml`、`deploy/README.deploy.md`、`api/lifespan.py`、`docs/SOP.md`。

## 9.1 部署架构

### 9.1.1 服务拓扑

```
┌─────────────────────────────────────────────────────────────┐
│  腾讯云东京 43.165.173.36(2C2G + 4G swap)                   │
│                                                               │
│  Docker Compose: imagefree-network (bridge)                  │
│  ┌─────────────────────┐    ┌──────────────────────────────┐ │
│  │ cfsolver (8001)     │    │ api (8100, 公网映射)         │ │
│  │ camoufox 无头浏览器 │◄───│ FastAPI + uvicorn asyncio    │ │
│  │ Turnstile 求解      │    │ mem_limit: 512m, cpus: 2     │ │
│  │ mem: 1024m, cpus: 2 │    │ depends_on: cfsolver healthy│ │
│  │ healthcheck: TCP   │    │ healthcheck: /v1/livez       │ │
│  └─────────────────────┘    │ volumes:                    │ │
│  不暴露公网端口              │   - ./data:/app/data        │ │
│                              │   - ./data/backups          │ │
│                              │   - ../frontend/dist (ro)   │ │
│                              │   - ../landing/dist (ro)    │ │
│                              └──────────────────────────────┘ │
│                                                               │
│  Caddy 反代: imagefree.tingfengai.art → 127.0.0.1:8100       │
│  crontab: 0 3 * * * python scripts/backup_db.py              │
└─────────────────────────────────────────────────────────────┘
                           │ 公网
                           ▼
              https://imagefree.tingfengai.art
```

### 9.1.2 容器资源

| 服务 | mem_limit | mem_reservation | cpus | 说明 |
|------|-----------|-----------------|------|------|
| cfsolver | 1024m | 1g | 2 | camoufox 无头浏览器,每槽约 +0.3GB |
| api | 512m | 256m | 2 | FastAPI + aiosqlite + 8 后台任务 + worker 池 + LRU 画廊缓存 |

### 9.1.3 镜像来源

- **api**:`ghcr.io/lza6/aggregate-to-2api/imagefree-api:latest`(CI 自动 push),fallback 本地 build
- **cfsolver**:`imagefree-cfsolver:7.2.0`(本地 build,`context: ..`,`dockerfile: deploy/Dockerfile.cfsolver`)

## 9.2 环境变量(部署关键项)

> 完整列表见 [06-技术规格](./06-technical-specifications.md#6.2.2-核心配置项节选),此处仅列部署必配。

### 9.2.1 必配项(docker-compose.yml environment)

```yaml
environment:
  - IF_CF_SOLVER_URL=http://cfsolver:8001
  - IF_CF_SOLVER_URLS=http://cfsolver:8001        # 多节点:逗号分隔
  - IF_SOLVER_IDLE_TIMEOUT_SECONDS=0
  - IF_ROUTING_DB=data/routing.db                  # 路由持久化(可选)
  - IF_HOST=0.0.0.0
  - IF_PORT=8100
  - IF_BASE_URL=https://imagefree.net
  - IF_SITEKEY=0x4AAAAAACE-XLGoQUckKKm_
  - IF_API_KEYS=${IF_API_KEYS}                    # 空=开放模式
  - IF_REQUESTS_PER_MINUTE=${IF_REQUESTS_PER_MINUTE:-30}
  - IF_FREE_PROXY=1                               # aifreeforever 每 IP 限额必须
  - IF_FREE_PROXY_REFRESH_MIN=10
  - IF_PROXY=                                     # 服务器直连,显式清空
  - HTTP_PROXY=
  - HTTPS_PROXY=
  - NO_PROXY=*
```

### 9.2.2 可选增强项

```yaml
# 号池自动注册
- IF_ACCOUNT_AUTO=1
- IF_NANOBANANA_ACCOUNT_TARGET=500

# 鉴权防滥用
- IF_API_KEYS=sk-key1,sk-key2
- IF_ADMIN_KEYS=admin-key1
- IF_REQUESTS_PER_MINUTE=30
- IF_AUTO_BLOCK_ENABLED=1

# 安全头
- IF_SECURITY_HEADERS_ENABLED=1
- IF_CSP_ENABLED=0

# 画廊签名
- IF_GALLERY_SIGNING_SECRET=<random>
- IF_GALLERY_SIGNING_TTL=600

# 可观测性
- IF_ALERT_WEBHOOK_URL=<企业微信/钉钉/Slack webhook>
- IF_OTEL_ENABLED=1
- IF_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# 成本告警
- IF_USD_PER_CREDIT=0.001
- IF_COST_BUDGET_USD=50.0
```

## 9.3 部署步骤

### 9.3.1 首次部署

```bash
# 1. 克隆代码到服务器
cd /home/ubuntu
git clone <repo> imagefree-api
cd imagefree-api

# 2. 构建前端产物(宿主机)
cd frontend && npm install && npm run build && cd ..
cd landing && npm install && npm run build && cd ..

# 3. 启动服务(从 deploy 目录)
cd deploy
sudo docker compose up -d

# 4. 验证
curl http://127.0.0.1:8100/v1/healthz   # {"status":"ok","cf_solver":"up",...}
curl http://127.0.0.1:8100/v1/models   # 多提供商模型列表
sudo docker ps --filter "health=healthy"

# 5. 配置 Caddy 反代(自动 HTTPS)
# /etc/caddy/Caddyfile:
#   imagefree.tingfengai.art {
#     reverse_proxy 127.0.0.1:8100
#   }
sudo systemctl reload caddy

# 6. DNS(DNSPod):imagefree A 记录 → 43.165.173.36
# 7. 腾讯云轻量防火墙放行 80/443
```

### 9.3.2 更新部署(改代码后)

```bash
cd /home/ubuntu/imagefree-api

# 仅改 api 源码/配置:重建 api 镜像
sudo docker compose build api && sudo docker compose up -d api

# 改了 cf_solver:
sudo docker compose build && sudo docker compose up -d

# 改前端:重新 build dist(只读挂载,无需重启 api)
cd frontend && npm run build && cd ..
cd landing && npm run build && cd ..
# dist 已挂载,刷新即生效
```

### 9.3.3 多节点求解器扩展

```bash
# 1. 复制 cfsolver service(docker-compose.yml)
#    cfsolver2:
#      build: { context: .., dockerfile: deploy/Dockerfile.cfsolver }
#      ... 同 cfsolver
#      networks: [imagefree]

# 2. api 的 IF_CF_SOLVER_URLS 改为逗号分隔多 URL
- IF_CF_SOLVER_URLS=http://cfsolver:8001,http://cfsolver2:8001

# 3. 可选:调权重
- IF_SOLVER_NODE_WEIGHTS={"http://cfsolver:8001":2,"http://cfsolver2:8001":1}
# 或字符串格式: http://cfsolver:8001=2,http://cfsolver2:8001=1

# 4. 重启
sudo docker compose up -d

# solver_guard 自动加权最少在途调度 + failover
curl http://127.0.0.1:8100/v1/stats | python3 -m json.tool | grep solver
```

## 9.4 健康检查

### 9.4.1 Docker healthcheck

- **cfsolver**:TCP 探活 `127.0.0.1:8001`,`interval: 30s`,`retries: 3`,`start_period: 30s`
- **api**:`/v1/livez` 返回 `{"status":"ok"}`,`interval: 30s`,`timeout: 10s`,`retries: 3`,`start_period: 15s`
- **依赖**:`depends_on: cfsolver: condition: service_healthy`(api 等待 cfsolver 健康)

### 9.4.2 健康端点

```bash
# liveness(Docker healthcheck 用,进程活即 ok)
curl http://127.0.0.1:8100/v1/livez

# readiness(聚合 cf_solver + solver + DB + 队列 + 提供商 + SLO)
curl http://127.0.0.1:8100/v1/healthz

# readyz(聚合依赖探活,任一不 ok → 503,供上游路由探活)
curl http://127.0.0.1:8100/v1/readyz

# 一键体检
curl http://127.0.0.1:8100/v1/diagnostics
```

### 9.4.3 外部拨测(可选)

- **UptimeRobot 免费层**:5min 间隔监控 `/v1/healthz`,宕机邮件告警
- **Grafana Cloud 免费层**:接 `/metrics` remote write,托管面板

## 9.5 监控与告警

### 9.5.1 Prometheus 指标

```bash
curl http://127.0.0.1:8100/metrics
```
- **指标**:出图总量、错误码分桶(`imagefree_errors_by_code`)、SSE 事件、solver 成功率/多节点明细、队列水位

### 9.5.2 OpenTelemetry 链路

- **配置**:`IF_OTEL_ENABLED=1`、`IF_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
- **采样**:tail-based,`IF_OTEL_SAMPLE_RATE=0.1`(正常 10%)、`IF_OTEL_ERROR_SAMPLE_RATE=1.0`(错误 100%)
- **traceId 串联**:一个任务 ID 看全链路 `GET /v1/tasks/{id}/logs`

### 9.5.3 实时日志

```bash
# HTTP 快照(需管理 Key)
curl -H "Authorization: Bearer <admin_key>" http://127.0.0.1:8100/v1/logs?lines=50

# WebSocket 实时推送(需管理 Key)
wscat -c "ws://127.0.0.1:8100/v1/logs/ws?api_key=<admin_key>"

# 容器日志
sudo docker logs -f imagefree-api
sudo docker logs -f imagefree-cfsolver
```

### 9.5.4 告警 webhook

- **配置**:`IF_ALERT_WEBHOOK_URL`(企业微信/钉钉/Slack 通用 JSON POST,空=不外发)
- **检查间隔**:`IF_ALERT_CHECK_INTERVAL=60`

### 9.5.5 慢日志画像

```bash
curl http://127.0.0.1:8100/v1/slow?limit=50
# threshold_ms / queue_ms / wait_token_ms / solve_ms / upstream_ms / retry_ms / total_ms / slowest_stage
```

## 9.6 备份与恢复

### 9.6.1 自动备份

- **crontab**:`0 3 * * * cd /home/ubuntu/imagefree-api && python scripts/backup_db.py --db data/imagefree.db --out-dir data/backups`
- **持久化**:`./data/backups` 独立卷挂载
- **RPO**:24h(每日全量热备)

### 9.6.2 恢复

```bash
# 恢复见 docs/SOP.md「DB 备份与恢复」
python scripts/restore_db.py --backup <备份文件> --target data/imagefree.db
```

### 9.6.3 可选增强(零成本)

- **litestream**:实时把 WAL 流式推到 R2/S3(单二进制,~10MB 内存),RPO 从 24h 降到秒级
- **触发条件**:数据丢失不可接受时

## 9.7 数据清理

### 9.7.1 自动清理

- **DB 启动清理**:`lifespan` 启动时 `db.cleanup(DB_RETENTION_DAYS=365)` 删除过期任务
- **base64 文件**:`base64_store.clean_base64_files(IF_BASE64_FILE_TTL=86400)` 启动清理 + 定时清理
- **磁盘配额**:`IF_IMG_MAX_GB=5.0`,超过后按最旧优先清理至 80%
- **日志**:`IF_LOG_RETENTION_DAYS=14` 滚动清理
- **WAL checkpoint**:每 5 分钟回收 `-wal` 体积(`_WAL_CHECKPOINT_INTERVAL_SECONDS=300`)

### 9.7.2 手动清理

```bash
# 清空死信队列(需管理 Key)
curl -X DELETE -H "Authorization: Bearer <admin_key>" http://127.0.0.1:8100/v1/dead-letter-queue

# DLQ 重试(需管理 Key)
curl -X POST -H "Authorization: Bearer <admin_key>" http://127.0.0.1:8100/v1/dead-letter-queue/<task_id>/retry
```

## 9.8 SOP(标准操作流程)

> 详见 `docs/SOP.md`,此处仅列关键场景。

### 9.8.1 服务启停

```bash
# 启动
cd /home/ubuntu/imagefree-api/deploy
sudo docker compose up -d

# 停止(保留 ./data 数据)
sudo docker compose down

# 重启单个服务
sudo docker compose restart api
sudo docker compose restart cfsolver
```

### 9.8.2 故障排查

```bash
# 1. 看健康状态
curl http://127.0.0.1:8100/v1/healthz | python3 -m json.tool

# 2. 看容器状态
sudo docker ps --filter "health=healthy"
sudo docker ps -a  # 含已停止

# 3. 看容器日志
sudo docker logs --tail 100 -f imagefree-api
sudo docker logs --tail 100 -f imagefree-cfsolver

# 4. 一键体检
curl http://127.0.0.1:8100/v1/diagnostics | python3 -m json.tool

# 5. 单任务全链路
curl http://127.0.0.1:8100/v1/tasks/<task_id>/logs | python3 -m json.tool

# 6. 慢请求画像
curl http://127.0.0.1:8100/v1/slow | python3 -m json.tool
```

### 9.8.3 号池补号

```bash
# 自动补号(配 IF_ACCOUNT_AUTO=1 后自动跑)
# 手动批量真实注册(需代理池轮换,防风控)
sudo docker exec imagefree-api python scripts/inject_accounts.py \
  --provider nanobanana --count 500 --real --use-proxy-pool

# 验证
curl http://127.0.0.1:8100/v1/account-pool | python3 -m json.tool
```

### 9.8.4 上游风控应对

- **Turnstile 求解失败**:看 `solver_guard.snapshot()`,熔断时 30s 后自动探测恢复
- **邮箱源 429**:email_pool 自动退避切换备用源
- **代理 429**:proxy_pool 递增冷却(0/30/90/300/900s),24h 重置
- **站点改版**:ActionSniffer 动态嗅探自愈(nanobanana),失败回退静态 Action ID

## 9.9 服务器资源约束

### 9.9.1 内存

- **2G 内存较紧张**:已扩 swap 到 4G(`/swapfile2`)
- **cfsolver**:`mem_limit: 1024m`,每浏览器槽约 0.3GB,单槽配置
- **api**:`mem_limit: 512m`,高负载 OOM 风险已通过 LRU 画廊缓存 + SSE 连接数控制缓解

### 9.9.2 SSH 长命令

- **问题**:SSH 桥长命令易断(broken pipe)
- **解决**:`setsid nohup <命令> > log 2>&1 &` 后台跑,再查日志

## 9.10 架构演进路线

> 详见 `docs/architecture-evolution.md`。当前最划算的三步(全部免费,零架构改动):

1. **Cloudflare 免费层**(CDN + WAF + 限流):套域名,landing/admin 静态资源全球边缘缓存
2. **UptimeRobot 拨测**:5min 间隔监控 `/v1/healthz`,宕机邮件告警
3. **litestream 异地备份**:实时把 WAL 推到 R2/S3,RPO 秒级

其余项(Postgres/Kafka/Redis 集群/分表/Load Balancer)在触发器出现前都是负优化。
