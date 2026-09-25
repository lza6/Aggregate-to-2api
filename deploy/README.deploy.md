# imagefree-api 服务器部署（腾讯云东京 43.165.173.36）

> 部署目录：`/home/ubuntu/imagefree-api`
> Docker Compose 编排 `cfsolver`(8001, 内部) + `api`(8100, 公网)。
> **已上线公网**：`https://imagefree.tingfengai.art`（Caddy 自动 HTTPS）。

## 服务结构

```
imagefree-api/
├── docker-compose.yml      # 编排（api 挂载 ./data 持久化统计/数据库）
├── Dockerfile.api          # 封装服务镜像（fastapi/uvicorn/httpx）
├── Dockerfile.cfsolver     # CF 求解镜像（camoufox 无头浏览器）
├── requirements.txt
├── loadtest.py             # 并发压测脚本（服务器上跑：python3 loadtest.py）
├── api/                    # 封装服务源码（worker.py 高并发引擎 + db.py SQLite + docs.html）
├── data/
│   ├── imagefree.db        # SQLite：请求记录/统计/画廊（自动生成）
│   └── stats.json          # （旧版 JSON 统计，新架构已迁移到 db，可忽略）
└── cf_solver/              # cf_solver 源码（复用 GPT 项目）
    └── config.json         # 服务器版：headless=true / proxy_support=false（直连）
```

## 当前运行状态

```bash
sudo docker ps                     # imagefree-cfsolver + imagefree-api
sudo docker logs -f imagefree-api  # API 访问日志（含 worker/token 预取日志）
sudo docker logs -f imagefree-cfsolver  # turnstile 求解日志
curl http://127.0.0.1:8100/v1/healthz   # {"status":"ok","cf_solver":"up","processing":..,"queued":..}
curl http://127.0.0.1:8100/v1/stats     # 总量+并发+排队+日/月+平均耗时
curl http://127.0.0.1:8100/             # 对外中文 API 文档首页（统计+画廊）
```

## 用量统计（SQLite 持久化）

- `GET /v1/stats`：总请求 / 总出图 / 总失败 / **平均出图耗时** / **当前并发** / **排队数** / **按日(14)+月(12)拆分**。
- 持久化到 `./data/imagefree.db`（compose volume），**容器重启不丢**（已实测）。
- 每次 `POST /v1/generate` 或 `/v1/generate/async` 计一次请求；每次成功出图计一次出图。
- `GET /v1/gallery`：最近完成的 N 条作品（画廊，前端首页每 15s 自动刷新）。

## 高并发配置（compose 内 `environment`）

| 变量 | 服务器当前值 | 说明 |
|---|---|---|
| `IF_WORKERS` | `10` | worker 并发数（生成通道） |
| `IF_TOKEN_POOL_SIZE` | `2` | Turnstile token 预取池大小 |
| `IF_MAX_QUEUE` | `2000` | 有界队列上限，满则 429 |
| `IF_SYNC_TIMEOUT` | `300` | 同步接口最长等待 |
| `IF_GENERATE_MAX_ATTEMPTS` | `2` | 生成失败最大尝试次数；token 被上游拒绝（如 `Human verification failed`）时自动换新 token 重试一次 |
| `IF_TOKEN_WAIT_TIMEOUT` | `30` | 取 token 等待超时（秒），池空超时报错而非无限阻塞 |
| `IF_EDIT_TIMEOUT` | `3600` | 图生图轮询超时（秒，上游较慢） |
| `IF_EDIT_PROXY_FILE` | 空 | 图生图住宅代理池文件（每行一个代理 URL）。**默认空 = 直连单并发**（上游图生图硬并发=1，实测）。填多 IP 住宅代理 + `IF_EDIT_PROXY_PARALLEL>1` 后，每任务独立出口 IP 并行绕过并发限制 |
| `IF_EDIT_PROXY_PARALLEL` | `1` | 图生图并行代理会话数。>1 需多 IP 住宅代理（免费数据中心代理被 CF 403，不可用；kookeey 当前配置为固定单 IP）且受服务器内存约束（每代理 ≈0.5–1GB） |

**压测结果**（服务器 50 并发瞬时）：≈270 RPS，平均 4ms/请求，0 限流 0 失败。
**吞吐上限**：生成吞吐由 cf_solver 决定（单槽 ≈5s/token → 理论 ~0.2 图/秒）。要更高吞吐需给
cf_solver 加浏览器槽（改 `cf_solver/config.json` 的 `thread`/`page_count`，每个槽约 +0.3GB RAM）。

## 更新部署（改代码后）

```bash
cd /home/ubuntu/imagefree-api
# 仅更新 api 源码/配置后，只需重建 api 镜像：
sudo docker compose build api && sudo docker compose up -d api
# 改了 cf_solver 则：sudo docker compose build && sudo docker compose up -d
```

> 注意：服务器 2G 内存较紧张。已扩 swap 到 4G（`/swapfile2`）。cf_solver 限制 1.5G、单浏览器槽。
> SSH 桥长命令易断（broken pipe），用 `setsid nohup <命令> > log 2>&1 &` 后台跑，再查日志。

## 公网访问（已配好）

- 域名：`imagefree.tingfengai.art` → Caddy 反代 → `127.0.0.1:8100`，自动 HTTPS（Let's Encrypt）。
- DNS 归 **DNSPod** 管：`imagefree` A 记录 → `43.165.173.36`（在 DNSPod 加，不是轻量控制台）。
- 腾讯云轻量防火墙需放行 **80/443**。
- Caddy 配置 `/etc/caddy/Caddyfile`，改域名/加站点后 `sudo systemctl reload caddy`。

## 说明

- **公益开放**：无鉴权、CORS 全开。防滥用靠有界队列 429 限流；如被刷严重可降 `IF_MAX_QUEUE` 或加 IP 限流。
- **cf_solver 直连**：东京直连 imagefree.net 无需代理，`proxy_support=false`，求解约 5s（本机走代理约 9-14s）。
- 停止服务：`sudo docker compose down`（保留 `./data` 数据）。

---

## 多提供商网关部署（听风AI）

> 图片上游为 imagefree / aifreeforever（匿名免费），对话与 agent 上游为 tryingopen。
> nanobanana、minimaxh3、fal.ai 已于 v20.0.0 全量下线：不再启动自动补号/每日签到，
> `IF_NANOBANANA_ACCOUNT_TARGET` / `IF_FALAI_*` 配置不再生效。

### 1. 同步代码并重启

```bash
# 服务器上（/home/ubuntu/imagefree-api）
cd /home/ubuntu/imagefree-api
sudo docker compose build api && sudo docker compose up -d api
curl http://127.0.0.1:8100/v1/models        # 应返回 imagefree/aifreeforever 图片模型 + tryingopen 对话模型
curl http://127.0.0.1:8100/v1/chat/completions -d '{"model":"tryingopen/default","messages":[{"role":"user","content":"hi"}]}'
```

### 2. 启用免费代理池（aifreeforever / tryingopen 每 IP 限额场景）

compose 的 api 服务 environment 加：
```yaml
- IF_FREE_PROXY=1              # 免费代理抓取（proxyscrape/geonode/proxy-list.download/proxifly 4 源）
- IF_FREE_PROXY_REFRESH_MIN=30
# 若有付费住宅代理，优先配：
# - IF_PROXY_FILE=/app/data/proxies.txt
```
验证：`sudo docker logs imagefree-api | grep 免费代理` 应看到 `sources_ok=N fetched=N injected=N`。

### 3. 号池（nanobanana 下线后默认停用）

- `IF_ACCOUNT_AUTO` 默认 0，启动不再挂自动补号/每日签到；历史账号数据保留在 `data/account_pool.db`。
- 在线使用入口：落地页首页对话（HomeChat）与 `/admin`（`/` 在线聊天、`/dashboard` 仪表盘）。

## v2.3.0 更新内容

### 新特性
- **多阶段构建**: Docker 镜像体积从 ~500MB 降至 ~200MB
- **健康检查**: Docker Compose 集成 HEALTHCHECK 指令，api 等待 cfsolver 健康后才启动
- **资源限制**: CPU/内存显式约束（mem_limit + mem_reservation + cpus），防止 OOM
- **网络隔离**: 独立 bridge 网络，cfsolver 不暴露任何公网端口
- **CI/CD 管线**: GitHub Actions 自动测试 + 构建 + 发行版
- **集成测试框架**: 18 个集成测试覆盖完整流程/异步/图生图/限流/熔断/超时/降级/死信队列
- **性能测试**: 基准测试（pytest-benchmark）+ 压力测试（50 并发）
- **混沌测试**: 故障注入验证系统韧性（cf_solver 不可用/失败/恢复）
- **E2E 验收**: 独立验收脚本（30 项覆盖），全 mock 模式零外部依赖

### 部署方式
```bash
# 拉取最新代码
cd /home/ubuntu/imagefree-api
git pull origin main

# 构建并重启
sudo docker compose -f deploy/docker-compose.yml build
sudo docker compose -f deploy/docker-compose.yml up -d

# 验证
curl http://127.0.0.1:8100/v1/healthz
curl http://127.0.0.1:8100/v1/models | python3 -m json.tool

# 查看容器健康状态
sudo docker ps --filter "health=healthy"
```
