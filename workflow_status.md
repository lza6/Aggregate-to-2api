# workflow_status.md — 听风AI v9.0.0-A 智能体 DAG 编排落地台账

> **任务契约**：把 `计划书/下一步改进指南.md` §6.1（G4 智能体 DAG 编排）+ §6.2（MCP 协议化前置）从「待办」推进到「真实落地闭环」。
> **授权边界**：用户明确指示「完整落地闭环 + 真实 E2E + 提交推送 + 创建发行版」；源码改动限于新增 `api/agent/dag.py`、`api/agent/planner.py`、`api/routes/agent_dag*`、`tests/test_agent_dag*` + 最小接缝（`routes/__init__.py`、`config/__init__.py`、`agent/routes.py`、`.env.example`、`.env.production.example`）。

## 一、验收标准表

| ID | 验收标准 | 状态 | 证据 |
|---|---|---|---|
| A1 | `POST /v1/agent/dag/run` 提交 → 后台执行 → `GET /{run_id}` 终态 | ✅ done | E2E 实测 `run_id=0786856771544d5f` status=succeeded，node A/B/C 全 succeeded |
| A2 | 拓扑排序串行链正确，并行扇出真并发 | ✅ done | 引擎单测 `TestTopologicalSort`/`TestConcurrency`（throttle/并发 2 用例）+ HTTP 扇出 run 三节点全 succeeded |
| A3 | 失败传播：fail_fast 依赖链 failed→skipped + 重试耗尽才 failed | ✅ done | 引擎单测 `test_fail_fast_skips_downstream` / `test_retry_exhausted_marks_failed` / `test_retry_then_success` |
| A4 | 输入校验：未知 kind / 环 / 自依赖 / 未知依赖 / id 重复 / 超上限 → 422 中文 | ✅ done | 引擎 + 路由单测 + E2E 实测（bogus→422「未知节点类型」、cycle→422「检测到环形依赖」） |
| A5 | 规划器：Mock 优先 + LLM 路径降级 Mock + 零真实付费 | ✅ done | `test_agent_planner.py` 8 用例；`grep` 确认仅 tryingopen+Mock |
| A6 | 开关：`IF_AGENT_DAG_ENABLED=0` / `IF_AGENT_PLANNER_ENABLED=0` → 404 | ✅ done | 路由单测 `TestDagDisableSwitch`/`test_plan_disabled_404`；config 3 新字段 + env.example/production 同步，`test_config_validate` 20 passed |
| A7 | 鉴权：复用 `guard_chat_request`（公益开放） | ✅ done | 路由所有端点调用；E2E 无 Key 直调 200 |
| A8 | Prometheus 指标启动即注册 | ✅ done | `agent/routes.py` import metrics；E2E 实测 `/metrics` 含 4 个 `agent_*` HELP/TYPE |
| A9 | 全量单测基线无回归 | ✅ done | 5 连全绿（含 1 skip）；首次 exit=1 为已知组合串扰 flaky（lru_cache），非本次回归 |
| A10 | ruff 0 error | ✅ done | `ruff check api/agent/ api/routes/agent_dag*.py api/routes/__init__.py api/config/__init__.py` → All checks passed |
| A11 | SO 覆盖率 ≥ 80% | ✅ done | json 实测：dag.py 95% / planner.py 80% / routes.agent_dag 91% / exec 85% / store 87% / 合计 89.5% |
| A12 | spec-kit 结构化追踪（006 spec/tasks） | ✅ done | `.specify/specs/006-agent-dag-mcp/spec.md` 已建；tasks.md 见下 |

## 二、任务图

```
spec 006（spec.md）
   └─ S1 api/agent/dag.py ────────────────┐
   └─ S2 api/agent/planner.py ────────────┼─→ S3 routes/agent_dag{,.py,_store,_exec}
                                           └─ 接缝：routes/__init__ + config + agent/routes + env 模板
                                                └─ 测试（4 文件 56 用例）→ 全量回归 → E2E → 文档 → commit/tag/push
```

- 可并行：S1/S2（纯新文件）→ 已并行完成
- 必须串行：S3 依赖 S1+S2 → 已按序完成
- 收尾串行：workflow_status → spec tasks.md 回写 → 文档同步 → git commit/tag/push → Release

## 三、验证日志

| 日期 | 范围 | 命令 | 结果 |
|---|---|---|---|
| 2026-09-07 | 引擎单测 | `pytest tests/test_agent_dag.py` | 29 passed |
| 2026-09-07 | 规划器单测 | `pytest tests/test_agent_planner.py` | 8 passed |
| 2026-09-07 | 路由 HTTP 单测 | `pytest tests/test_agent_dag_routes.py` | 11 passed |
| 2026-09-07 | 执行体单测 | `pytest tests/test_agent_dag_exec.py` | 8 passed |
| 2026-09-07 | 新功能覆盖率 | `--cov=api.agent.dag ... json` | 89.5%（5 文件，合计 410/458 stmts） |
| 2026-09-07 | 全量单测回归×5 | `pytest -m "not integration and not chaos and not slow"` | 5× `[100%]` exit 0（1723+ 基线） |
| 2026-09-07 | ruff | `ruff check api/agent/ api/routes/agent_dag*.py ...` | All checks passed |
| 2026-09-07 | config 一致性 | `pytest tests/test_config_validate.py` | 20 passed |
| 2026-09-07 | 真实 E2E | uvicorn:8102 + mock solver:8002 | plan→run→轮询 succeeded；bogus 422；cycle 422；404；扇出成功；/v1/agent/health+skills 无回归；/metrics agent_* 启动即注册 |

## 四、审查发现与闭环

- R1（本轮）：`api.routes.agent_dag_store` 包级属性被 `_common re-export` 遮蔽 → 改用 `.dag_run_store` 实例方法（`_STORE`），cerebrum 已教训建档
- R2：planner 真实 LLM 路径先用真 `registry` 单例（bootstrap 触碰 `registry.providers` 破坏注入 Mock）→ 改为有单例直接取、无单例才 bootstrap
- R3：DAG 引擎并发并行时 skip 判定竞态（预标记无法预知重试结果）→ 改为依赖终态实时判定（`_run_node` 内）
- R4：config 新字段与 `.env.example` 双向一致性（`test_config_validate` 拦截）→ 已同步生产/开发模板
- R5：`agent/routes.py` 未 import metrics → 指标要等首次 LLM 调用才注册 → 加 `from . import metrics`（F401 noqa）

## 五、阻塞项 / 待办

- **BLOCKED**：GitHub Release 创建需 PAT（`gh` CLI 未装、环境无 `GH_TOKEN`）。git push 用现有 GCM 凭据可完成；Release 需用户到 github.com/settings/tokens 提供 `repo` 权限 token 或手动创建。
- R1 旧档案：GitHub PAT 泄露轮换仍为社区操作（§32.2 R1），不因本轮解除。
- P3-DAG：前端 DAG 可视化、SQLite 持久化 run、MCP server 化（v9.0.0-B）——本轮不做，立项为后续。

## 六、下一步

1. 文档同步（下一步改进指南.md §6.1/§32 回写 + README 补 DAG 端点）
2. `git add` 本轮变更 → commit（约定式 `feat(v9.0.0): smart agent DAG orchestration`）→ tag `v9.0.0` → push origin main
3. Release 待 PAT（用户操作）