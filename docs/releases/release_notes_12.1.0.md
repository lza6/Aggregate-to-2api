# v12.1.0 发行说明

> 发布时间：2026-09-12 | 基于 v12.0.0（`cf471a0`）| 智能体深化：反思闭环 / 工具循环 / 人机审批 / DAG 可视化

## 主题：让 agent 真正"反思、用工具、等人拍板"，并把黑匣子打开

### 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **自反思 critic 闭环**（T1） | `_exec_critic` 终检 fail 时按 issues **单轮修正重生成**（`critic=reflection ... regen:` 输出；仅一轮防震荡），对齐 hermes-self-evolution 反思式修正 | `IF_CRITIC_REFLECTION_ENABLED=1` |
| **LLM 工具调用循环**（T2） | `_exec_llm` 响应含 `[tool:名字]` 时自动执行本地 skills 工具并把结果回填下一轮（上限 `IF_LLM_TOOL_ITERATIONS` 轮，0=关闭，防死循环） | `IF_LLM_TOOL_ITERATIONS=2` |
| **human_input 审批真通道**（T3） | `api/agent/human_inbox.py` 审批收件箱 + `api/routes/agent_human.py` 三端点：`GET /v1/agent/human-inbox`（列表）、`POST .../{req_id}/decision`（approve/reject 幂等决策）；DAG human_input 节点真通道等待审批（超时降级 timeout 继续下游）；DAG 引擎向 state 注入 `run_id`（审批关联 run，纯增量） | `IF_HUMAN_INPUT_ENABLED=0` |
| **前端 DAG 节点图**（T4） | `frontend/src/components/DagGraph.tsx`：SVG 分层拓扑图（最长路径分层/状态着色/箭头边/running 呼吸动画/键盘可达），替代 NodeRow 递归缩进列表 | — |
| **black-box 推理轨迹面板**（T4） | 点击节点显示完整推理过程：prompt 全文 / result 全文 / error 红底 / attempt / 耗时 / model / condition / 依赖——小白能看到每步被喂了什么、产出了什么 | — |
| 前端契约补齐 | `DagNodePublic` 补 `condition` 字段（对齐后端 public_state） | — |

### 修复

- human_input 审批请求 run_id 关联缺失（E2E 12a/12b 暴露）→ DAG state 注入 `run_id` 全链传递
- T2 工具循环组合跑 mock 缓存污染（测试显式 `IF_MOCK_UPSTREAM=0` + `reset_settings()`）
- 版本号全链 12.0.0 → 12.1.0（13 处含 MCP serverInfo）+ frontend/landing dist 重建

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `pytest -m "not integration and not chaos and not slow"` | **2021 tests, 0 failed, 0 error, 1 skip**（两次确认） |
| ruff | `ruff check api/ tests/ scripts/` | 0 error |
| 前端 build | `npm run build`（frontend/） | ✓ 0 error（Agent chunk 9.29 kB） |
| 前端单测 | `npm run test -- --run` | **239 passed (239)**（含 DagGraph 6 新用例） |
| 真实 E2E | `python scripts/e2e_v12.py` | **14/14 PASS**（新增：human_input 审批决策 + 审批后 run succeeded） |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，零真实付费上游调用。

### 升级说明

- 新增 4 个环境变量：`IF_CRITIC_REFLECTION_ENABLED=1`（默认开，critic fail 路径增强）/ `IF_LLM_TOOL_ITERATIONS=2` / `IF_HUMAN_INPUT_ENABLED=0` / `IF_HUMAN_INPUT_TIMEOUT=60`
- human_input 审批端点当前公益开放（guard_chat_request 限流）；**生产建议改管理 Key**（审批是写操作）
- 审批收件箱为进程内存储（与 DAG 内存 store 同级生命周期）；SQLite 持久化留 v12.0.2（run 本身已落 dag_runs.db）

### 遗留（v12.0.2 候选）

- 审批收件箱 SQLite 持久化（重启可查历史审批）
- intent embedding 路（补 mcp-agent 双路的 embedding 侧）
- GitHub Release 页面创建（gh CLI/token 缺失；tag `v12.1.0` 已推远程）
- 前端真实浏览器视觉验证（明暗两主题；jsdom 已验结构/坐标属性）
