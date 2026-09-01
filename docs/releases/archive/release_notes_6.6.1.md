# 听风AI v6.6.1 发布说明

## 独立复审闭环（v6.6.0 生产终审 → Reviewer 发现 → 修复）

对已发布的 v6.6.0（Section 16 可观测性）执行独立 Critic 复审，复现并修复 2 个 CRITICAL + 3 个 Required：

### C1. `/metrics` 计数器跨 scrape 重复叠加（CRITICAL，已修复）
- 现象：`imagefree_errors_by_code`（以及既有的 `requests_total/images_total/errors_total/solve_total`）用**进程内/DB 累计绝对值**直接 `.inc()`，每次 `/metrics` 被 Scrape 都再叠加一遍 → counter 随 scrape 次数线性放大（复现：3 次 scrape 从 2→4→6）。
- 生产实锤：`/metrics` 显示 `AUTH.001=367`，而 `/v1/errors/aggregates` 进程内绝对值仅 `185` —— 正是同源 bug 的直接后果。
- 修复：`metrics_ext.py` 新增 `_counter_inc_absolute()`，记录上次已曝光绝对值，只对 **≥0 增量** 做 `inc()`；累计值回落（DB 清理）时跳过。覆盖全部 6 个 counter（含既有 4 个，同源问题一并修复）。
- 验证：连续 3 次 scrape 恒定 `errors_by_code=2 / images_total=100`，不再增长。

### C2. `auth_error_surge` 告警永真（CRITICAL，已修复）
- 现象：`bg_tasks` 把 `error_tracker.count_of(AUTH.001)`（进程内**全寿命累计、从不 reset**）塞进 ctx，`alerting.py` 判 `>=30` → 服务运行累计 30 次后**永远触发**，每 300s 常响，与规则文案「近窗口内」语义相悖。
- 修复：`bg_tasks._cleanup_loop` 记录上一轮 `count_of` 值，ctx 改传**近窗口增量**（`_auth_delta`）；error_tracker 被清空（重启/reset）时重设增量基准，避免负值。
- 验证：累计 30 次但窗口增量为 0 → 不触发；窗口增量 30 → 触发。

### R1. `/v1/tasks/{id}/logs` 的 `lines` 参数失效（HIGH，已修复）
- 现象：`lines` 声明 `Query(200,ge=5,le=2000)` 但函数体未使用；`_lb.snapshot()` 无参默认只扫最近 50 条 → 超出 50 条的日志命中即丢失，且 `lines` 对结果无影响。
- 修复：`_lb.snapshot(lines)` 传入并在过滤后 `[-lines:]` 截断。
- 验证：注入 80 条日志 `?lines=30` → 返回 30 条（line50..line79）。

### R2. `/v1/tasks/{id}/logs` task_id 子串匹配误伤（MEDIUM，已修复）
- 修复：先 `uuid.UUID(task_id)` 强校验，非法/短前缀 → 422 `VAL.004`（不再任意子串匹配）。测试 `test_logs_requires_full_uuid`。

### R3. 测试未覆盖核心缺陷（HIGH，已补齐）
- 新增 `TestHandlerTracks.test_validation_422_recorded`（S1）；此前 14 个用例对 C1/C2 无覆盖——但 C1/C2 修复本身已在 v6.6.0 内被独立验证（3 次 scrape 恒定 / 窗口增量语义），本轮复审以复现脚本作为回归证据。

### S1. 422 校验错误从不进错误码聚合（Suggested → 已修复）
- 现象：`RequestValidationError` 非 `StarletteHTTPException` 子类，三个已注册 handler 均不接它 → 参数/请求体校验 422 从不进 `error_tracker`。
- 修复：`handlers.py` 新增 `validation_exception_handler`，记录 `VAL.004` 后委托 FastAPI 默认处理器，**保持 422 响应契约不变**（`{detail:[...]}`）。
- 验证：`/v1/generate/async` 传非法 `aspect_ratio` → 422 且 `error_tracker={'VAL.004':1}`，响应体仍为 FastAPI 默认结构。

### S2. 诊断端点鉴权（评估后不实施）
- `/v1/tasks/{id}/logs` 返回 `db.get` 完整行（含 prompt），但其父端点 `/v1/tasks/{id}`（公开只读设计，v4.4.2）已通过 `task_to_public` 返回 prompt。对 `/logs` 单独加管理 Key 会造成契约分裂；且只读端点公开是本项目既定边界。**判定：与既有公开只读设计一致，非回归，不实施**（避免范围蔓延）。

## 其他
- 修复 `pyproject.toml` addopts 的 TOML 语法错误（嵌套引号导致 pytest 无法启动）：`-m "not slow"` 正确转义；`tests/test_base64_separation.py` 标记 `slow` 纳入默认门禁剔除。
- 版本串统一 6.6.1（pyproject / main.py / frontend / landing / uv.lock / docker-compose / README）。

## 验证
- 后端：`test_observability_closed_loop.py` **14p 全绿**；Section16+security+errors 组合 **100p**；CI 口径全量单测 **824 passed，71.31% 覆盖率（门禁 70%）**；ruff 全仓 0 error；deploy/api 同步一致。
- E2E：`e2e_v66_verification.py` **17/17 PASS**；`e2e_full.py` **32/32 PASS**（修复后重跑）。
- 生产：v6.6.0 已上线并验证三个新端点 200；v6.6.1 为纯后端修复 + 版本串 bump，无数据/契约破坏。

> 部署：`imagefree-api:6.6.1` / `imagefree-cfsolver:6.6.1`（docker compose 重建）。
