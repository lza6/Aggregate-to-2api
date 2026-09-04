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

- [ ] 2.1 契约修复（P0/P1 逐条 + 定向测试）
  - **Depends on**: 1.1 | **Requirement**: FR-B1, AC-1
- [ ] 2.2 后端修复（P0=0/P1 清零）
  - **Depends on**: 1.2 | **Requirement**: FR-B2, AC-2
- [ ] 2.3 前端修复（UX P1 + 已知 P2 一并落地）
  - **Depends on**: 1.3 | **Requirement**: FR-B3, AC-3
- [ ] 2.4 CI frontend 门禁 job（vitest+tsc+build）+ 本地模拟
  - **Depends on**: 1.4 | **Requirement**: FR-B4, AC-4
- [ ] 2.5 文档同步（README/SOP v2.4/PRD 增量）
  - **Depends on**: 1.4, 2.1-2.3 | **Requirement**: FR-B5, AC-5

## Phase 3: 全量验证

- [ ] 3.1 后端 CI 口径全量 + ruff（若有 py 改动）
  - **Depends on**: Phase 2 | **Requirement**: AC-2
- [ ] 3.2 前端 vitest + tsc + build + 双 E2E（本地）
  - **Depends on**: Phase 2 | **Requirement**: AC-3
- [ ] 3.3 CI 门禁本地模拟（frontend job 步骤）
  - **Depends on**: 2.4 | **Requirement**: AC-4

## Phase 4: 审查循环（≤3 轮）

- [ ] 4.1 独立审查线程六维审查 → 修复清单
  - **Depends on**: Phase 3 | **Requirement**: FR-D1, FR-D2, AC-6
- [ ] 4.2 主线程修复 → 审查复验 → 收敛或阻塞披露
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
