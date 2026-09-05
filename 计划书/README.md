# 计划书文件夹

> 听风AI（imagefree-2ai）项目的迭代升级计划与改进指南专目录。所有规划性文档集中存放于此，与项目源码（`api/`/`frontend/`/`landing/`/`tests/`/`deploy/`）分离，保持仓库整洁。

## 文档索引

| 文档 | 用途 | 状态 |
|------|------|------|
| [下一步改进指南.md](./下一步改进指南.md) | v7.7.6 → v8.0.0 全景迭代蓝图（P0~P3 分级、RIPER-5 协议、TDD 清单、验收命令、回滚方案、版本路线图） | ✅ 已完成 |

## 使用方式

1. **执行方（AI 或开发者）**：从 `下一步改进指南.md` 第 0 章「执行总纲」开始，按 §0.2 执行顺序图逐 Phase 推进，每条改动遵循附录 B 的 TDD 模板。
2. **决策方（产品/技术负责人）**：参考第 4 章「改进总览矩阵」做优先级取舍，参考第 12 章「风险登记簿」做风险评估。
3. **验收方（QA）**：按第 11 章「验收口径与命令清单」逐项验证，结果追加到 `docs/verification-log.md`。

## 文档原则

- **可落地**：每条改进锚定 `file:line` + 具体函数名 + 验收命令，禁止空谈。
- **不重构**：只改进不重构，保留兼容垫片，不破坏公共接口。
- **不造轮子**：复用已造好未接线的能力（`storage/`/`background.spawn`/`solver_guard` 联邦/`adaptive_router` 持久化）。
- **真实闭环**：所有「完成」必须附 `pytest`/`vitest`/`build` 真实输出。

## 版本基线

- **当前版本**：v7.7.6（`pyproject.toml:4` + `api/main.py:109` + `frontend/package.json` + `landing/package.json` + `deploy/docker-compose.yml` ×2，共 7 处）
- **目标版本**：v8.0.0（架构治理 + 能力跃迁 + 体验登顶三线并进）
- **基线测试**：单测 1545 / 集成 37 / 混沌 5 / vitest 197 / E2E 22 / resp 20，全绿

## 相关文档（项目内）

- 架构评估：`docs/architecture-evolution.md`（演进触发器与「当前最划算三步」结论）
- 验证台账：`docs/verification-log.md`（每轮验证记录 + 「验证过勿重跑」结论）
- 发布历史：`release_notes_7.0.0.md` ~ `release_notes_7.4.0.md`（各版本变更明细）
- SOP 运维：`docs/SOP.md`
- 提供商集成：`docs/PROVIDER_INTEGRATION_GUIDE.md`

## 后续滚动

v8.0.0 落地后，本文件夹继续承载：
- `v8.1-免费三步走.md`（litestream + Cloudflare + UptimeRobot）
- `v8.2-向量检索.md`（语义去重/相似聚类）
- `v8.3-智能体编排.md`（DAG + 工具链）
- `v8.4-边缘计算与多模态.md`

每完成一个版本，在 `docs/verification-log.md` 追加验证记录 + 「验证过勿重跑」结论，并在本索引表追加一行。
