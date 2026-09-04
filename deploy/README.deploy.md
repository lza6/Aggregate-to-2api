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

## 多提供商网关部署（听风AI · 逆向号池）

> 在 imagefree 主站之上叠加 minimaxh3 / aifreeforever / nanobanana 等积分制提供商 +
> 号池自动注册 + 每日签到 + 免费/住宅代理池。部署 = 同步代码 → compose 重启 → 配代理/号池。

### 1. 同步代码并重启

```bash
# 服务器上（/home/ubuntu/imagefree-api）
# v6.8.0 起 build context = 仓库根（..），直接用根 api/ 源码构建，无需 sync_deploy 同步
cd /home/ubuntu/imagefree-api
sudo docker compose build api && sudo docker compose up -d api
curl http://127.0.0.1:8100/v1/models        # 应返回 45 模型（4 提供商）
curl http://127.0.0.1:8100/v1/account-pool   # 号池看板
```

### 2. 启用免费代理池（aifreeforever 每 IP 每日限额场景）

compose 的 api 服务 environment 加：
```yaml
- IF_FREE_PROXY=1              # 免费代理抓取（proxyscrape/geonode/proxy-list.download/proxifly 4 源）
- IF_FREE_PROXY_REFRESH_MIN=30
# 若有付费住宅代理，优先配：
# - IF_PROXY_FILE=/app/data/proxies.txt
```
验证：`sudo docker logs imagefree-api | grep 免费代理` 应看到 `sources_ok=N fetched=N injected=N`。

### 3. 号池自动补号 + 每日签到

```yaml
- IF_ACCOUNT_AUTO=1
# minimaxh3 已于 v6.8.0 全量移除（IF_MINIMAXH3_ACCOUNT_TARGET 已废弃，填了不生效）
- IF_NANOBANANA_ACCOUNT_TARGET=500  # nanobanana 每日签到续额 → 常驻 500
```
验证：`curl /v1/account-pool` 看 `nanobanana.ok` 是否增长、`auto_register: true`。

### 4. 手动批量真实注册（500 号，服务器执行）

> 前提：cf_solver 可求解（8001 通）、邮箱源 temp.tf 可达、Turnstile 不被上游风控。
> **必须配合代理池轮换**（`--use-proxy-pool`），否则同 IP 批量注册必被风控。

```bash
cd /home/ubuntu/imagefree-api
# 免费代理池兜底（先开 IF_FREE_PROXY=1 让池子有货）：
sudo docker exec imagefree-api python scripts/inject_accounts.py --provider minimaxh3 --count 500 --real --use-proxy-pool
sudo docker exec imagefree-api python scripts/inject_accounts.py --provider nanobanana --count 500 --real --use-proxy-pool
# 或从宿主机（容器内 /app/data 挂载到 ./data）：
python3 scripts/inject_accounts.py --provider minimaxh3 --count 500 --real --use-proxy-pool --db data/account_pool.db
```
注册成功日志 `[N/500] 注册成功 xxx@high.edu.pl credits=4`；完成后 `curl /v1/account-pool` 确认 500 号。

### 5. 注意事项（真实运行）

- minimaxh3 新号 4 积分：一次生成即耗光 → 号池必须维持 500 常驻，自动补号循环会持续补。
- nanobanana 签到奖励 7 天循环 [4,4,8,4,4,4,10]，积分 2 天过期 → 每天签到（号池自动跑），签到后尽快消费。
- aifreeforever 每 IP 每日限额：务必开 `IF_FREE_PROXY=1`（免费代理量大兜底）或住宅代理文件；429 自动冷却递增 + 24h 重置。
- 内存：号池/代理池在 api 容器内，cf_solver 每浏览器上下文 0.5-1GB；500 号并发注册时 Turnstile 求解是瓶颈（单槽 ~5s/次）。

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
