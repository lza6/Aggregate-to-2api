# 005-v77-terminal-closure Spec — 终局闭环总审计（v7.7）

> Spec-Kit 7 阶段。宪法：`.specify/memory/constitution.md`（Production-First / Complete Closure / Defense in Depth / Developer Experience）。
> 前置：004-final-audit-v76（v7.6.0 已发布、生产验证通过）。本轮 = 全链路盲点扫描 + 未知未知补齐 + 工作流资产沉淀。

## 背景与触发

用户判定上一轮交付"实现过浅、未深度闭环"：前后端衔接、功能完整性、兼容性、调用体验等多方面未考虑。要求：
1. Spec-Kit 规范流程（宪法/spec/plan/tasks/analyze/implement）；
2. 多子代理拆解并行审计 → 主线程修复 → 独立审查复验循环；
3. 盲点扫描（unknown unknowns）；
4. 一人开发当团队用：Agent 管 Agent、复用历史验证记录避免重复劳动；
5. 收尾：HTML 变更报告 + 底部测验（必须通过）；
6. 把项目整理成可复用 workflow + skills（新 API/新功能的标准化接入路径）；
7. critical-code-reviewer 严苛审查协议（有罪推定）；
8. Agent 自主挑选高价值增强（高并发/安全/性能/UI）。

## 功能需求（FR）

### A. 审计与发现（已完成 → 产出清单）

- **FR-A1 前后端契约审计**：前端 `api/*.ts` 类型 ↔ 后端 routes 响应逐字段比对（字段名/类型/可选性/幽灵端点/错误信封）。产出：contract 清单。
- **FR-A2 后端安全健壮性审计**：SQL 注入面、裸 except、未 await 协程、敏感日志、path traversal、资源泄漏、TODO/FIXME 残留、错误码不一致、跨协程数据竞争。产出：P0/P1/P2 清单。
- **FR-A3 前端 UX 闭环审计**：防重复提交、危险操作确认、空态/错误态、表单校验前后端一致、轮询生命周期、深链刷新、无 Key UX、格式一致性、console 残留。产出：P1/P2 清单。
- **FR-A4 配置/部署/文档一致性审计**：IF_* 三方核对（config ↔ .env.example ↔ compose）、版本 8 处、README 可跑通性、SOP 时效、CI 盲区（frontend 门禁）。产出：漂移清单。

### B. 修复与补齐（依据 A 清单，主线程执行）

- **FR-B1 契约修复（P0/P1）**：类型错位修正 + 幽灵端点清理或补实现；错误信封解析对齐。
- **FR-B2 后端修复（P0/P1）**：注入面参数化、吞错重抛/注释、协程 await、敏感日志脱敏、TODO 清理或转 issue。
- **FR-B3 前端修复（P1）**：防重复提交（提交中禁用）、危险操作二次确认、无 Key 引导、已知 P2（aria-label×3 页、h2 跳级、role=log、img 尺寸）一并落地。
- **FR-B4 CI 门禁补盲**：frontend vitest+tsc+build 纳入 CI job（landing 已有，frontend 缺）。
- **FR-B5 文档同步**：README/SOP 时效修正、verification-log 追加、PRD 增量。

### C. 资产沉淀（复用）

- **FR-C1 需求追踪矩阵**：显式/隐式/验收/非功能四类需求 → 实现映射（写入 spec plan.md）。
- **FR-C2 workflow_status.md**：任务契约、任务图、验证日志、审查发现、阻塞项，循环更新直至全绿。
- **FR-C3 验证记录复用**：所有验证结论写入 verification-log「勿重跑」区 + 记忆 MEMORY.md 更新（避免下轮重复审计）。
- **FR-C4 skills 沉淀**：`.claude/skills/imagefree-workflow/` 扩充《新 Provider 接入 SOP》《新功能接入 SOP》（含验收清单），使下次"加新 API/新功能"有标准路径可读。
- **FR-C5 HTML 变更报告**：docs/reports/v7.7-*.html 含上下文/直觉/变更/测验（8 题，必须通过口径）。

### D. 独立审查循环

- **FR-D1**：审查线程（不直接改码）从需求完整性/逻辑正确性/边界/代码质量/测试覆盖/运行结果六维审查 → 修复清单交主线程 → 修复 → 复验，最多 3 轮。
- **FR-D2 critical-code-reviewer 协议**：有罪推定、file:line 证据、Blocking/Required/Suggestion/Nit 四级、Assessment 收尾。

## 非功能需求（NFR）

- NFR-1 兼容性：修复不破坏既有调用方（/v1/* 公益开放契约不变，新增字段只增不改）。
- NFR-2 性能：不改慢的更慢；前端 bundle 不增长 >5%。
- NFR-3 安全：付费上游零真实调用；密钥仅 IF_* 环境变量。
- NFR-4 平台：Windows 本地开发 + Ubuntu CI/生产双通过。
- NFR-5 诚实结案：四级标签（已验证/静态确认/合理推断/待验证）。

## 验收标准（AC）

- AC-1 契约审计清单 100% 处置（修复或标注"设计如此+理由"）。
- AC-2 后端审计 P0=0、P1 修复或有阻塞说明。
- AC-3 UX 审计 P1=0；Top8 落地。
- AC-4 CI 增加 frontend 门禁 job 并本地模拟通过。
- AC-5 版本 8 处一致；README 步骤与实际吻合；SOP 更新至 v2.4。
- AC-6审查循环收敛：审查线程复验 PASS 或明确阻塞清单。
- AC-7 workflow_status.md 全任务 [x] + 证据链接。
- AC-8 HTML 报告 + 测验交付。
- AC-9 skills 文档两篇（新 Provider / 新功能 SOP）落地并被 SKILL.md 索引。
- AC-10 发版：版本 bump → 提交推送 → tag → Deploy 全绿 → 生产 E2E 复验。

## Out of Scope

- 真实付费上游 E2E（fal.ai/imagefree 付费通道，预算 0）。
- Redis/Kafka/CDN 等基础设施级扩展（当前 SQLite+单机架构下属过度设计，转为 P3 建议记录于 architecture-evolution.md）。
- React 大版本/框架迁移、Tailwind 引入（已评估否决）。
- landing 大改版（v7.4 已完成）。

## Clarifications（自问自答，用户已授权自主推进）

### Q1: CI 集成测试 job flaky（组合串扰）是否本轮根治？
**答**: 根治成本高（需隔离 IP 桶状态的全局 fixture 重构）。本轮做**缓解**：拆分测试执行顺序（integration 单独 --fork 或 -p xdist 分组），并记录于 verification-log。彻底根治转 P3。

### Q2: 数据库迁移/Redis 引入是否本轮做？
**答**: 不做（Out of Scope）。SQLite 单机写场景（0.2s 批量合并 + WAL）在当前量级（16k 行）无瓶颈，Architecture Decision Record 记录升级触发条件（>100 QPS 持续写 或 数据 >500MB）。

### Q3: HTML 报告测验放多少题？
**答**: 8 题（沿用 v7.4 惯例），覆盖：契约修复、CI 门禁、UX 闭环、安全修复、文档同步、skills 沉淀、发布流程、勿重跑机制。
