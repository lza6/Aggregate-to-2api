# 听风AI v6.7.0 发布说明

## 概述

v6.7.0 在 M4 前端体验升级（D1–D5）基础上，一并落地 v6.6.1 遗留的两项 P3 收尾（/admin 边界说明、OpenAPI↔前端契约测试），并新增「安全风控」管理页、给 DLQ 写端点补管理 Key 鉴权，完整闭环 P3-1/P3-2 与 Critic 复审 3 个 HIGH。

## M4 · 前端体验升级（D1–D5）

- **D1 动作化错误提示**：429 切备用 provider / 401 curl 一键复制 / 502 备用列表（`Feedback.tsx` 重构）。
- **D2 ChatPlayground 会话化**：localStorage 持久化（密钥不落盘）+ usage 成本展示。
- **D3 移动端/a11y**：Layout 抽屉式侧栏 + aria-label/aria-expanded + focus-visible + 320/768/1440 无溢出。
- **D4 落地页扩展**：SectionFaq（FAQ+curl）+ SectionChangelog（healthz+release notes）。
- **D5 前端遥测**：`telemetry.ts`（onerror/unhandledrejection 上报）+ POST/GET `/v1/errors/frontend`（公开，与 P0-P1 聚合隔离）。

## P3-1 · /admin 公开/受保护边界说明

- `Layout.tsx` 顶栏 `boundary-pill`「公开只读 · 写操作需管理 Key」，hover/title 展示完整边界；移动端 ≤860px 自动隐藏。
- 危险操作（DLQ 清空）改 prompt 输入 CLEAR 二次确认，防误触。
- 不引入登录体系：公开只读展示，写操作（封禁/解封、DLQ 重试/清空）需 `IF_ADMIN_KEYS` 管理 Key。

## P3-2 · OpenAPI↔前端契约测试

- `tests/test_openapi_contract.py`：schema paths 存在性 + TaskInfo 字段稳定 + 真实响应字段 + 写操作鉴权契约（无管理 Key → 401/403）+ 安全风控响应字段契约（`expire_at`）。
- 字段漂移即红，强制前端同步；不引入 openapi-typescript。

## 安全风控管理页（Security）

- `/security` 路由 + `SecurityPage`：封禁（block/daily_limit）/解封/列表/单 IP 状态。
- 管理 Key 仅存 localStorage，仅写操作附 `Authorization`；只读端点不携带。
- 后端 `/v1/admin/security/*` 已有鉴权，本轮前端补齐对接。

## DLQ 写端点管理 Key 鉴权 + Critic 复审修复

- `admin.py` `retry_dlq_task`/`clear_dlq` 补 `check_admin_key(scope="admin-dlq")`。
- H1 修复：`BlockRule.expires_at`→`expire_at` 对齐后端 `ip_blocklist_store`。
- H2 修复：`block_ip` 全量封禁不再校验 `daily_limit>=1`（block 类型忽略该字段）。
- H3 修复：`retryDLQTask`/`clearDLQ` 补 `!res.ok` 抛错，失败如实报错。

## 版本统一 6.7.0

`pyproject.toml` / `api/main.py` / `deploy/api/main.py` / `frontend/package.json` / `landing/package.json` / `deploy/docker-compose.yml`（注释+2 镜像 tag）/ `uv.lock` / `README badge`。`scripts/sync_deploy.py` FILES 补 `slo_budget.py`，确保 deploy 副本与根 api 完全一致。

## 验收（真实运行）

- 契约测试 `pytest tests/test_openapi_contract.py` → **14 passed**。
- 关键单测：`test_account_pool`(23)/`test_chat_auth`+`test_auth_ip`(21)/`test_db_security`(10)/`test_ip_blocklist`(22) 全绿。
- 真实 E2E `scripts/e2e_v67_verification.py` → **16/16 PASS**（/admin boundary 文案 + /security chunk + DLQ/security 鉴权 401→200 + meta 脱敏 + OpenAPI 新增端点）。
- 前端 `tsc --noEmit` 0 error；`vite build` exit0；`landing build` exit0。
- 同步 `sync_deploy.py check` → OK api/ 与 deploy/api/ 完全一致。
- ruff `check api/` → All checks passed!（admin.py E701 拆行 + `[tool.ruff] target-version="py311"` 消除 F821 误报）。

## 兼容性

- DLQ/封禁写端点新增鉴权：已配置 `IF_ADMIN_KEYS` 的部署无感；未配置且非开放模式从「裸奔」变默认拒绝（安全加固，非破坏）。
- 前端新增 `/security` 路由与 `boundary-pill`，纯增量。
- 无 schema/契约变更，无数据破坏风险。
