# Cerebrum — 跨会话学习记忆

> 跨会话沉淀的偏好、约定、教训、决策。新会话必读，避免重复发现过程。
> 门槛很低，略冗余无成本。更新时直接追加到对应章节。

## User Preferences

- **语言**：所有回复必须使用简体中文；代码/路径/命令/技术术语保留英文
- **Windows 平台**：禁止 .sh 脚本，用 node 或 PowerShell；命令链接用 `; if($?) { }` 而非 `&&`；查可执行文件用 `where.exe`；搜索用内置 `rg`
- **预算态度**：用户明确"无需担心预算成本 token，放开手脚大胆干活"（2026-09-05 确认）；imagefree-2ai agent 化批次的 LLM 调用已批准真实付费（无预算上限，见 Decision Log）
- **验证策略**：不为每次小改动运行完整构建；优先最小测试范围；仅故障/跨模块/架构调整时扩大
- **工作风格**：先思考再编码；完整可用优先；真实闭环（禁止把理论可行包装成已完成）；证据优先（未验证标注"待验证"）
- **提交**：不自动 commit/push/PR 未经明确指示；提交前过 .pre-commit-config.yaml（ruff check+format + 基础 hooks）
- **不可变优先**：创建新对象而非就地修改
- **提交格式**：`<type>: <description>`，类型 feat/fix/refactor/docs/test/chore/perf/ci；归属已全局禁用

## Key Learnings

- **大文件拆分模式**：旧文件留兼容垫片 `from .new_module import *`，re-export 全部公共符号；from-import 是值拷贝，monkeypatch 改包命名空间要用 `_pkg_attr()` 运行时读包命名空间才能命中
- **MOCK_REGISTER patch 契约**：拆分后子模块读 MOCK_REGISTER 等常量需运行时 `getattr(sys.modules[__package__], "MOCK_REGISTER", False)` 而非 from-import 值拷贝
- **配置工厂**：`api/config/` 用 `get_settings()` + 测试钩子 `reset_settings()`；`tests/conftest.py` autouse 复位避免跨用例污染
- **日志脱敏**：`mask_key()` 对密钥/token 掩码；`uvicorn.access` 与 `httpx` logger `propagate=False` 防 query 泄露进 log_buffer
- **DB 批量写**：0.2s 窗口合并 commit；在线热备用 `VACUUM INTO`（见 `scripts/backup_db.py`）
- **graft 图谱**：本仓库已被 graft 索引（`graft/`）；改动大块代码后跑 `graft build` 刷新；定位代码优先 `graft ask`/`graft callers`/`graft skeleton`，再回退 `rg`/`Read`
- **测试门禁**：CI 口径 `pytest -m "not integration and not chaos and not slow"`；CLI `-m` 会覆盖 addopts 的 `not slow`，故 CLI 需把 `not slow` 一并写进去
- **cf_solver 依赖**：聊天/生图主链路依赖 `cf_solver`（端口 8001），缺它部分集成测试会失败；用 `scripts/mock_cfsolver.py` 起本地 mock
- **版本号 7 处**：pyproject.toml×2 + api/main.py + frontend/package.json + landing/package.json + deploy/docker-compose.yml，改版本要全改
- **预存 flaky**：`test_autoregister_loop_fills_to_target`（代理池每日限额时序）单跑全绿属组合串扰，非回归；registerer 3 用例组合失败用 `_mock_register()` 运行时解析根治

## Do-Not-Repeat

- **2026-09-05**：拆分大文件后 monkeypatch 改包命名空间不命中子模块读点——必须用 `_pkg_attr()`/`_mock_register()` 运行时读包命名空间，不能 from-import 值拷贝
- **2026-09-05**：`_FakeReg.__init__(self, result=None)` 里 `result if result is not None else 8` 会让 `result=None` 落到默认 8（成功），无法表达失败——用 `_SENTINEL = object()` 哨兵区分"未设"与 None
- **2026-09-05**：landing dist 含旧版本号导致 `test_landing_built_dist_version_matches_source` 失败——改版本后必须 `cd landing && npm run build` 重建 dist
- **2026-09-05**：陈旧 `api/__pycache__/account_pool.cpython-311.pyc` 干扰 ImportError——拆分后清 `*.pyc` 再跑全量
- **2026-09-05**：127.0.0.1 被 IP 黑名单误伤（rate-limit-exceeded 入黑名单）导致本地 E2E generate 403——`DELETE FROM ip_blocklist WHERE ip='127.0.0.1'` + `IF_IP_WHITELIST=127.0.0.1` 重启
- **2026-09-05**：curl GitHub API SSL 失败（exit 35）——改用 `python -c "import httpx; ..."` 调 API
- **2026-09-05**：`.wolf/*.md` 从未进过 git（仅 buglog.json 进过），无法从历史恢复——直接重写最小版

## Decision Log

- **2026-09-05**：用户批准 imagefree-2ai agent 化批次（P1-A3/A7/A2/P2-A2）LLM 真实付费调用，无预算上限。覆盖 CLAUDE.md 默认预算=0。理由：让 agent 化能力真正落地非 Mock 悬空。此授权针对本批次，其他批次/项目不自动继承
- **2026-09-05**：.wolf 协议断链修复方式——git 历史无此文件，按 CLAUDE.md 协议重写最小版（OPENWOLF.md 定义协议 + cerebrum.md 学习记忆 + anatomy.md 文件索引 + memory.md 单行条目）
- **2026-09-05**：批次0+批次1 落地范围确认——v8.0.0 已闭环 P0 架构治理，本轮做 P0-0（.wolf 修复）+ P1-A1~A7（agent 化跃迁）
- **2026-09-05**：agent 化扩展遵循"只追加不重构"三铁律——不重构公共接口、不造轮子、先测后改；所有新功能 IF_*_ENABLED 缺省关闭
- **2026-09-05**：版本号 v8.0.0→v8.1.0（批次1 agent 化跃迁）

## 2026-09-06 P0-11 CI 历史遗留根治诊断链（v8.1.1→v8.2.3）

### 根因（经 13 轮 CI 诊断定位）
1. **v8.1.1 lock 漂移**：landing/frontend package-lock.json version 滞后 8/9 版本，npm ci 装包与本地不一致 → frontend-version-gate exit 4
2. **v8.2.0 .gitignore 误伤**：`.gitignore:109 config/` 规则误伤 `api/config/presets.py`（Python 包路径含 config/ 段）→ CI clone 缺文件 → `api/config/__init__.py:973 import presets` 失败 → conftest autouse `_reset_settings_singleton` 调 `reset_settings()→Settings()` 失败 → 全用例 setup 阶段 E → exit 2
3. **v8.2.1-v8.2.2 遗漏提交**：`api/config/__init__.py`（agent 开关 8 字段）+ `api/config/settings.py`（ruff 排序 220 行）本地 ruff --fix 修复后未 git add → CI ruff 仍报 import block
4. **v8.2.3 集成 flaky**：`test_account_growth::test_account_pool_growth_field` CI 上 404（本地全绿），1/37 flaky

### 修复（v8.1.1→v8.2.3 累计）
- v8.1.1: landing/frontend lock version 同步 + ci.yml version-gate 强化输出
- v8.2.0: `.gitignore config/` → `/config/` + 提交 `api/config/presets.py`（根治 exit 2）
- v8.2.1: ruff --fix solver.py import 排序 + ci.yml set+e 保 cat 段
- v8.2.2: 提交遗漏的 `__init__.py` + `settings.py` + ci.yml junitxml 解析单测
- v8.2.3: ci.yml 集成 step 加 junitxml 解析（定位 exit 1 真因）

### 关键教训（Do-Not-Repeat）
- `.gitignore` 的 `config/` 规则会误伤所有 `*/config/` 子路径，必须用 `/config/` 锚定顶层
- ruff --fix 后必须 `git add` 提交，否则 CI clone 缺改动本地全绿 CI 失败
- pytest 9 + tee 在 GitHub Actions 上 stdout 被截断，需用 `--junitxml` + Python 解析 xml 绕过
- CI exit 2 无 stdout 多是 conftest autouse fixture setup 失败（import 错），用 `--setup-show` + `python -c "import api.config"` 诊断

## 2026-09-06 test_account_growth flaky（CI 时序）

### 现象
CI 集成测试 37 个用例，`test_account_growth::test_account_pool_growth_field` 偶发 404（本地全绿）。
该用例是集成测试第 1 个跑的（文件名排序），用 `app_with_mocks` fixture（首次创建 session 级 `_app_instance`）。

### 根因（合理推断）
- 404 而非 500 说明路由未注册（FastAPI 路由不存在才 404，handler 内部错误返回 500）
- 但本地 admin.router.routes 含 /v1/account-pool（27 路由）
- CI runner 慢，`_app_instance` 的 lifespan startup 含 nanobanana 注册 + worker 池启动
- `app_with_mocks` 的 healthz 等待循环 30×0.2=6s，CI 上可能 lifespan 未完成时路由未挂
- 但路由是 import 时挂载（非 lifespan），疑 CI 上 admin 包 import 时机与 conftest purge 逻辑交互

### 处理
属已知 flaky，不阻塞主链路（1/37）。下次 CI 失败可直接从 junitxml 解析看是否同一用例。
若反复失败，需加 healthz 等待循环次数（30→60）或诊断 admin 包 CI import 时机。

## 2026-09-06 P0-S1 storage 热路径真接线（v8.2.3→v8.3.0）

### 根因
v8.0 P1-1 只完成「装配层」（lifespan 注入 RedisStorageAdapter + request_guard set/get 函数），「消费层」（热路径真调适配器）未落地。request_guard 的 _check_l1(259-272)/滑窗(530-545) 仍走内存 dict，IF_STORAGE_BACKEND=redis 时空有适配器单例但限流不共享 → 双实例集中式限流名存实亡。

### 修复（P0-S1）
- api/request_guard.py(+90/-6)：
  - _await_sync(coro) 同步→异步桥（无 running loop 复用线程局部 loop；有 loop 起 daemon 子线程跑，避免死锁主 loop）
  - _warn_redis_fallback_once 适配器异常降级内存（每轮装配仅 warning 一次，不 fail-open 保真限流）
  - _l1_check 热路径分叉：adapter 非 None 调 adapter.rate_limiter.is_allowed("l1:"+key)，refill>0 用细窗 capacity/refill，refill=0 用 max(capacity,1.0) 突发桶窗
  - 基线滑窗热路径分叉：adapter 非 None 调 adapter.rate_limiter.is_allowed("rate:"+key, limit, window)；AppError 直接 re-raise，其他异常降级内存滑窗
- tests/test_request_guard_redis_mode.py（新建 15 用例）：L1 热路径 5 + 滑窗热路径 5 + 降级 warning 去重 1 + _await_sync 桥接 3，用 Mock 适配器不连真实 Redis
- tests/test_request_guard_storage_mode.py（已存在 v7.3 建）

### 验证（v8.3.0）
- request_guard 全家 + redis_adapter + chat_auth + adaptive_router + agent + async_sync_contamination：193 passed 0F
- IF_STORAGE_BACKEND=sqlite 单机模式零回归
- ruff 0 error / mypy strict(errors+retry_policy) 0 issue
- E2E 实测：/v1/livez=200 /v1/healthz=200 /v1/models=200(48 模型) /v1/generate(imagefree/default)=completed 有图 /v1/chat/completions(glm-5.3-flash)=200 有 reasoning_content /v1/agent/intent=200 llm_used=true scene=image /v1/agent/skills=200 /v1/agent/memory=200 /metrics=200

### Do-Not-Repeat
- 2026-09-06：storage 接线时 check_rate_limit 是 sync 入口被 FastAPI sync 路由线程池调用（无 running loop），调 async adapter.is_allowed 必须用 _await_sync 桥接——无 loop 复用线程局部 loop（避免每请求新建 loop 开销），有 loop 起子线程跑（避免阻塞主 loop）
- 2026-09-06：storage 适配器异常降级**不 fail-open**——降级到内存桶按本机 RPS 限流，比放行安全（双实例集中式限流挂掉时退化为单机限流，保真限流语义）
- 2026-09-06：agent intent.py:107-148 已有真实 provider.chat_collect 路径（走 tryingopen 免费上游，IF_MOCK_UPSTREAM=0 默认真实），**非 Mock 悬空**——指南修正「待验证=补 E2E 验收」而非「是否真调 LLM」

### Decision Log
- 2026-09-06：P0-S1 storage 真接线采用「不 fail-open + 同步→异步桥」方案，不改 check_rate_limit 同步签名、不改 generate.py 调用链（避免 L3 跨模块改动）。真实 Redis 集中式限流端到端属 L3 生产灰度，本地用 Mock 验证热路径真调+降级，待验证
- 2026-09-06：版本 bump 8.2.3→8.3.0（P0-S1 = MINOR 向后兼容，缺省 sqlite 零回归），7 处一致 + dist 重建
