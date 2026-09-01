# 003-final-closure Spec — v7.3 终局闭环总审计

> 依据 spec-kit-skill 7 阶段工作流的 Specify 产物。宪法：.specify/memory/constitution.md。

## 功能需求（FR）

- **FR-1 需求追踪矩阵落地**：《下一步改进指南.md》22 条逐项核对，状态回写真实结论（✅/⚠️/⬜）+ 证据，消灭「文档待办 vs 代码已做」漂移。
- **FR-2 后端大文件拆分补全（P2-4 后端半）**：email_pool.py（1315 行）9 个 Source 类拆 `api/email_sources/` 子包（每源一文件，向后兼容 import）；目标全部 <800 行。
- **FR-3 生产收紧包（P1-2 补全）**：产出 `deploy/.env.production.example` 收紧模板（CORS 白名单/CSP 开启/独立管理 Key 语义说明）+ 文档化开启步骤与回滚，等部署时替换即生效。
- **FR-4 全量回归验证**：本地全量跑后端套件（排除预存卡死 2 用例）+ 前端全量 + landing build + ruff，产出 verification-log。
- **FR-5 独立审查线程**：以 critical-code-reviewer 协议对本轮全部 diff 做六维审查（需求完整性/逻辑正确性/边界/代码质量/测试覆盖/实际运行），产出修复清单，主线程修复后复验，循环至通过或明确阻塞。
- **FR-6 文档全面同步**：README（版本徽章/架构图/端点表/skill 结构描述）、.claude/skills/imagefree-workflow/SKILL.md（v6.x 单文件时代描述→v7.2 现状）、workflow_status.md、改进指南版本回写区。
- **FR-7 项目工作流 skill 化**：imagefree-workflow skill 增加「新增提供商接入 SOP」「验证记录优先读取协议」章节；写持久记忆（memory/）沉淀跨会话经验。
- **FR-8 HTML 变更报告**：本轮全部变更的上下文/直觉/内容报告 + 底部验收测验（必须通过）。
- **FR-9 高价值架构评估**（Agent 管理 Agent 产出）：高并发补强路线图（Redis/CDN/MQ/LB/分片等在当前公益单机形态下的适用性判断），形成 docs/architecture-evolution.md——评估落地，不做未授权生产变更。
- **FR-10 SOP 完善**：docs/SOP.md 补「新版本发布 checklist」「故障排查速查」「备份验证演练」章节。

## 验收标准（AC）

- AC-1 改进指南 22 条每条有真实状态+证据，版本回写区填 v7.0/v7.1/v7.2 三行。
- AC-2 email_pool 拆分后 `from api.email_pool import LinshiMailSource` 等旧 import 路径不破（或明确列出迁移映射），email_pool.py < 800 行，`api/email_sources/` 每文件 <400 行，全量测试绿。
- AC-3 .env.production.example 存在且每项有注释说明；README 引用。
- AC-4 全量回归有实际运行输出记录进 verification-log.md。
- AC-5 审查线程六维结论：Blocking=0（或全部修复后复验通过）。
- AC-6 README 版本徽章=7.2.0，skill 描述与真实结构一致（抽查 3 处文件路径存在）。
- AC-7 memory/ 有 ≥3 条跨会话记忆；skill 含 SOP 章节。
- AC-8 HTML 报告可打开、内容完整、测验 10 题。
- AC-9 architecture-evolution.md 有明确的「适用/不适用/前置条件」结论。
- AC-10 SOP.md 含发布 checklist + 排查速查。

## 范围外（Out of Scope）

- cf_solver page_count 生产变更（需灰度窗口，本轮只产出评估）
- cloudflare_temp_email 自建部署（外部资源）
- Redis/MQ/分片实际引入（公益单机形态收益<成本，FR-9 只评估）
- 真实付费 API E2E（用户明确豁免）
