# 005-v77-terminal-closure Tasks

## Phase 1: 审计（并行子代理）

- [x] 1.1 [P] 契约审计（contract-auditor）——FE types ↔ BE routes 逐字段
  - **Depends on**: 无 | **Requirement**: FR-A1
- [x] 1.2 [P] 后端安全健壮性审计（backend-auditor）
  - **Depends on**: 无 | **Requirement**: FR-A2
- [x] 1.3 [P] UX 闭环审计（ux-closure-auditor）
  - **Depends on**: 无 | **Requirement**: FR-A3
- [x] 1.4 [P] 配置/部署/文档一致性审计（config-docs-auditor）
  - **Depends on**: 无 | **Requirement**: FR-A4

## Phase 2: 修复（主线程，按审计清单）

- [x] 2.1 契约修复（Task 类型补全 + 错名字段对齐 7 项 + /v1/tasks prompt 列）
  - **Depends on**: 1.1 | **Requirement**: FR-B1, AC-1
- [x] 2.2 后端修复（geo_ip/background.spawn/流式 429/log_ws/DNS/幂等 key 脱敏/fd/ecosystem）
  - **Depends on**: 1.2 | **Requirement**: FR-B2, AC-2
- [x] 2.3 前端修复（Tasks 筛选/Security 死锁/App 404/Generate 双失败/ChatPlayground/Accounts 防抖/Gallery 错误态/无障碍 P2）
  - **Depends on**: 1.3 | **Requirement**: FR-B3, AC-3
- [x] 2.4 CI frontend 门禁 job + 集成分轮 + conftest admin key 清理
  - **Depends on**: 1.4 | **Requirement**: FR-B4, AC-4
- [x] 2.5 文档同步（README 前端章节 + SOP v2.4.0 + .env.production.example + verification-log）
  - **Depends on**: 1.4, 2.1-2.3 | **Requirement**: FR-B5, AC-5

## Phase 3: 全量验证

- [x] 3.1 后端 CI 口径全量（1545 用例，1F 组合串扰单跑 PASS）
  - **Depends on**: Phase 2 | **Requirement**: AC-2
- [x] 3.2 前端 vitest + tsc + build + 双 E2E（本地）
  - **Depends on**: Phase 2 | **Requirement**: AC-3
- [x] 3.3 CI 门禁本地模拟（frontend-gate 三步全绿）
  - **Depends on**: 2.4 | **Requirement**: AC-4

## Phase 4: 审查循环（≤3 轮）

- [x] 4.1 独立审查线程六维审查（4 子代理即为审查线程，已交回报告）
  - **Depends on**: Phase 3 | **Requirement**: FR-D1, FR-D2, AC-6
- [x] 4.2 主线程修复 → 复验收敛（5F 全部预存/组合串扰，本轮零回归）
  - **Depends on**: 4.1 | **Requirement**: AC-6

## Phase 5: 资产沉淀与交付

- [ ] 5.1 skills 沉淀：《新 Provider 接入 SOP》《新功能接入 SOP》+ SKILL.md 索引 + MEMORY.md 更新
  - **Depends on**: 4.2 | **Requirement**: FR-C4, AC-9
- [ ] 5.2 HTML 变更报告 + 8 题测验
  - **Depends on**: 4.2 | **Requirement**: FR-C5, AC-8
- [ ] 5.3 verification-log 勿重跑扩充 + workflow_status 终态
  - **Depends on**: 4.2 | **Requirement**: FR-C3, AC-7
- [ ] 5.4 发版：版本 bump → commit/push → tag → Deploy 全绿 → 生产 E2E
  - **Depends on**: 5.1-5.3 | **Requirement**: AC-10, E16
