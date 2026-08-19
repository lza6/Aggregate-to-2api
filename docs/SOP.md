# imagefree API 标准操作程序（SOP）

> 版本: 2.3.0 | 最后更新: 2026-08-19
> 适用: 本机（Windows 开发）+ 线上服务器（腾讯云东京 43.165.173.36，Docker Compose）
> 公网入口: `https://imagefree.tingfengai.art`（Caddy 自动 HTTPS → `127.0.0.1:8100`）

---

## 1. 服务启动流程

### 1.1 本机开发启动

**前置条件**：
- Python 3.11+ 虚拟环境（项目 `.venv`，会自动检测；或复用父级 GPT 项目 `.venv`）
- 依赖已安装：`.venv\Scripts\pip install -r requirements.txt`
- cf_solver 子服务已就绪（Turnstile 求解器，端口 8001）

**快速启动**（推荐，双击或命令行）：
```powershell
# 双击 start.bat（纯 ASCII 壳，转调 start.ps1 以支持中文路径），或：
powershell -ExecutionPolicy Bypass -File start.ps1
```
`start.ps1` 自动完成：
1. 自动探测 Python 解释器（项目 `.venv` > 父级 `.venv` > PATH）
2. 自动探测 cf_solver 目录并拉起（若 8001 未监听），等待就绪最多 60s
3. 前台运行 `uvicorn api.main:app --host 127.0.0.1 --port 8100`（Ctrl+C 停止）

**手动分步启动**：
```powershell
# 终端 1 — cf_solver（Turnstile 求解器）
cd ../私单/GPT自动化注册的项目/cf_solver
../.venv/Scripts/python.exe boterdrop_wrapper.py

# 终端 2 — API 服务
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8100
```

**验证启动**：
```powershell
curl http://127.0.0.1:8100/v1/healthz
# 预期: {"status":"ok","cf_solver":"up",...}
curl http://127.0.0.1:8100/v1/models
# 预期: 返回 45+ 模型列表（4 提供商）
```

### 1.2 服务器 Docker 启动

```bash
cd /home/ubuntu/imagefree-api
sudo docker compose up -d          # 首次或全量启动
# 验证:
curl http://127.0.0.1:8100/v1/healthz   # 需在服务器上执行，或公网 curl
curl https://imagefree.tingfengai.art/v1/healthz
```

Compose 服务结构：
| 服务 | 容器名 | 端口 | 资源限制 | 说明 |
|------|--------|------|----------|------|
| cfsolver | `imagefree-cfsolver` | 8001（仅内部） | mem 1500m, cpus 2 | Turnstile 求解，healthcheck 30s |
| api | `imagefree-api` | 8100（公网） | mem 256m, cpus 1 | FastAPI 服务，`depends_on` cfsolver 健康，挂载 `./data` |

停止服务：`sudo docker compose down`（保留 `./data` 数据不丢）。

---

## 2. 前端构建流程

**项目**：`frontend/`（React 19 + TypeScript + Vite 6 + recharts）

```powershell
cd frontend
npm install                      # 首次：安装依赖（node_modules 已存在可跳过）
npm run build                    # 构建: tsc -b && vite build → frontend/dist/
npm run dev                      # 开发模式（热更新，代理配置见 vite.config.ts）
npm run preview                  # 本地预览构建产物
```

**开发代理**（`frontend/vite.config.ts`，仅 dev server 生效）：
- `/v1` → `http://127.0.0.1:8100`
- `/metrics` → `http://127.0.0.1:8100`

**构建产物**：`frontend/dist/`（`index.html` + `assets/`）。dist 已生成（latest build 在仓库中），正常迭代流程为：
1. 改 `frontend/src/` 源码
2. `npm run build`
3. 将 dist 部署到服务器（见 §3.2）

> 生产静态服分为两类：
> - **API 文档首页**：`api/static/`（`docs.html` 等，随 api 镜像同步部署，见 sync_deploy 的 DIRS）
> - **React 看板前端**：`frontend/dist/`（实时日志、画廊、metrics 看板等）

---

## 3. 部署流程（本地 + 服务器）

### 3.1 本地构建与同步检查

```powershell
# 后端 — 检查 deploy/api 与根 api/ 是否漂移（改代码后必查）
python scripts/sync_deploy.py check    # exit 1 = 有差异
python scripts/sync_deploy.py sync     # 把 api/*.py、providers/、static/ 同步到 deploy/api/

# 前端 — 构建 dist（§2）
cd frontend; npm run build
```

> `deploy/api` 是线上部署副本；**必须**保持与根 `api/` 一致（逐文件哈希比对），否则上线版本与本地开发版漂移（M9 风险）。

### 3.2 代码上传服务器

方式 A（打包上传，推荐）：
```bash
# 本地把 deploy/api + deploy/cf_solver + 其余部署文件上传到 /home/ubuntu/imagefree-api
# 前端 dist 上传到 /home/ubuntu/imagefree-api/frontend/dist（或独立静态目录）
rsync -av deploy/ ubuntu@43.165.173.36:/home/ubuntu/imagefree-api/
```

方式 B（对照 deploy/README.deploy.md 手动上传 `api/` 目录）。

### 3.3 服务器构建并重启

```bash
cd /home/ubuntu/imagefree-api

# 仅更新 api 服务（最常见）
sudo docker compose build api && sudo docker compose up -d api

# 更新 cf_solver（改了 solver 相关才需要）
sudo docker compose build && sudo docker compose up -d
```

> 注意：服务器 2G 内存较紧张（已扩 swap 4G）。SSH 桥长命令易断（broken pipe），
> 用 `setsid nohup <命令> > log 2>&1 &` 后台跑，再查日志。

### 3.4 部署后验证清单

```bash
curl http://127.0.0.1:8100/v1/healthz        # status:"ok", cf_solver:"up"
curl http://127.0.0.1:8100/v1/models         # 45+ 模型
curl http://127.0.0.1:8100/v1/account-pool   # 号池数据正常
curl http://127.0.0.1:8100/v1/stats          # 计数非零/递增
# 测试生成：
curl -X POST http://127.0.0.1:8100/v1/generate/async -H "Content-Type: application/json" -d '{"prompt":"test"}'
# 公网验证：
curl https://imagefree.tingfengai.art/v1/healthz
sudo docker ps                               # 两容器均 healthy
sudo docker logs --tail 50 imagefree-api     # 无异常堆栈
```

---

## 4. 故障排查指南

### 4.1 healthz 状态异常

| 症状 | 可能原因 | 排查步骤 |
|------|----------|----------|
| `cf_solver: down` | 8001 未监听 / 容器未健康 | 1. `curl http://127.0.0.1:8001/health`<br>2. `sudo docker ps` 看 cfsolver 状态<br>3. `sudo docker logs imagefree-cfsolver`<br>4. 本机则启动 cf_solver 并等待 30s |
| `solver_status: circuit_open` | 连续求解失败触发熔断 | 1. 检查代理是否正常（服务器为直连）<br>2. 检查 cf_solver 日志<br>3. 熔断 30s 后自动探测恢复，无需干预 |
| `solver_status: degraded` | 部分求解失败 | 1. 看 `solver_window_success_rate` 指标<br>2. 检查代理池健康（`/v1/proxy-pool`） |
| `status: down` | 服务不可用 | 1. `sudo docker logs imagefree-api`<br>2. 检查内存/磁盘（§4.4）<br>3. `sudo docker compose restart api` |

### 4.2 请求失败

| 错误类型 | 原因 | 处理 |
|----------|------|------|
| `429 queue_full` | 队列满（`IF_MAX_QUEUE` 默认 2000） | 1. 稍后重试<br>2. 增大 `IF_MAX_QUEUE`<br>3. 检查 worker 是否正常（`IF_WORKERS`） |
| `turnstile 求解失败` | Turnstile 解析失败 | 1. 检查 cf_solver 代理<br>2. 检查 sitekey 是否过期<br>3. 检查 solver 熔断状态 |
| `human verification failed` | token 被上游拒绝 | 自动重试（换新 token，`IF_GENERATE_MAX_ATTEMPTS=2`），手动无需操作 |
| `生成硬超时` | worker 超过硬超时 | 1. 检查上游是否正常<br>2. 增大 `IF_TASK_HARD_TIMEOUT` |
| `图生图失败` | 上游编辑任务失败（上游硬并发=1） | 1. 检查 `edit_inflight` 指标<br>2. 配多 IP 住宅代理 + `IF_EDIT_PROXY_PARALLEL>1` 绕过 |

### 4.3 性能问题

| 问题 | 可能原因 | 优化 |
|------|----------|------|
| 生成慢 | token 预取不足 | 增大 `IF_TOKEN_POOL_SIZE`（注意单槽 solver ≈5s/token 约 0.2 图/秒上限） |
| 队列积压 | worker 不够 | 1. 开启 `IF_WORKER_AUTO=1`<br>2. 增大 `IF_WORKERS`（服务器受 2G 内存约束） |
| 入口 429 | 并发超限 | 1. 增大 `IF_MAX_QUEUE`<br>2. 客户端改用 async 模式 |
| aifreeforever 限额 | 免费号池每 IP 每日限额 | 开启 `IF_FREE_PROXY=1`，日志应见 `免费代理 ... sources_ok=N fetched=N injected=N` |

### 4.4 内存 / 磁盘

- **内存不足**：服务器 2G 内存紧张。cf_solver 限 1.5G、api 限 256M（compose 已配 mem_limit）。给 cf_solver 加浏览器槽前先确认 RAM（每槽 ≈0.3GB+）
- **磁盘增长**：`data/imagefree.db` 随请求量增长，`IF_DB_RETENTION_DAYS` 控制保留天数
- **base64 文件**：`data/imgs/` 自动清理（`IF_BASE64_FILE_TTL`）
- 日志已限容：compose 日志 `max-size: 10m, max-file: 3`，不会无限膨胀

### 4.5 排查入口总览

```
实时日志:   sudo docker logs -f imagefree-api       （服务器）
在线日志:   curl http://127.0.0.1:8100/v1/logs?lines=200   （内存环形缓冲，最多 200 条）
失败明细:   curl http://127.0.0.1:8100/v1/errors?limit=20   （prompt 仅截断前 60 字符）
死信队列:   curl http://127.0.0.1:8100/v1/dead-letter-queue
代理池:     curl http://127.0.0.1:8100/v1/proxy-pool
指标:       curl http://127.0.0.1:8100/metrics
审计日志:   cat data/audit.log                            （服务器宿主机）
```

---

## 5. 监控和告警说明

### 5.1 指标端点

| 端点 | 内容 | 用途 |
|------|------|------|
| `GET /metrics` | Prometheus 文本格式（prometheus_client）：请求/出图/失败/在途/排队/token 池水位/DB 行数/运行时长/solver 求解质量 | Prometheus 采集（`include_in_schema=False`，格式 `text/plain; version=0.0.4`） |
| `GET /v1/healthz` | 服务/求解器/熔断/窗口成功率 | 存活探针，建议每 30s 轮询（compose healthcheck 已内置同款逻辑） |
| `GET /v1/stats` | 总请求/出图/失败/平均耗时/当前并发/排队/按日(14)+月(12) | 日常用量监控 |
| `GET /v1/providers` | 提供商看板 | 多提供商健康 |
| `GET /v1/account-pool` | 号池看板（各提供商 ok 数、auto_register） | 号池水位 |
| `GET /v1/gallery` | 最近完成作品 | 画廊（前端首页每 15s 刷新） |

### 5.2 内置告警引擎（无需外部 Prometheus + AlertManager）

`api/alerting.py` 内置轻量告警：**规则评估 + 冷却抑制 + 日志触达**。命中时通过日志 `告警触发 [severity/name]: message` 输出（`imagefree_api.alerting` logger）。

| 规则名 | 级别 | 触发条件 | 冷却 |
|--------|------|----------|------|
| `queue_backlog` | warning | 排队任务数 > 1000 | 300s |
| `high_error_rate` | critical | 近 5 分钟窗口错误率 > 20%（`window_requests>0` 且 `window_errors/窗口请求 > 0.2`） | 300s |
| `solver_circuit_open` | critical | 求解器熔断已开启 >= 30s | 60s |
| `token_pool_empty` | warning | token 池空 > 10s | 120s |
| `provider_down` | warning | 提供商持续不可用 > 5min | 300s |

**运维提示**：
- 告警目前落在日志，未接外部通知。若需 IM/邮件推送，可在 evaluate 触发分支挂 webhook，或由外部 Prometheus 抓 `/metrics` 并走 AlertManager
- 熔断/健康状态以 `/v1/healthz` 的 `solver_status` 为准，告警引擎评估同源快照（`engine.snapshot()` + `solver_guard.snapshot()`）

### 5.3 OpenTelemetry（可选追踪）

`IF_OTEL_ENABLED=1` 启用 OTel（默认 0 关闭，零开销降级导入）。启用后：FastAPI/HTTPX/Logging 三种 instrumentation 自动注入 `trace_id`，日志末尾追加 `[trace=<hex_id>]`。导出目标 `IF_OTEL_EXPORTER_OTLP_ENDPOINT`（默认空 = 仅控制台）。

---

## 6. 日志查看方式

### 6.1 服务器 Docker 日志

```bash
sudo docker logs -f imagefree-api          # API 实时（含 worker/token 预取日志）
sudo docker logs -f imagefree-cfsolver     # Turnstile 求解日志
sudo docker logs --tail 200 imagefree-api  # 最近 200 条
```
日志驱动 `json-file`，单文件 10MB、保留 3 份，自动轮转不膨胀。

### 6.2 在线查看（无需登录服务器）

```bash
# 最近 N 行（内存环形缓冲，1~200 行）
curl "http://127.0.0.1:8100/v1/logs?lines=200"

# WebSocket 实时日志流（前端实时日志页使用）
# 前端 Logs 页自动连接 /v1/logs/ws，客户端定期发 "ping" 服务端回 "pong" 保活
# 手动验证:
#   wscat -c ws://127.0.0.1:8100/v1/logs/ws   （或前端页面打开日志页）

# 最近失败请求明细（在线排查首选，不回传完整 prompt）
curl "http://127.0.0.1:8100/v1/errors?limit=20"
```
> `log_buffer` 为内存环形缓冲（maxlen 1000），**服务重启后丢失**；持续排查请用 docker 日志（持久化到宿主机 json-file）。

### 6.3 本机查看

```powershell
# uvicorn 前台运行时直接看终端输出
# cf_solver 日志:
Get-Content "$env:USERPROFILE\..\私单\GPT自动化注册的项目\cf_solver\logs\cf_solver.log" -Tail 100
```

---

## 7. 审计日志说明

### 7.1 位置与格式

- **文件**：`data/audit.log`（服务器容器内挂载到 `./data/audit.log`，对应宿主机 `/home/ubuntu/imagefree-api/data/audit.log`）
- **格式**：JSON Lines（每行一个 JSON 对象），UTF-8
- **条目字段**：
  ```json
  {"timestamp": "2026-08-19T03:00:00.000000+00:00", "action": "dlq.retry", "actor": "1.2.3.4", "target": "task:xxx", "detail": "重试死信队列任务"}
  ```
- **不可变性**：仅追加（append-only），永不修改已有记录（`AuditLog` 设计约束）。写入失败仅告警、不中断请求

### 7.2 记录点（当前）

| action | 触发端点 | 说明 |
|--------|----------|------|
| `dlq.retry` | `POST /v1/dead-letter-queue/{task_id}/retry` | 从死信队列移除并重试 |
| `dlq.clear` | `DELETE /v1/dead-letter-queue` | 清空死信队列 |

架构预留：`audit_log.record(action, actor, target, detail)` 为管理操作、鉴权失败、provider 状态变更等场景预留，新增管理类操作时应同步写审计。

### 7.3 查看方式

```bash
# 服务器上查看最近 50 条
tail -50 /home/ubuntu/imagefree-api/data/audit.log
# 容器内查看
sudo docker exec imagefree-api tail -50 /app/data/audit.log
```

### 7.4 运维注意

- 审计日志不受 DB 保留策略（`IF_DB_RETENTION_DAYS`）管理，累积增长需人工轮转：`data/audit.log` 达到预期大小时改名归档（如 `audit.log.2026-08-19`），新日志自动写入新 `audit.log`
- 审计日志与请求日志分离：请求明细走 SQLite `imagefree.db`，管理操作走 `audit.log`

---

## 8. 回滚流程

### 8.1 API 后端回滚（git 版本）

```bash
cd /home/ubuntu/imagefree-api
# 1. 确认当前版本与可选目标版本
git log --oneline -10
# 2. 恢复到上一版本（先保证 deploy/api 与目标一致）
git checkout <上一版本标签>
# 3. 重建并重启 api 服务
sudo docker compose build api && sudo docker compose up -d api
# 4. 验证（§3.4 清单）
```

**漂移防护**：回滚前务必跑 `python scripts/sync_deploy.py check`，确认根 `api/` 与 `deploy/api/` 一致，避免"回滚到一半"的半新半旧状态。回滚后 `sync` 一次再验证。

### 8.2 前端回滚

```powershell
# 本地重新构建旧版本代码并覆盖部署：
cd frontend
git checkout <上一版本标签>   # 或检出上一版 src
npm run build
# 将 frontend/dist 上传覆盖服务器对应目录，刷新浏览器缓存验证
```

### 8.3 数据回滚（谨慎）

- `imagefree.db`（SQLite）为增量数据，**不支持自动回滚**；如需恢复，依赖备份文件替换（若未配置备份则无法回退）
- 建议上线涉及 DB schema 变更前，先备份：
  ```bash
  cp /home/ubuntu/imagefree-api/data/imagefree.db /home/ubuntu/imagefree-api/data/imagefree.db.bak
  ```
- 参数类变更（环境变量）回滚 = 改回 compose environment → `sudo docker compose up -d api`，直接生效、无需重建

---

## 9. 重要端点参考

| 端点 | 用途 | 频次 |
|------|------|------|
| `GET /v1/healthz` | 健康检查 | 监控用（每 30s） |
| `GET /v1/stats` | 用量统计 | 日常监控 |
| `GET /v1/models` | 模型列表 | 客户端初始化 |
| `GET /v1/providers` | 提供商看板 | 运维监控 |
| `GET /v1/account-pool` | 号池看板 | 运维监控 |
| `GET /v1/logs` | 最近日志 | 排查异常 |
| `WS /v1/logs/ws` | 实时日志流 | 前端实时日志页 |
| `GET /v1/errors` | 最近失败明细 | 排查异常 |
| `GET /v1/dead-letter-queue` | 死信队列（+ retry/clear） | 每周检查 |
| `GET /metrics` | Prometheus 指标 | 监控系统采集 |
| `GET /v1/proxy-pool` | 代理池状态 | 排查代理 |
| `POST /v1/generate/async` | 异步生成 | 日常调用 |
| `POST /v1/generate` | 同步生成 | 低并发调用 |
| `POST /v1/edit` | 图生图 | 图片编辑 |
| `GET /v1/gallery` | 最近作品 | 画廊首页 |

---

## 附录 A：环境变量速查

| 变量 | 本机 | 服务器 | 说明 |
|------|------|--------|------|
| `IF_PROXY` | `http://127.0.0.1:10808` | 空（显式清空） | Clash 代理 / 直连 |
| `IF_WORKERS` | 4 | 10 | worker 并发数 |
| `IF_TOKEN_POOL_SIZE` | — | 2 | 单槽求解器 |
| `IF_FREE_PROXY` | 0 | 1 | 免费代理池（aifreeforever 必需） |
| `IF_MAX_QUEUE` | — | 2000 | 有界队列上限，满则 429 |
| `IF_GENERATE_MAX_ATTEMPTS` | — | 2 | 失败重试次数 |
| `IF_PERSISTENT_QUEUE_ENABLED` | 0 | 按需 | 持久化队列（IO 换可靠性） |
| `IF_WORKER_AUTO` | 0 | 生产推荐 1 | worker 自动伸缩 |
| `IF_OTEL_ENABLED` | 0 | 0 | OpenTelemetry 追踪开关 |
| `IF_DB_RETENTION_DAYS` | — | 按需 | DB 记录保留天数 |

完整开关与说明见 `api/config.py`、`.env.example`、`deploy/.env.example`。