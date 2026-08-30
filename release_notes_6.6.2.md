# 听风AI v6.6.2 发布说明

## 概述

v6.6.2 是 v6.6.1 之后的**收尾型维护版本**，聚焦两件来自复审清单的 P3 项闭环：
① README 测试命令与默认门禁口径同步；② 线上 Key 脱敏行为复核。同时统一版本串至 6.6.2（外部曾误置 6.7.0/6.6.1 混用），并修复 deploy/api 与 api/ 的代码漂移。

## 修复与变更

### P3-7 · README 测试命令与门禁口径同步
- **问题**：README「🧪 测试」仅写 `pytest tests/ -q`，未说明默认门禁 `-m "not slow"`、CI 口径、slow 标记语义，新开发者照抄会跑进需 mock cf_solver 的 integration/chaos 用例而失败。
- **修复**：README 测试章节重写，给出 5 条分层命令 + 门禁口径说明（`-m` 覆盖而非合并 `addopts` 的 `-m "not slow"`、integration/chaos 需先启 mock cfsolver），并指向 `.github/workflows/ci.yml` 作为权威 CI 口径。
- **验证**：默认 `pytest -q` 与 README 第 1 条 CI 单测口径行为一致（`addopts` 内置 `-m "not slow"` 实测有效）；`pytest --collect-only` 收集到全部用例。

### P3-9 · 线上复核 P0-1 修复行为（Key 脱敏）
- **目标**：复核 v6.6.0/v6.6.1 的 P0-1「公开端点不泄露完整 API Key」在线上确已生效。
- **线上实锤**（匿名 curl `https://imagefree.tingfengai.art`）：
  - `GET /v1/meta` → `{"auth_enabled":true,"api_key_mask":"sk-tfai-1248***"}`，**无完整 key**。✅
  - `GET /v1/chat/auth/status` → `{"enabled":true,"admin_enabled":true,"key_mask":"sk-tfai-1248***","key":"",...}`，匿名 `key` 字段为空。✅
- **结论**：P0-1 修复行为在线上已确认，匿名响应不泄露完整 key，仅 `*_mask` + `enabled`；完整 key 仅在携带管理 Key（`check_admin_key` 通过）时由 `/v1/chat/auth/status` 返回，供站长一键复制。

### 版本串统一至 6.6.2
- 背景：仓库曾出现 6.6.1 / 6.7.0 / 6.6.2 混用（`pyproject.toml` 6.7.0、`deploy/pyproject.toml` 6.6.1、`uv.lock` 6.6.2、README badge 6.6.2）。
- 统一为 6.6.2：`pyproject.toml`、`deploy/pyproject.toml`、`api/main.py`、`deploy/api/main.py`、`deploy/docker-compose.yml`（3 处镜像 tag + 注释）、`frontend/package.json`、`landing/package.json`、`README.md` badge、`uv.lock`。
- 说明：源码注释中以 `v6.7.0` 标注的特性文档（`api/routes/admin.py` 管理面 Key 鉴权、`api/request_guard.py` 三层限流）属历史特性命名，非版本号，保持不动以免误改特性追溯链。

### deploy/api 代码漂移修复
- `sync_deploy.py check` 曾报 4 文件漂移（`error_tracker.py`、`routes/admin.py`、`db/core.py`、`worker/engine.py`）。
- 根因：根 `api/worker/engine.py` 较 deploy 副本新增 B2「worker 后台协程 contextvars 恢复」特性，其余三文件为历史同步滞后。
- 修复：`scripts/sync_deploy.py sync` 拉齐 deploy/api 与根 api 完全一致；`check` 复跑 `OK api/ 与 deploy/api/ 完全一致`。
- 验证：`ruff check api/` 全仓 0 error；`sync_deploy.py check` 通过。

## 验证

- **lint**：`ruff check api/ --no-fix` → All checks passed!（0 error）。
- **同步**：`python scripts/sync_deploy.py check` → OK api/ 与 deploy/api/ 完全一致。
- **版本串**：全仓扫描 `6.7.0` 仅余特性注释（admin.py / request_guard.py），非版本位；版本位统一 6.6.2。
- **线上 Key 脱敏**：见 P3-9，匿名 `/v1/meta`、`/v1/chat/auth/status` 均不泄露完整 key。

## 兼容性

- 纯文档 + 版本串 + deploy 副本同步，**无接口/数据/契约变更**，无数据破坏风险。
- 部署：`imagefree-api:6.6.2` / `imagefree-cfsolver:6.6.2`（docker compose 重建）。

## 关联

- v6.6.0 独立复审闭环（C1/C2/R1/R2/S1）见 `release_notes_6.6.1.md`。
- 本版承接 v6.6.1，仅补 P3 收尾与版本串统一。
