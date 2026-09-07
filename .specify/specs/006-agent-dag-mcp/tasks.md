# Implementation Tasks: 006 智能体 DAG 编排 + MCP 前置（v9.0.0-A）

## Phase 1: 引擎与规划器（纯新文件，可并行）

- [x] 1.1 `api/agent/dag.py` 引擎（DAGNode/DagRun/parse_nodes/topological_sort/execute_run）
  - Kahn 拓扑 + 环/自依赖/未知依赖拒绝
  - 状态机 pending→running→succeeded/failed/skipped
  - 并行扇出真并发 + max_parallel 信号量限流
  - 指数退避+抖动重试
  - **Depends on**: None
- [x] 1.2 `api/agent/planner.py` 规划器（Mock 优先 + LLM 降级）
  - scene → 节点串（复用 intent 规则正则）
  - LLM 路径仅 tryingopen（`IF_MOCK_UPSTREAM=0`）+ 解析失败回退 Mock
  - **Depends on**: None

## Phase 2: 路由与执行体

- [x] 2.1 `api/routes/agent_dag.py` 路由（/v1/agent/dag/run|plan|{run_id}）
  - `guard_chat_request` 鉴权；开关 404
  - 提交时拓扑校验（环→422）
  - 后台 `background.spawn` 执行 + `_STORE` 内存 run 存储
  - **Depends on**: 1.1, 1.2
- [x] 2.2 `api/routes/agent_dag_store.py` 进程内 run 存储
  - **Depends on**: 2.1
- [x] 2.3 `api/routes/agent_dag_exec.py` 节点执行体（scene/llm/critic/memory/tool 分发）
  - **Depends on**: 2.1

## Phase 3: 接缝（最小改动）

- [x] 3.1 `api/routes/__init__.py` 挂载 agent_dag.router
- [x] 3.2 `api/config/__init__.py` 三新字段（IF_AGENT_DAG_ENABLED / IF_AGENT_PLANNER_ENABLED / IF_PLANNER_LLM_MODEL）+ `deploy/.env.example` / `.env.production.example` 同步
- [x] 3.3 `api/agent/routes.py` import metrics（启动即注册）
- **Depends on**: 2.1, 2.2, 2.3

## Phase 4: 测试（TDD，先测后码）

- [x] 4.1 `tests/test_agent_dag.py`（29 用例：拓扑/解析/执行/并发/重试/状态）
- [x] 4.2 `tests/test_agent_planner.py`（8 用例：Mock/LLM 降级/契约）
- [x] 4.3 `tests/test_agent_dag_routes.py`（11 用例：HTTP 端点/校验/开关/404）
- [x] 4.4 `tests/test_agent_dag_exec.py`（8 用例：5 kind 分发/边界/降级）
- **Depends on**: 1.1-3.3

## Phase 5: 验证与收尾

- [x] 5.1 新功能 4 文件全绿（56 用例）
- [x] 5.2 全量单测 5× 全绿（1723+ 基线无回归）
- [x] 5.3 ruff 0 error + config 一致性测试 20 passed
- [x] 5.4 覆盖率 ≥80%（5 文件合计 89.5%）
- [x] 5.5 真实 E2E（uvicorn + mock solver：plan→run→轮询 / 422 / 404 / 扇出 / metrics / 既有端点回归）
- [x] 5.6 `workflow_status.md` 台账
- [ ] 5.7 文档同步（下一步改进指南 §6.1/§32 回写 + README DAG 端点）
- [ ] 5.8 commit → tag v9.0.0 → push → Release（Release 待 PAT）
- **Depends on**: 4.1-4.4

## Notes

- 付费红线：planner/exec 仅 tryingopen 免费上游 + IF_MOCK_UPSTREAM=1 Mock；`grep` 无真实付费调用
- 三铁律：不重构现有 agent 模块公共接口；只追加；先测后改
- MCP server 化（工具执行回路）为 v9.0.0-B 立项，本轮不做