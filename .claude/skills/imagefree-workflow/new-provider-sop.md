# 新 Provider 接入 SOP（v7.7 沉淀）

> 适用：往听风AI 网关新增一家上游图像/视频/对话生成提供商。
> 前置阅读：`.claude/skills/imagefree-workflow/SKILL.md` + `imagefree-rules.md`。

## 接入 7 步（每步有验收点）

### 1. Provider 适配器（api/providers/<name>.py）
- 继承 `Provider`（生图）或 `ChatProvider`（对话），实现 `generate`/`chat_collect`/`chat_stream`。
- 构造里注册 `ModelSpec`（capabilities/aspect_ratios/resolutions/credits/account_required）。
- 上游网络调用统一走 `httpx.AsyncClient` + `retry_policy`（指数退避+jitter），不自写重试循环。
- 风控差异化：每 IP 限额 → `needs_proxy_per_request=True`；需账号 → `needs_account=True`。
- **验收**：`pytest tests/test_providers.py::TestProviderGenerate -q -m "not slow"` 全绿。

### 2. Registry 注册（api/providers/registry.py）
- `_PROVIDER_CLASSES` 元组加新类。
- `bootstrap()` 会自动实例化并注册 ModelSpec。
- 若需号池：`account_pool.py` 的 provider 分支加注册/签到逻辑。
- **验收**：`/v1/models` 返回含新提供商分组；`/v1/providers` 看板显示健康状态。

### 3. 配置（api/config/ 分组 + .env.example + .env.production.example）
- 新增 `IF_<NAME>_*` 环境变量进 `api/config/provider.py`（或 `__init__.py` 的 validation_alias）。
- 同步 `deploy/.env.example`（默认值+注释）+ `deploy/.env.production.example`（生产收紧建议）。
- 散落 `os.getenv` 也行但优先入 Settings 模型。
- **验收**：`pytest tests/test_config_validate.py` 全绿；`docker compose exec api env | grep IF_<NAME>`。

### 4. 路由记录（api/dispatch.py）
- `_dispatch_generate` 按 model 前缀路由，新 provider 走 `_PROVIDER_TASKS` 后台直调路径。
- 用 `background.spawn`（api/background.py）持强引用，**禁止裸 `asyncio.create_task`**（GC 风险）。
- priority=0 需 `check_admin_key`；priority 1/2 走信号量 `_provider_sem`。
- **验收**：`/v1/routing/records` 含新 provider 的评分快照。

### 5. 数据层（api/db/）
- 若新 provider 需独立持久化（如号池/路由 DB），走 `aiosqlite` + `db/core.py` 批量写合并（0.2s flush）。
- 列名走 `_PUBLIC_COLS`/`_TASK_LIST_COLS` 白名单，**禁止 f-string 拼接 SQL 值**（用 `?` 参数化）。
- **验收**：`pytest tests/test_db_*.py` 全绿。

### 6. 前端类型（frontend/src/api/providers.ts）
- `ProviderSummary` 加可选字段（如 `credits?`），勿声明为必填（聊天 provider 无此键）。
- 错误信封 `{error:{code,message,details}}` 与 `api/core.ts readErrorBody` 对齐。
- **验收**：`cd frontend && npm run build && npm run test` 全绿。

### 7. 文档 + 发版
- `README.md` 提供商清单表加行；`docs/SOP.md` §1.1 模型数更新。
- 版本 bump 全 8 处（pyproject×2/api.main/frontend/landing/compose×2/README badge）。
- `verification-log` 追加「勿重跑」结论。
- tag `v<版本>` push 触发 Deploy，生产 E2E（`E2E_BASE=... node e2e-smoke.cjs`）。
- **验收**：Deploy 4 job 全绿 + 生产 healthz ok + 新 provider 在 `/v1/models`。

## 红线

- 付费上游零真实调用（用 Mock/fixture 验证参数拼装/轮询/回调/超时/重试/幂等/取消）。
- 密钥仅 `IF_*` 环境变量，不硬编码；日志经 `mask_key`/`_mask_idem_key` 脱敏。
- 同步 I/O（DNS/urllib）必须 `to_thread` 下放，不卡事件循环。
- 装饰 emoji 图标 `aria-hidden`；触控目标 ≥44px；`:focus-visible` 全局环。
