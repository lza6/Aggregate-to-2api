# imagefree-2ai · 项目上下文

听风AI —— 多提供商 AI 图像/对话生成网关。聚合 imagefree / aifreeforever / nanobanana / tryingopen / falai 五家上游，统一暴露 OpenAI 风格 `/v1/*` 接口，含号池自动化、代理池轮换、高并发异步队列、React 管理面板。

## 规则（优先级最高，覆盖一切默认行为）

- **付费 API 红线**：真实付费上游（fal.ai / imagefree 等）调用预算默认为 0。用 Mock / fixture / 录制响应验证参数拼装、轮询、回调、超时、重试、幂等；禁止为"通过测试"发起真实付费请求。
- **Windows 平台**：禁止 `.sh` 脚本，用 `node` 或 PowerShell；命令链接用 `; if($?) { }` 而非 `&&`；查可执行文件用 `where.exe`；搜索用内置 `rg`，不依赖 `grep`/`awk`/`sed`/`tmux`。
- **不自动提交**：未经明确指示不创建 commit / push / PR。提交前过 `.pre-commit-config.yaml`（ruff check+format + 基础 hooks）。
- **不可变优先**：创建新对象而非就地修改；防隐藏副作用与并发竞态。
- **真实闭环**：声称"完成/通过/修复"必须附带实际运行的命令与真实输出；Mock 仅证明隔离逻辑，不得描述为真实集成已通过。
- **敏感数据**：密钥仅经环境变量注入（`IF_*` 前缀），不硬编码；`uvicorn.access` 与 `httpx` 日志已禁用冒泡（防 `?api_key=` query 泄露进 `log_buffer`）。

## 技术栈

- **后端**：Python 3.11+ / FastAPI / uvicorn / httpx / aiosqlite / pydantic-settings / prometheus-client / OpenTelemetry（可选）。版本与依赖以 `pyproject.toml` + `requirements.txt` 为准。
- **前端**：React 19 + TypeScript 5.7 + Vite 6 + react-router-dom 7 + recharts + Vitest 4（管理面板 `frontend/`）；Vue3 + Vite（公开落地页 `landing/`）。脚本见 `frontend/package.json`。
- **外部求解器**：`cf_solver`（Turnstile 求解器，端口 8001），位于 `deploy/cf_solver/`，入口 `boterdrop_wrapper.py`。聊天/生图主链路依赖此服务，缺它部分集成测试会失败。
- **数据层**：SQLite（aiosqlite 异步）—— `data/imagefree.db`（任务/审计）、`data/account_pool.db`（号池）、`data/email_registry.db`（邮箱池）、`data/edit_leases.db`（图生图互斥租约）。

## 结构

```
api/
  main.py            应用组装入口（<300 行，仅挂载路由/中间件/前端/生命周期）
  routes/            health / tasks / generate / admin / chat / ecosystem / security
  dispatch.py        路由调度 + 路由记录全覆盖
  dispatch_edit.py    图生图双层互斥锁
  sse_events.py      每任务 SSE 事件流（subscribe/publish/replay + Last-Event-ID）
  adaptive_router.py MAB-EWMA 路由引擎（成功率/时延/负载打分 + 熔断）
  lifespan.py        9 阶段优雅关闭
  worker/            engine.py 引擎 / token_pool.py Turnstile token 预取池
  account_pool.py    号池（aiosqlite，>1000 行，待拆分）
  email_pool.py      邮箱池 + email_sources/（多临时邮箱源：mailtm/mailgw/tempmail/guerrilla/do22/linshi/temptf/custom_imap）
  providers/         base.py + imagefree/aifreeforever/nanobanana/tryingopen/falai + registry.py + action_sniffer.py
  config/            分组配置包（base/cache/db/edit/http/observability/pool/provider/queue/security/solver/settings.py 兼容命名空间）
  db/                core.py（连接池）/ queries.py / queue_store.py / lease_store.py / ip_blocklist_store.py
  auth.py            聊天端点固定 Key 鉴权（IF_API_KEYS）
  telemetry.py       OTel tail-based 采样（错误 100% + 正常 10%）
  proxy_pool.py      住宅代理 + 免费代理双源轮换
  solver_guard.py    cf_solver 多节点联邦 + 熔断
frontend/src/        pages/（13 页：Dashboard/Tasks/Generate/ChatPlayground/Accounts/Providers/Health/Logs/Security/Slow/DLQ/Costs/Ecosystem）+ api/ barrel + hooks/ + components/
landing/             Vue3 公开落地页 + 隐私声明
deploy/              docker-compose.yml / Dockerfile.api / Dockerfile.cfsolver / .env.example / .env.production.example / cf_solver/
tests/               unit + integration/ + chaos/ + performance/ + conftest.py
docs/                SOP.md / PROVIDER_INTEGRATION_GUIDE.md / verification-log.md / architecture-evolution.md / releases/
scripts/             backup_db.py / restore_db.py / mock_cfsolver.py / e2e_*.py / loadtest.py / final_suite.py
```

## 命令

### 启动

```bash
# 一键启动（Windows，自动拉起 cf_solver + API）
powershell -ExecutionPolicy Bypass -File start.ps1

# 手动分步
python deploy/cf_solver/boterdrop_wrapper.py &       # 终端1：Turnstile 求解器（端口 8001）
uvicorn api.main:app --host 127.0.0.1 --port 8100    # 终端2：API（端口 8100）
```

### 测试（门禁口径见 `pyproject.toml` addopts）

```bash
# 推荐：CI 单测口径（无需 mock cfsolver）
pytest -m "not integration and not chaos and not slow"

# 等价显式目录
pytest tests/ -q -m "not integration and not chaos and not slow"

# 集成测试（须先起 mock cf_solver）
python scripts/mock_cfsolver.py --port 8001 &
pytest tests/integration/ -q

# 慢速/真实网络（默认跳过）
pytest -m slow -q
```

> 注意：CLI `-m` 会**覆盖**（非合并）`pyproject.toml` addopts 的 `-m "not slow"`，故 CLI 需把 `not slow` 一并写进去，不能省。覆盖率门禁由 CI `ci.yml` 的 `--cov-fail-under` 强制，本地跑不默认触发。

### 前端

```bash
cd frontend
npm install
npm run build          # 构建管理面板到 frontend/dist/（由 main.py 挂载到 /admin）
npm run test           # Vitest 单测
npm run test:coverage
```

### Lint / 类型

```bash
ruff check api/ tests/ scripts/        # 0 error 基线（v7.2 已清零 412→0）
ruff format api/ tests/ scripts/
mypy api/errors.py api/retry_policy.py  # 渐进 strict：仅这两个模块 0 error
```

### 部署

```bash
cd deploy
docker compose up -d                  # Docker Compose（推荐）
```

CI 流水线：`.github/workflows/ci.yml`（单测 + 集成 + ruff + sync_deploy 防 deploy/api 漂移）、`deploy.yml`（线上部署）。

## 约定

- **环境变量统一 `IF_` 前缀**：`IF_HOST`/`IF_PORT`/`IF_CF_SOLVER_URL`/`IF_CORS_ORIGINS`/`IF_API_KEYS`/`IF_DB_FILE` 等，全部经 `api/config/` 分组加载；`.env.example`（160+ 项模板）+ `deploy/.env.production.example`（生产收紧：CORS 白名单/独立管理 Key/CSP/限流）。
- **聊天端点鉴权**：`/v1/chat/completions`、`/v1/messages` 受 `IF_API_KEYS` 保护（Bearer / `X-API-Key` / `?api_key=` 三种传法）；生图主链路 `/v1/generate*` 公益开放不受影响。
- **路由引擎**：MAB-EWMA 打分 `Score=(成功率/log10时延)×负载惩罚`，10% 探索率 + 熔断器；`/v1/routing/records` 可查节点评分快照。
- **SSE 事件流**：每任务 `subscribe`/`publish`/`replay`，`Last-Event-ID` 断线补偿；全局广播 `/v1/events/tasks` 向后兼容。
- **大文件治理**：单文件目标 <800 行；`account_pool.py`（1037）/ `email_pool.py`（未拆后端部分）/ `config/` 等仍超线，属已知技术债（见 `workflow_status.md` P2-4）。
- **配置工厂**：`api/config/` 使用 `get_settings()` + 测试钩子 `reset_settings()`；`tests/conftest.py` autouse 复位，避免跨用例污染。
- **日志脱敏**：`mask_key()` 对密钥/token 做掩码；`uvicorn.access` 与 `httpx` logger `propagate=False`，防 query 泄露。
- **DB 批量写**：0.2s 窗口合并 commit；在线热备用 `VACUUM INTO`（见 `scripts/backup_db.py`）。
- **提交格式**：`<type>: <description>`，类型 feat/fix/refactor/docs/test/chore/perf/ci；归属已全局禁用。
- **graf 图谱**：本仓库已被 graft 索引（`graft/`），改动大块代码后跑 `graft build` 刷新；定位代码优先 `graft ask`/`graft callers`/`graft skeleton`，再回退 `rg`/`Read`。

## 边界（需授权 / 默认禁止）

- **生产收紧需授权**：线上 `IF_CORS_ORIGINS=*` 仍开放、`cf_solver` 并发 `page_count` 提升、自建邮箱（CF Workers + 域名）—— 均属 L3 生产灰度/外部资源，未授权不实施（见 `workflow_status.md` P0-1 / P1-2 / P3-1）。
- **真实付费上游调用**：默认预算 0；仅用户明确批准并给预算后才可真实调用，且先本地 Mock 验证 + 最小调用次数。
- **不可逆操作**：`git reset --hard` / `git clean` / force push / amend 用户历史 / 删除真实数据 / 数据库迁移 —— 未经明确指示不执行。
- **scope 约束**：`可参考的项目/`（参考仓库群）与 `landing/node_modules/`、`.venv/`、`graft/` 不属本项目源码，改动不纳入提交。
