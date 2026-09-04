# 004-final-audit-v76 Tasks — v7.6 审计闭环

## Phase 1: 后端 P0/P1 修复

- [x] 1.1 幂等 TOCTOU 根治：db/core.py save_idempotency 改原子 upsert（ON CONFLICT DO NOTHING + rowcount 检查），dispatch.py 用原子接口；并发单测
  - **Depends on**: 无
  - **Requirement**: FR-1, AC-1
- [x] 1.2 lifespan shutdown drain `_PROVIDER_TASKS`（③ 与 ⑨ 之间，timeout 5s）；单测
  - **Depends on**: 无
  - **Requirement**: FR-2, AC-2
- [x] 1.3 chat.py `_chat_collect` 补 `except ProviderRateLimited → 429`；测试
  - **Depends on**: 无
  - **Requirement**: FR-7, AC-7
- [x] 1.4 dispatch.py priority=0 需 admin key（guard 传入 raw_request）；测试
  - **Depends on**: 无
  - **Requirement**: FR-8, AC-8

## Phase 2: 前端 P1 修复

- [x] 2.1 Logs.tsx ping 裸串 + heartbeat 移 onmessage；后端 pong 已有；测试
  - **Depends on**: 无
  - **Requirement**: FR-3, AC-3
- [x] 2.2 misc.ts fetchLogs adminHeaders + LogEntry timestamp:string
  - **Depends on**: 无
  - **Requirement**: FR-4, AC-4
- [x] 2.3 Dashboard.tsx adminKey 用 getStoredAdminKey
  - **Depends on**: 无
  - **Requirement**: FR-5, AC-5
- [x] 2.4 Security.tsx page 变化触发 reload（useEffect）
  - **Depends on**: 无
  - **Requirement**: FR-6, AC-6

## Phase 3: 部署/工程一致性

- [x] 3.1 deploy/pyproject.toml version 6.7.0→7.2.0
  - **Depends on**: 无
  - **Requirement**: FR-9, AC-9
- [x] 3.2 cov-fail-under 统一 80（deploy.yml 70→80）
  - **Depends on**: 无
  - **Requirement**: FR-9, AC-9
- [x] 3.3 IF_REQUESTS_PER_MINUTE 默认对齐（compose 30→20 与 production 模板一致）
  - **Depends on**: 无
  - **Requirement**: FR-9, AC-9
- [x] 3.4 README cf_solver 路径修正 + sync_deploy no-op step 删除
  - **Depends on**: 无
  - **Requirement**: FR-9, AC-9

## Phase 4: 全量验证 + 审查循环

- [x] 4.1 后端定向测试 + 前端 vitest 全量 + tsc + ruff
  - **Depends on**: Phase 1-3
  - **Requirement**: AC-10
- [x] 4.2 独立审查线程六维审查（critical-code-reviewer 协议）→ 修复清单 → 主线程修复 → 复验循环
  - **Depends on**: 4.1
  - **Requirement**: 全部 AC
- [x] 4.3 文档同步：verification-log「勿重跑」结论、workflow_status 终态、HTML 报告+测验
  - **Depends on**: 4.2
  - **Requirement**: FR-11, FR-12, AC-11, AC-12
