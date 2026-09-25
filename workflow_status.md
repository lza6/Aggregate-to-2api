# Workflow Status — 终局闭环总审计 / 生产化补强（Spec 008）

> 更新：2026-09-26 ｜ 上一版本：Phase A 参考项目对标（2026-09-22，已归档 docs/archived/）
> 主项目：`C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\imagefree-2ai`（听风AI，**v20.2.0 已发版**）
> 生产：20.204.27.154（ARM64 2C/4G）nginx 443 → imagefree-api 8100 + cfsolver 8001（camoufox）+ 代理池 2076
> 编排：Spec Kit 008（.specify/specs/008-production-hardening）+ 多子代理工作流

## 当前状态（2026-09-26）

| 域 | 状态 | 证据 |
|----|------|------|
| 提供商收敛 | ✅ imagefree/aifreeforever + tryingopen（nanobanana/falai 已下线） | registry=[imagefree,aifreeforever]+[tryingopen] |
| 首页在线使用 | ✅ landing HomeChat + 管理端 / 聊天 | https://imagefree.hwhcie.bond 200 |
| tryingopen 真实调用 | ✅ IF_MOCK_UPSTREAM=0，chat/Anthropic/agent plan 200 | 实测 mock=False |
| 代理池高并发 | ✅ IF_FREE_PROXY=1 启用，并发 4/4 completed | v20.2 fix `_is_upstream_ip_busy` |
| cf_solver | ✅ camoufox ARM64 单次 ~3s | solve_success |
| 版本/Release | ✅ v20.0.0/v20.1.0/v20.2.0 | gh release |
| **终局审计（本轮）** | 🔄 Spec 008 进行中：S1 全仓审计 / S2 SQL+压测 / S3 契约 / S4 架构 ADR | 见下 |

## 本轮子任务工作流（Spec 008）

| 子任务 | Agent | 状态 | 产出 |
|--------|-------|------|------|
| S1 终局审计（架构/死代码/契约撒谎/安全/性能） | explorer #3 | 🔄 运行中 | 审计报告 → 修复 commit |
| S2 SQL/索引/事务/压测 | explorer #4 | 🔄 运行中 | SQL 审计 + 压测断言 |
| S3 契约核验（OpenAPI≠前端≠文档≠真实） | 主控 | ⏳ 排队 | 契约矩阵 → 修复 |
| S4 架构演进 ADR（LB/Redis/CDN/DB/队列/限流/熔断/可观测） | worker | ⏳ 排队 | adr/architecture-evolution.md |

## 铁律（本工作流强制）

1. 验证记录防重跑：docs/verification-log.md 持续追加；"验证过勿重跑"结论维护
2. 真实性：每项验收附命令输出/证据，禁止"跑过=完成"
3. 可回滚：所有改动主题 commit + push；不强行上重架构（单机成本现实）
4. 节点验收：每子任务产出独立验收（单测/E2E/真实输出），主控汇总后统一 commit/release

---

## 历史（Phase A 参考项目对标，2026-09-22）

# Workflow Status — 参考项目全量对标分析与主项目改进路线图（Phase A v2）

> 任务类型：深度对标分析（ANALYSIS_ONLY 阶段，v2）。启动：2026-09-22。
> 主项目：`C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\imagefree-2ai`（听风AI，v19.0.0，Release 已发布）
> 参考根：`D:\参考项目`（**1234 个业务目录** = v1 清单 1170 + delta 新增 68 + `.claude` 豁免）
> 编排方式：**6 子代理深复核 agent_ai/agent_skill 190 目录**（v2 报告 `docs/research/ref-scan-v2/out_g01~g06.md`）+ 主协调沿用 v1 基线（g07~g23）+ delta 68 快筛 + 合成（同线程分角色检查，未冒充独立代理）。
> 旧状态（v1，2026-09-16）已归档 `docs/archived/workflow_status-2026-09-16-PhaseA-v1.md`。

## Task Contract

- **原始目标**：自动完成参考项目识别、同类筛选、优点提炼、差距分析、优化方案设计，产出 `参考的结果计划指南.md` + 本文件；**用户确认后进入 Phase B 逐步实施**。
- **当前阶段**：Phase A（ANALYSIS_ONLY）— 只读分析 + 产出文档。
- **当前授权**：读取/分析主项目与参考项目；运行非破坏性发现命令；写文档（参考的结果计划指南.md、workflow_status.md、ref-scan-v2/*.md）。**禁止修改源码/配置/数据库/依赖/部署**；禁止提交/推送/部署；禁止删除任何文件。
- **成功标准**：①1234 目录全覆盖（每目录至少一行结论或明确归组）②主项目 v19 现状评估 ③参考亮点提炼（证据）④差距分析 ⑤可迁移/半迁移/不建议迁移分类 ⑥P0/P1/P2 路线图 ⑦全栈实施方案（Batches）⑧写 `参考的结果计划指南.md` + 本文件 ⑨停止等用户确认。
- **停止条件**：产出完整 Phase A 报告并停止等待用户确认；任何阻塞 → 标 BLOCKED 并披露。

## Task Graph

| ID | Owner | Goal | Dependencies | Deliverable | Validation | Status |
|----|-------|------|--------------|-------------|-----------|--------|
| S0 | 主协调 | 环境重勘（参考根/清单/基线/delta） | 无 | 1234 目录 + 68 delta | 命令实测 | DONE |
| S1 | 子代理 g01 | agent_ai_a 40 目录 v2 深复核 | S0 | out_g01（169 行，40/40，去重后 37） | 报告+摘要 | DONE |
| S2 | 子代理 g02 | agent_ai_b 40 目录 v2 深复核 | S0 | out_g02（140 行，40/40） | 报告+摘要 | DONE |
| S3 | 子代理 g03 | agent_ai_c 37 目录 v2 深复核 | S0 | out_g03（TOP 带 file:行） | 报告+摘要 | DONE |
| S4 | 子代理 g04 | agent_skill_a 28 目录 v2 深复核 | S0 | out_g04（237 行） | 报告+摘要 | DONE |
| S5 | 子代理 g05 | agent_skill_b 28 目录 v2 深复核 | S0 | out_g05 | 报告+摘要 | DONE |
| S6 | 子代理 g06 | agent_skill_c 26 目录 v2 深复核 | S0 | out_g06（29KB） | 报告+摘要 | DONE |
| S7 | 主协调 | g07~g23 沿用 v1 基线（记忆/视频/编码/网关/MCP/安全/桌面/misc） | S0 | 指南四/五 | 引用 v1 实测 | DONE（沿用） |
| S8 | 主协调 | delta 68 新目录快筛 + 分类 | S0 | 指南附录 B | 枚举实测 | DONE |
| S9 | 主协调 | 合成 `参考的结果计划指南.md` | S2-S8 | 根目录文档（30.5KB，12 章） | 章节完整 | DONE |
| S10 | 主协调 | 更新本文件 | S9 | workflow_status.md | 状态一致 | DONE |
| S11 | 独立 Critic | 六维审查 v2 指南 | S9 | critic 发现 | 审查完成 | PENDING |
| S12 | 用户 | 确认 Phase B 范围 | S9-S11 | 授权决定 | 用户输入 | AWAITING |

## Project Inventory

- **主项目摘要**：Python3.11/FastAPI/SSE 图像+对话生成网关（听风AI v20.0.0）：图片上游 imagefree/aifreeforever（nanobanana、falai 已下线）+ 对话/agent 上游 tryingopen（默认真实调用）+ 首页在线对话（HomeChat）+ agent（意图/DAG/critic/记忆 L1-L3+RRF/MCP 8 工具+审批/skills 5 件套+扫描+手动&自动沉淀）+ React19 面板（`/` 在线聊天、`/dashboard` 仪表盘）+ Vue3 landing + Tauri2 桌面 + 视频 Mock + PPT + 电商护栏。测试：单测/集成/混沌/vitest 分批验证中，E2E 见 v20 更新。
- **参考候选（高价值，v2/v1）**：hermes-agent/CowAgent/wild_agentos/learn-agent/mattpocock teach/nuwa（agent 进化+教学）、mono-color/marketing/SkillOpt（技能验证+精修）、agentmemory/mem0/ai-memory/cognee（记忆）、product-review-agent/EcomAgent/commerce-agents（电商护栏）、Pixelle/video-shotcraft/MoneyPrinterTurbo（视频）、new-api/sub2api/smart-mcp-proxy（网关/MCP）、dsh-desktop/cc-switch（桌面）、captcha-solver/Pentest-Swarm-AI/agentseal（安全）、headroom/rtk-master（上下文，v19 已落地 context_trim 库）。
- **delta 68**：sub2api/cognee/AgentCompass/OpenSpec/trailofbits__skills/Tencent__BrowserSkill 等优先；jev-* 24 项疑重复（先归并）。
- **排除**：`.claude`（配置豁免）；jev-* 副本（去重后再深扫）；infra 通用件（pingora/localsend/vaultwarden 等）仅记录。

## Evidence Ledger

| Claim | Evidence | Type | Confidence |
|---|---|---|---|
| 参考根 1234 目录 | `Get-ChildItem D:\参考项目 -Directory` 实测 | DIRECT | High |
| delta 68（新未覆盖） | 1234 − 23 组清单并集 1170 | DIRECT | High |
| 6 组 agent 深复核落盘 | ref-scan-v2/out_g01~g06.md 存在且含全表+TOP(file:行) | DIRECT | High |
| 主项目 v19.0.0 | api/main.py version、git HEAD 490185d、gh release v19.0.0 | DIRECT | High |
| g07~g23 沿用 v1 | docs/research/ref-scan/out_g07~g23.md（2026-09-16 实测） | DIRECT | High |
| 未改任何源码 | git status --short 仅未跟踪用户文件 | DIRECT | High |

## Decisions and Assumptions

- **决策**：6 组 agent 深复核 + 主协调沿用 v1（勿重做 66 深侦察与 1170 目录初扫）。
- **决策**：本机子代理并发受限（约 6）→ 分批执行；g07~g23 不强行重扫，明确标注沿用 v1。
- **决策**：路线图以用户命题为主线（agent 深度/小白可懂/沉淀用户技能/扩展场景）。
- **假设**：misc 803 中多数与主项目无直接关系，仅作远期扩展线索。
- **被否决**：不引入 Rust/Go 完整项目、不引图数据库记忆、不推翻重写；只有子代理通道恢复正常或用户要求时才补 g07~g23 的 v2 逐目录重扫。

## Risks and Blockers

| 风险 | 触发 | 影响 | 缓解 |
|---|---|---|---|
| 子代理通道受限 | 平台并发/接口限流 | g07~g23 无 v2 重扫 | 标注"沿用 v1"；通道恢复后再补扫 |
| 技能自演化迁移过度乐观 | Phase B B1 | 误判/污染技能库 | 留出验证+严格门禁+快照回滚+仅记收据哈希 |
| 技能沉淀含私有 prompt | Phase B B1/B4 | 泄露 | 审批提示+导出脱敏+仅哈希收据（沿用 v17） |
| jev-* 重复副本误扫/误删 | delta 深扫/清理 | 浪费/误删 | 先归并去重；删除须用户逐项确认 |
| 真实视频/桌面验证 | Phase B B8/B9 | 付费/耗时 | Mock 红线+「待验证」标注不伪装 |

## Implementation Batches（Phase B，未授权）

B0 基线回归 → B1 技能进化精修（IF_SKILL_EVOLVE_ENABLED=0）→ B2 技能蒸馏向导 → B3 黑匣子（步骤摘要+计划vs产物diff+不可变收据）→ B4 skills 市场/不可变/审批 → B5 evals 断言目录+CI → B6 电商护栏三分流+置信度 → B7 记忆巩固+级联过时+召回指标 → B8 视频动作族+配方卡+真实链 → B9 桌面真机 → B10 i18n 10 页+a11y → B11 安全沙箱+CI 门禁 → B12 文档/部署/版本 bump v20.0.0 发布。详见 `参考的结果计划指南.md` §七。

## Validation Matrix

| Requirement | Validation Method | Result | Status |
|---|---|---|---|
| 1234 目录覆盖 | 枚举 vs 清单并集 | 全覆盖（1170+68） | VERIFIED |
| agent 类 v2 深复核 6/6 | out_g01~g06 存在+全表 | 190 目录复核 | VERIFIED |
| 主指南 12 章完整 | rg "^## " | 12 章 | VERIFIED |
| 不改源码 | git status | 无源码改动 | VERIFIED |

## Review Findings

- v1 Critic：3.8/5 → CONDITIONAL PASS（全部已修复并归档）。
- v2 修正：i18n 10 页（v1 笔误 9）；Rust 已装；g01 去重 3 副本→37；g04 修正 3 处技能偏差；delta 68。
- 剩余：g07~g23 v2 重扫待通道恢复/用户要求；真实视频/桌面待验证；S11 Critic 待跑。

## Next Gate

- **停止等待用户确认 Phase B 范围**（决策点①②③④见 `参考的结果计划指南.md` §十）。
- 用户确认后：按 B0→B12 逐批实施，每批回填 `docs/verification-log.md` + 本文件状态。
