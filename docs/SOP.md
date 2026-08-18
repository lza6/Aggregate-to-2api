# imagefree API 标准操作程序（SOP）

> 版本: 2.2.0 | 最后更新: 2026-08-19

---

## 1. 启动流程

### 1.1 本机开发启动

**前置条件**：
- Python 3.11+ 虚拟环境（复用 GPT 项目或独立）
- 依赖已安装：`pip install -r requirements.txt`
- cf_solver 子服务已就绪

**快速启动**（推荐）：
```powershell
# 双击 start.bat，或：
powershell -ExecutionPolicy Bypass -File start.ps1
```

**手动分步启动**：

终端 1 — cf_solver（Turnstile 求解器）：
```powershell
cd ../私单/GPT自动化注册的项目/cf_solver
../.venv/Scripts/python.exe boterdrop_wrapper.py
```

终端 2 — API 服务：
```powershell
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8100
```

**验证启动**：
```powershell
curl http://127.0.0.1:8100/v1/healthz
# 预期: {"status":"ok","cf_solver":"up",...}
curl http://127.0.0.1:8100/v1/models
# 预期: 返回 45+ 模型列表
```

### 1.2 Docker 部署启动

参见 `deploy/README.deploy.md` 完整说明。

```bash
cd /home/ubuntu/imagefree-api
sudo docker compose up -d
# 验证:
curl http://127.0.0.1:8100/v1/healthz
```

---

## 2. 配置说明

### 2.1 核心配置项

配置通过环境变量控制，参见 `.env.example` 或 README 配置表。

**必须配置的变量**：
- 无（所有变量有默认值，可直接启动）

**推荐根据环境调整的变量**：

| 环境 | 变量 | 推荐值 | 说明 |
|------|------|--------|------|
| 本机（走代理） | `IF_PROXY` | `http://127.0.0.1:10808` | Clash 代理地址 |
| 本机（走代理） | `IF_WORKERS` | `4` | 本机资源有限 |
| 服务器（直连） | `IF_PROXY` | 空 | 显式清空 |
| 服务器（直连） | `IF_WORKERS` | `10` | 充分利用服务器 |
| 服务器（直连） | `IF_TOKEN_POOL_SIZE` | `2` | 单槽求解器 |
| 服务器（直连） | `IF_FREE_PROXY` | `1` | 免费代理池（aifreeforever 必需） |
| 测试环境 | `IF_MOCK_REGISTER` | `1` | 号池返回 mock 账号 |
| 测试环境 | `IF_FREE_PROXY` | `0` | 关闭代理抓取 |

### 2.2 环境变量文件

```bash
# 复制示例文件，按需修改
cp .env.example .env
# 或参考 deploy/.env.example
```

### 2.3 特性开关速查

| 特性 | 开关 | 默认 | 说明 |
|------|------|------|------|
| 持久化队列 | `IF_PERSISTENT_QUEUE_ENABLED` | `0` | 关闭时可节省 DB 写入 |
| 幂等提交 | `IF_IDEMPOTENCY_ENABLED` | `0` | 按需开启 |
| 免费代理池 | `IF_FREE_PROXY` | `0` | 生产推荐开启 |
| 号池自动注册 | `IF_ACCOUNT_AUTO` | `1` | 测试可关 |
| 批量写合并 | `IF_DB_BATCH_ENABLED` | `1` | 非必要不关 |
| Worker 自动伸缩 | `IF_WORKER_AUTO` | `0` | 生产推荐开启 |
| 健康探测 | `IF_HEALTH_CHECK_ENABLED` | `1` | 推荐开启 |
| 死信队列 | `IF_DLQ_ENABLED` | `1` | 推荐开启 |
| 图生图跨进程锁 | `IF_EDIT_MUTEX_ENABLED` | `1` | 多实例部署必须开 |

---

## 3. 部署流程

### 3.1 代码同步到服务器

```bash
# 本地打包
python scripts/sync_deploy.py sync

# 或手动上传到服务器
# 将 api/ 目录上传到 /home/ubuntu/imagefree-api/
```

### 3.2 构建并重启

```bash
cd /home/ubuntu/imagefree-api

# 仅更新 api 服务
sudo docker compose build api && sudo docker compose up -d api

# 更新 cf_solver
sudo docker compose build && sudo docker compose up -d

# 查看日志
sudo docker logs -f imagefree-api
sudo docker logs -f imagefree-cfsolver
```

### 3.3 部署后验证清单

- [ ] `curl /v1/healthz` → `status:"ok"`, `cf_solver:"up"`
- [ ] `curl /v1/models` → 返回 45+ 模型
- [ ] `curl /v1/account-pool` → 号池数据正常
- [ ] 测试生成：`curl -X POST /v1/generate/async -d '{"prompt":"test"}'`
- [ ] 检查日志无异常

### 3.4 回滚流程

```bash
cd /home/ubuntu/imagefree-api
# 恢复到上一个版本（假设 git 管理）
git checkout <上一版本标签>
sudo docker compose build api && sudo docker compose up -d api
```

---

## 4. 故障排查

### 4.1 healthz 状态异常

| 症状 | 可能原因 | 排查步骤 |
|------|----------|----------|
| `cf_solver: down` | 8001 未监听 | 1. `curl http://127.0.0.1:8001/health`<br>2. 启动 cf_solver<br>3. 检查 `cf_solver/logs/cf_solver.log` |
| `solver_status: circuit_open` | 连续求解失败 | 1. 检查代理是否正常<br>2. 检查 cf_solver 日志<br>3. 30s 后自动探测恢复 |
| `solver_status: degraded` | 部分求解失败 | 1. 查看 `solver_window_success_rate`<br>2. 检查代理池健康 |
| `status: down` | 服务不可用 | 1. `docker logs imagefree-api`<br>2. 检查内存/磁盘 |

### 4.2 请求失败

| 错误类型 | 原因 | 处理 |
|----------|------|------|
| `429 queue_full` | 队列满 | 1. 稍后重试<br>2. 考虑增大 `IF_MAX_QUEUE`<br>3. 检查 worker 是否正常运行 |
| `turnstile 求解失败` | Turnstile 解析失败 | 1. 检查 cf_solver 代理<br>2. 检查 sitekey 是否过期<br>3. 检查 solver 熔断状态 |
| `human verification failed` | token 被上游拒绝 | 自动重试（换新 token），手动无需操作 |
| `生成硬超时` | worker 超时 | 1. 检查上游是否正常<br>2. 考虑增大 `IF_TASK_HARD_TIMEOUT` |
| `图生图失败` | 上游编辑任务失败 | 1. 检查上游并发槽状态<br>2. 检查 `edit_inflight` 指标 |

### 4.3 性能问题

| 问题 | 可能原因 | 优化 |
|------|----------|------|
| 生成慢 | token 预取不足 | 增大 `IF_TOKEN_POOL_SIZE` |
| 队列积压 | worker 不够 | 1. 开启 `IF_WORKER_AUTO=1`<br>2. 增大 `IF_WORKERS` |
| 入口 429 | 并发超限 | 1. 增大 `IF_MAX_QUEUE`<br>2. 客户端改用 async 模式 |
| 图生图排队 | 上游并发=1 | 配置住宅代理池绕过 |

### 4.4 内存/磁盘

- **内存不足**：服务器 2G 内存较紧张，cf_solver 限制 1.5G，api 限制 256M
- **磁盘增长**：`data/imagefree.db` 会随请求量增长，`IF_DB_RETENTION_DAYS` 控制保留天数
- **base64 文件**：`data/imgs/` 目录自动清理（`IF_BASE64_FILE_TTL` 控制 TTL）

### 4.5 日志查看

```bash
# API 实时日志
sudo docker logs -f imagefree-api

# 最近 200 条日志（API 端点）
curl http://127.0.0.1:8100/v1/logs?lines=200

# 最近失败请求
curl http://127.0.0.1:8100/v1/errors?limit=20

# 死信队列
curl http://127.0.0.1:8100/v1/dead-letter-queue
```

---

## 5. 添加新提供商步骤

### 5.1 创建 Provider 实现

1. 在 `api/providers/` 下新建 `<provider_name>.py`
2. 继承 `providers/base.py` 中的 `Provider` 基类
3. 实现 `generate()` 抽象方法
4. 定义 `ModelSpec` 列表（模型 id 格式：`<前缀>/<上游真实模型名>`）
5. 可选：实现 `credits()`, `health()`, `health_check()`, `needs_account()`, `needs_proxy_per_request()`

### 5.2 注册到注册表

编辑 `api/providers/registry.py`：
```python
from . import <provider_name>
registry.register(<provider_name>.YourProvider())
```

### 5.3 配置环境变量

按需添加新配置项到 `api/config.py`，并更新 `.env.example`。

### 5.4 测试

```bash
# 验证模型列表
curl http://127.0.0.1:8100/v1/models | jq '.items.<前缀> | length'

# 运行多提供商 E2E（mock 模式）
python scripts/e2e_providers.py

# 运行提供商单元测试
python -m pytest tests/test_providers.py -v
```

### 5.5 检查清单

- [ ] Provider 类正确继承 `Provider` 基类
- [ ] `generate()` 方法返回 `GenerationResult` 类型
- [ ] 模型 id 格式为 `<前缀>/<上游真实模型名>`
- [ ] `ModelSpec` 的 `capabilities` 正确声明能力
- [ ] 已在 `registry.py` 中注册
- [ ] 已添加配置项到 `config.py`
- [ ] 已有测试覆盖（至少基本生成测试）

---

## 6. 测试运行

### 6.1 单元测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行指定测试文件
python -m pytest tests/test_priority_queue.py -v

# 运行带覆盖率的测试
python -m pytest tests/ --cov=api --cov-report=term-missing

# 运行特定标记的测试
python -m pytest tests/ -m "unit"
python -m pytest tests/ -m "integration"
```

### 6.2 E2E 测试

```bash
# Mock 模式（零真实求解消耗，推荐日常使用）
python scripts/e2e_validate.py --mode mock

# 真实模式（需先启动 cf_solver + 本机代理）
python scripts/e2e_validate.py --mode real

# 多提供商 E2E（mock 全开，27 项）
python scripts/e2e_providers.py
```

### 6.3 压测

```bash
# 本机压测
python scripts/loadtest.py

# 服务器压测（需在服务器上运行）
cd /home/ubuntu/imagefree-api
python3 loadtest.py
```

### 6.4 测试覆盖率目标

| 等级 | 覆盖率 | 模块 |
|------|--------|------|
| 优秀 | >= 90% | solver_guard, config, base, cache, semaphore_manager |
| 良好 | >= 80% | worker, db, registry, base64_store |
| 需改进 | < 80% | main, providers, imagefree_client, account_pool, proxy_pool |
| 缺失 | 0% | free_proxy_fetcher, registerer |

---

## 7. 架构概览

```
入口 ──POST /v1/generate ──► ┌───────────────────────────────────────────────┐
   (同步/异步)                │  FastAPI (:8100)                              │
                              │  AuthMiddleware → RateLimiter → 校验 → DB 入库  │
                              └───────────────────────────────────────────────┘
                                    │
                              优先级队列(0/1/2) ── 分级上限 ── 429 满则限流
                                    │
                            ┌───────▼────────┐
                            │  Worker 池(4~16) │◄── Token 预取池(direct+per-proxy)
                            │  (自动伸缩)      │    └── cf_solver (Turnstile 求解)
                            └───────┬────────┘
                                    │
                            ┌───────▼────────┐
                            │  多提供商路由    │── imagefree / minimaxh3 / aifreeforever / nanobanana
                            │  号池/邮箱池/代理池│
                            └────────────────┘
```

## 8. 重要端点参考

| 端点 | 用途 | 频次 |
|------|------|------|
| `GET /v1/healthz` | 健康检查 | 监控用（每 30s） |
| `GET /v1/stats` | 用量统计 | 日常监控 |
| `GET /v1/models` | 模型列表 | 客户端初始化 |
| `GET /v1/providers` | 提供商看板 | 运维监控 |
| `GET /v1/account-pool` | 号池看板 | 运维监控 |
| `GET /v1/logs` | 最近日志 | 排查异常 |
| `GET /v1/dead-letter-queue` | 死信队列 | 每周检查 |
| `GET /metrics` | Prometheus 指标 | 监控系统采集 |
| `POST /v1/generate/async` | 异步生成 | 日常调用 |
| `POST /v1/generate` | 同步生成 | 低并发调用 |
| `POST /v1/edit` | 图生图 | 图片编辑 |