# imagefree_api 代码规范

> 与 `skills/imagefree-workflow/SKILL.md` 配套。适用于本仓库所有后端（api/）、前端（frontend/src/）与测试（tests/）代码。

## 1. 代码规范

### 通用

- **不可变性（关键）**：始终创建新对象，绝不就地修改现有对象。配置对象、任务信息等只读数据尤其如此。
- **KISS / DRY / YAGNI**：最简单可用方案优先；真实重复才抽公共函数；不做推测性抽象。
- **文件组织**：多小文件优于少大文件。文件 ≤800 行，函数 <50 行，嵌套 ≤4 层（用提前 return）。
- **绝对路径导入**：后端模块间用 `from api.xxx import yyy`；避免相对导入依赖当前目录。
- **类型标注**：公共函数/类必须有完整类型标注（Python 3.11 语法：`dict | None`、`tuple[int, ...]`）。
- **配置文件集中**：所有可配置项进 `api/config.py`（`IF_*` 环境变量），不散落硬编码。新配置必须同步 `.env.example`。

### Python 后端

- 异步优先：IO 密集用 `async def` / `asyncio`；全局单例（engine、db、settings）模块级实例化，运行时 `await xxx.start()`。
- SQLite 写统一走 `api/db.py` 的批量写合并（`DB._enqueue_write` + 0.2s flush），不要直接裸 `sqlite3` 高频 commit。
- 上游网络调用统一走 `httpx`，超时与重试用 `retry_policy.py`（指数退避 + jitter），不自己手写重试循环。
- 并发控制用 `semaphore_manager.py` / `asyncio.Lock`，不在业务代码里散落裸锁。

### 前端（React + TS）

- 组件按 `frontend/src/pages/`（页面）与 `components/`（复用 UI）划分；数据请求集中在 `api.ts`，不在组件内散落 fetch。
- 组件命名 `PascalCase`，钩子 `use` 前缀 camelCase，常量 `UPPER_SNAKE_CASE`，CSS class 用 kebab-case。
- 状态管理保持最小：服务端状态只做请求缓存，派生值不冗余存储。

## 2. 命名约定

| 场景 | 约定 | 示例 |
|------|------|------|
| 文件/模块 | `snake_case.py` | `free_proxy_fetcher.py` |
| 类 | `PascalCase` | `SolverGuard`、`TokenPoolManager` |
| 函数/变量 | 动词+名词 camelCase | `mark_finished`、`acquire_proxy` |
| 异步函数 | `async def` + 同步语义命名 | `async def submit(...)` |
| 布尔 | `is/has/should/can` 前缀 | `is_edit_slot_wedged` |
| 配置分组 | `Settings` 子类 + `IF_` 前缀字段 | `IF_GENERATE_TIMEOUT` |
| Provider | `<name>.py` + `class <Name>Provider` | `api/providers/nanobanana.py` |
| 测试文件 | `test_<被测模块>.py` | `test_worker_auto_scale.py` |
| 错误码 | `CATEGORY.NNN` 大写 | `PROV.002` |
| 内部函数 | 下划线前缀（不跨模块复用） | `_flush_db`、`_prune_expired` |

## 3. 错误处理模式

### 统一错误码体系（api/errors.py）

- 分层格式 `CATEGORY.NNN`：`AUTH`（认证）、`VAL`（参数校验）、`PROV`（提供商/上游）、`SYS`（系统内部）、`RATE`（限流/配额）。
- 端口层不直接抛裸 `HTTPException`，除非是标准化的 StarletteHTTPException。

```python
# 业务内 raise
raise AppError(ErrorCodes.QUEUE_FULL, "队列已满，请稍后重试", status_code=429)

# handler 内返回
return error_response(ErrorCodes.INVALID_MODEL, "模型不存在", status_code=422)

# 多语言（zh/en）动态参数
msg = get_error_message(ErrorCodes.QUEUE_FULL, lang="zh", timeout=60)
```

错误码常量定义在 `api/errors.py` 的 `ErrorCodes`；新增错误码必须在这里注册，不进 `SYS.001` 兜底。

### 提供商错误

`api/providers/base.py` 定义 `ProviderError`（上游不可用）和 `ProviderRateLimited`（限流），worker 依据异常类型决定 **重试/降级/熔断**：
- `ProviderRateLimited` → 计入限流，触发代理轮换或降级到备选 provider；
- 连续求解失败 → `solver_guard.py` 熔断（circuit open）→ 暂停 token 预取，超时后自动半开恢复。
- 未知异常必须 `logger.exception(...)` 保留堆栈，不得 `except Exception: pass`。

### 通用原则

- 每一层显式处理错误；不静默吞错；UI 层给用户友好中文消息，服务端日志记详细上下文。
- 外部输入必须在边界校验（`_validate_model` / `_validate_ratio` / `_parse_input_image`），快速失败并返回结构化错误。
- 超时/取消类路径（worker 硬超时、edit 槽位 wedged）走专用兜底标记，不让任务卡死队列。

## 4. 测试要求

- **覆盖率门槛 70%（CI 强制）**：CI 中 `--cov=api --cov-fail-under=70`。新代码块尽量覆盖；核心路径（校验、入队、重试、错误码）优先。
- **TDD**：先写测试（RED）→ 最小实现（GREEN）→ 重构（IMPROVE）。
- **测试结构 AAA**：Arrange → Act → Assert；命名用行为描述（`test_returns_empty_when_no_match`）。
- **异步测试**：pyproject 已配 `asyncio_mode = auto`，测试函数直接 `async def test_...` 即可，无需手动 `asyncio.run`。
- **测试分类**：
  - 单元测试 → `tests/test_*.py`（顶层，300+ 用例）
  - 集成测试 → `tests/integration/`（全流程/熔断/DLQ/编辑/限流/超时）
  - 故障注入 → `tests/chaos/`（`@pytest.mark.chaos`）
  - 压测 → `tests/performance/`（`@pytest.mark.benchmark`）
- **外部依赖**：涉及上游/网络/cf_solver 的测试用 mock 或 pytest monkeypatch；`scripts/e2e_validate.py --mode mock` 可做零消耗端到端。
- 新增功能必须配套测试；改 bug 先写复现用例再修。