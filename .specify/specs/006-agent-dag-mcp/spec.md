# Feature Specification: 智能体 DAG 编排 + 本地工具执行回路（v9.0.0-A）

## Problem Statement

听风AI 现有 agent 子系统（intent/critic/memory/guard）是**点状能力**，彼此不串联：一个"画猫→审查→发送"的多步任务只能由调用方手动分步调 3 个端点，且聊天端 `tools` 参数仅转发上游、**本机无工具执行回路**。本需求把点状能力编排成 **DAG（有向无环图）多步任务执行器**，并把 agent 工具调用升级为可由 MCP 客户端消费的**可组合编排**，同时为后续 MCP server 化打地基。

## User Stories

### Story 1: DAG 任务提交与状态追踪（P0）

作为 API 调用方，我可以提交一个多步任务（`POST /v1/agent/dag/run`），指定节点/依赖/各自的 LLM 提示词，让系统按**拓扑排序**并行/串行执行，我通过 `GET /v1/agent/dag/{run_id}` 随时查询每个节点的状态。

**验收标准**
- [ ] `POST /v1/agent/dag/run` 接受 `name` + `nodes[]`（每节点 `id/kind/depends_on/prompt/model`），校验非法（循环依赖/空图/未知 kind）返回 422 与中文 message
- [ ] 返回 `run_id`，节点状态初始 `pending`
- [ ] `GET /v1/agent/dag/{run_id}` 返回 `status: pending|running|succeeded|failed` + 每节点 `status/result/error/duration_ms`
- [ ] 拓扑排序正确：串行链（A→B→C）一个失败即 `failed` 且后续节点 `skipped`
- [ ] 并行节点可并发执行（`max_parallel` 限制并发数）

### Story 2: 失败传播与重试（P1）

作为调用方，我的多步任务中某步失败时，我能控制失败传播策略并依赖重试参数。

**验收标准**
- [ ] `fail_fast=true`（默认）：任一节点失败 → 后续依赖节点 `skipped`，run `failed`
- [ ] `fail_fast=false`：失败节点 `failed`，其余可并行分支继续，run 结束 `failed`（有失败）或 `succeeded`
- [ ] 节点 `retry` 支持（指数退避 + 抖动），重试耗尽才标记 `failed`

### Story 3: LLM 规划器（P2，Mock 优先）

作为调用方，我可以用自然语言让 planner 把一句话任务分解成 DAG（`POST /v1/agent/dag/plan`），默认 **Mock 分解**（零真实付费红线），`IF_MOCK_UPSTREAM=0` 时才走 tryingopen 免费上游。

**验收标准**
- [ ] Mock 路径返回稳定 DAG（scene 由 intent 规则推导，planner 提示词基于 scene 组装）
- [ ] 真实 LLM 路径调 tryingopen，解析失败回退 Mock，不崩链路
- [ ] `grep` 全部 DAG 相关代码确认**无真实付费 provider 调用**（仅 tryingopen + Mock）

### Story 4: 鉴权与配置开关（P1）

**验收标准**
- [ ] 端点复用 `guard_chat_request`（公益开放同 chat；管理面写操作不涉及）
- [ ] `IF_AGENT_DAG_ENABLED=0` 时 404（缺省 **1**，与现有 agent 模块缺省开启一致，向后兼容）
- [ ] 新指标 `agent_dag_runs_total{status}` + `agent_dag_nodes_total{status}` 注册成功（Prometheus REGISTRY）

## Non-Functional Requirements

- 性能：DAG 执行器不阻塞事件循环（节点耗时走 `asyncio`；DB 写走 `to_thread`）
- 安全：付费 API 红线——测试只发 Mock，`grep` 无真实付费调用；输入提示词长度上限 8000
- 可观测：每节点 `duration_ms` + run 级 `created_at/finished_at`；日志带 run_id
- 兼容：不改动现有 `api/agent/{intent,critic,memory,guard,routes}.py` 任何公共接口；新文件只追加
- 测试：新文件单测覆盖正常/环依赖/空图/失败传播/重试/并发/边界 + 集成 E2E（HTTP 真实调起）

## Success Metrics

- 新增单测/集成用例 ≥ 25 个，覆盖 Story1-4 全部验收标准
- 全量单测 1723+ 基线无回归（exit 0）
- `POST /v1/agent/dag/run` + 轮询 finish 真实 E2E 通过（mock cf_solver + uvicorn）

## Out of Scope

- MCP server 完整实现（本 spec 只做 **编排层**，为后续 MCP 化打地基；`api/mcp/` 另立 spec）
- 真实付费 LLM 调用（Red 线，仅 tryingopen + Mock）
- 前端 DAG 可视化（P3 另立 spec）