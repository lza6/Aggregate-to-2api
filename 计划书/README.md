# 计划书文件夹

> 听风AI（imagefree-2ai）项目的迭代升级计划与改进指南专目录。所有规划性文档集中存放于此，与项目源码（`api/`/`frontend/`/`landing/`/`tests/`/`deploy/`）分离，保持仓库整洁。

## 文档索引

| 文档 | 用途 | 状态 |
|------|------|------|
| [下一步改进指南.md](./下一步改进指南.md) | **v11.0.0 全景迭代升级指南**（v10.0.0 基线：MCP 协议化 + 深化层展开 + 前端 DAG 节点图 + 桌面版深化 + RAG 增强） | ✅ v11.0.0 规划轮重写 |
| [2026-09-07-stage-mtpst934-全栈现状分析.md](./2026-09-07-stage-mtpst934-全栈现状分析.md) | v8.5.0 复核 + 真实缺口（G1-G4）+ 5 新发现（N1-N5） | ✅ 已完成 |
| [2026-09-06-stage-mtpswcm8-权威基线档案.md](./2026-09-06-stage-mtpswcm8-权威基线档案.md) | v8.5.0 真实状态快照（5 缺口收敛 + 已落地项清单） | ✅ 已完成 |
| [2026-09-06-stage-mtpr9lhc-落地闭环核实与基线测试记录.md](./2026-09-06-stage-mtpr9lhc-落地闭环核实与基线测试记录.md) | 落地闭环核实记录 | ✅ 已完成 |
| [2026-09-06-stage-mtpr4smw-测试数据采集与收尾基线.md](./2026-09-06-stage-mtpr4smw-测试数据采集与收尾基线.md) | 测试数据采集基线 | ✅ 已完成 |
| [2026-09-06-stage-mtprbdhs-测试结果汇总与收尾基线.md](./2026-09-06-stage-mtprbdhs-测试结果汇总与收尾基线.md) | 测试结果汇总基线 | ✅ 已完成 |

## 使用方式

1. **执行方（AI 或开发者）**：先读 `下一步改进指南.md` §0 文档信息 + §4 可复用资产 + §5 已落地/待办核对，按 §13 依赖序逐波推进，每条改动遵循 §21 TDD 模板。
2. **决策方（产品/技术负责人）**：参考 §1.3 核心目标矩阵 + §18 风险登记簿做优先级取舍。
3. **验收方（QA）**：按 §17 验收标准和完成定义逐项验证，结果追加到 `docs/verification-log.md`。

## 文档原则

- **可落地**：每条改进锚定 `file:line` + 具体函数名 + 验收命令，禁止空谈。
- **不重构**：只改进不重构，保留兼容垫片，不破坏公共接口。
- **不造轮子**：复用已造好未接线的能力（`vector/`/`skills/`/`background.spawn`/`solver_guard` 联邦/`adaptive_router` 持久化/`cost_forecast`/`desktop/`）。
- **真实闭环**：所有「完成」必须附 `pytest`/`vitest`/`build` 真实输出。

## 版本基线

- **当前版本**：v10.0.0（`pyproject.toml` + `api/main.py` + `frontend/package.json` + `landing/package.json` + `deploy/docker-compose.yml` + `deploy/pyproject.toml` + `landing/index.html` + README badge 8 处一致 + 桌面版 2 处：`desktop/package.json` + `desktop/src-tauri/tauri.conf.json`）
- **目标版本**：v11.0.0（智能体体系成熟跃迁：MCP 协议化 + 深化层 + 前端 DAG 节点图 + 桌面版深化 + RAG 增强）
- **基线测试**：CI 单测口径 `pytest -m "not integration and not chaos and not slow"` = 1723+ passed（v10.0.0 实测）；集成 37 / 混沌 5 / vitest 225 / ruff 0 / mypy strict 7 模块
- **已落地勿重做**：DAG 引擎 + 规划器（v9.0.0）/ run SQLite 持久化 + 配置开关统一（v10.0.0-A）/ 前端 Agent 页列表闭环（v10.0.0）/ 桌面版全栈化（v10.0.0）/ storage 热路径 / litestream + Grafana / 向量检索 + 成本预测 / flaky 根治

## 相关文档（项目内）

- 架构评估：`docs/architecture-evolution.md`（演进触发器与「当前最划算三步」结论）
- 验证台账：`docs/verification-log.md`（每轮验证记录 + 「验证过勿重跑」结论）
- SOP 运维：`docs/SOP.md`
- 提供商集成：`docs/PROVIDER_INTEGRATION_GUIDE.md`

## 后续滚动

每完成一个版本，在 `docs/verification-log.md` 追加验证记录 + 「验证过勿重跑」结论，并在本索引表追加一行。
