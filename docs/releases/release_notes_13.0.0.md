# v13.0.0 发行说明

> 发布时间：2026-09-15 | 基于 v12.1.0（`19d66ff`）| 主控代理多子代理并行落地：审批持久化/鉴权 + DAG 记忆链与断点续跑 + MCP 预算门禁 + 前端反馈态 + flaky 根治

## 主题：把 v12.0.2 遗留闭环，补齐 DAG 编排的"记忆、续跑、护栏"，并根治全量 flaky

### 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **审批收件箱 SQLite 持久化**（P0-1） | `api/agent/human_inbox.py` 重建：同步 `sqlite3` + WAL + `isolation_level=None` + 内存热缓存；`get/reset_human_inbox` 工厂；重启实例（同 db_path）历史审批可查（重启后 `GET /v1/agent/human-inbox` 不丢）；`tests/test_human_inbox_persist.py` 14 用例（含重启/并发写/路由鉴权） | `IF_HUMAN_INBOX_DB=data/human_inbox.db` |
| **审批决策端点管理 Key 鉴权**（P0-2） | `POST /v1/agent/human-inbox/{req_id}/decision`（写操作）挂 `check_admin_key`（`IF_ADMIN_KEYS`，未配置默认 403；本地运维 `IF_ADMIN_KEY_OPEN=1` 放行）；列表 GET 保持公益只读 | 复用 `IF_ADMIN_KEYS` |
| **intent embedding 双路**（P0-6） | `api/agent/intent.py` 规则正则 → **embedding 相似度**（复用 `api/vector/embed.py`，5 类意图原型向量）→ LLM 兜底三段式；规则未命中时 ≤0.55 阈值降级 LLM 不崩 | `IF_INTENT_EMBED_THRESHOLD=0.55` |
| **DAG memory 节点读写**（P0-5） | `_exec_memory(op=read/write)`：write→`MemoryStore.observe`（L0），read→`query` L1→L0 兜底返回 `memory=read(n条)`；`execute_node` 透传节点 `config/info` 子键（scene/op） | — |
| **DAG 断点续跑 + 节点轨迹**（P0-7） | `execute_run` 增 `on_trace` 轨迹回调 + `node_traces` 表（append-only，`GET /v1/agent/dag/{run_id}` 回填 `nodes[].traces`，重启重建）；`POST /v1/agent/dag/{run_id}/resume` 幂等续跑（已 succeeded 节点不重跑；内存 store 后端） | `IF_DAG_RESUME_ENABLED=0` |
| **MCP 预算门禁**（P1-9） | `api/mcp/tools.py` `TOOL_PROVIDER_MAP` + `budget_guard.estimate_tool_cost`（`generate_image=0.04` 等）+ `guard_and_run` 统一闸口；enforce 超预算返回 JSON-RPC error（code -32000，不 500）；审计 `action=mcp.tool.call` | 复用 `IF_BUDGET_GUARD_MODE` |
| **前端统一按钮反馈态**（P1-13） | `frontend/src/components/ui/Button.tsx`（variant/size/loading spinner + `aria-busy` + disabled 防重复）；Generate/Agent/ChatPlayground 三页提交流程接入「提交中…」 | — |

### 修复（flaky 根治，基线 3 连 0 failures）

- **`test_ttl_expiry_allows_request` / `test_auto_block_after_repeated_429` `database is locked` 根治**（P0-3）：根因 = `memory.py`/`human_inbox.py` 同步 `sqlite3` 连接缺省 fallback journal（写者互斥窗口拉长）+ `consolidation` 常驻循环（300s）与 ip_blocklist 共享库跨用例写锁竞争。修复：两 store `_conn` 改 `isolation_level=None` + WAL + `busy_timeout=30000`（对齐主流程 Do-Not-Repeat#1）；conftest 双保险关闭 consolidation 常驻（env + 模块常量同步）。**全量单测 3 连 = 2059/0/0/1 稳定**。
- critic 反思路径 Mock 确定性：`_exec_critic` 反思重生成 mock 优先走 `_exec_llm_stable`（付费红线零真实调用），测试显式 `IF_MOCK_UPSTREAM=1` + `reset_settings()`。
- E2E 审批段适配管理 Key：env `IF_ADMIN_KEY_OPEN=1` 开放模式 + 决策头带 Key（12a/12b 恢复 PASS）。
- 版本号全链 12.1.0 → 13.0.0（后端 6 文件 + frontend/landing/desktop/README/E2E 断言）+ **frontend/landing dist 重建**。

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `pytest -m "not integration and not chaos and not slow"` | **2070 passed / 0 failed / 0 error / 1 skipped** |
| 集成测试 | `pytest tests/integration/`（mock cf_solver） | **49 passed / 0 failed** |
| 混沌测试 | `pytest tests/chaos/` | **5 passed / 0 failed** |
| ruff | `ruff check api/ tests/ scripts/` | 0 error |
| 前端 | `npm run test -- --run`（vitest） | **255 passed (22 files)** |
| 前端 build/tsc | `npm run build` + `npx tsc --noEmit` | 0 error |
| Playwright 探针 | `npx playwright test e2e/`（dev server） | 1 passed + 明暗截图 |
| 真实 E2E | `python scripts/e2e_v12.py`（全程 Mock） | **14/14 PASS** |
| 版本契约 | `test_openapi_contract.py` | 全过（dist 重建后） |

付费红线：全程 `IF_MOCK_UPSTREAM=1`（mock cfsolver 本地假求解器），零真实付费上游调用。

### 新增（v13 后续批次）

| 项 | 内容 | 开关 |
|---|---|---|
| **DAG 失败可重试**（P2-17） | Agent 页 failed/partial 终态显示「重试」按钮：优先调 `POST /v1/agent/dag/{run_id}/resume`，404/未启用降级 runDag 同参数重跑 | — |
| **成本仪表增强**（P2-16） | Costs 页「按提供商/按模型」视角切换（`aria-pressed`）+ 导出 CSV（UTF-8 BOM、RFC 4180 转义、两维度合并降序） | — |
| **DAG 记忆链测试**（P0-5 补） | `test_dag_memory_chain.py` 7 用例（read/write/config 子键/异常注入不崩） | — |
| **consolidation 生命周期测试**（P1-10 补） | `test_lifespan_consolidation.py` 4 用例（loop start/stop/cancel 不泄漏 CancelledError） | — |
| **Playwright 视觉探针**（P1-14） | `frontend/e2e/agent.spec.ts`：Agent 页渲染 + 明暗主题对比 + 重试按钮可见性；截图 gitignore | — |
| **a11y 断言**（P2-15） | 重试按钮 role/tagName、成本切换 aria-pressed、resumeDag 契约，共 +7 用例 | — |

### 集成修复（v13 后续批次，跨文件顺序污染根治）

- conftest `IF_MEMORY_CONSOLIDATION_ENABLED` 0→1（observe 端点此前 403「记忆子系统未启用」），常驻 consolidate 改 `CONSOLIDATION_INTERVAL_SECONDS=inf` 等效关闭（observe/query 可用，后台循环不竞争写锁）。
- agent_e2e 4 用例 `monkeypatch.setenv` 后补 `reset_settings()`（Settings 工厂缓存固化 mock=1 的经典串扰，memory 踩坑#1 同源）。
- intent 规则 '画一只' 增强后收窄为 `画.*(猫|狗|人|风景)`（'画一个电商主图' 归 ecommerce 规则，避免 image 规则吃掉电商 prompt）。
- conftest 模块级（api import 前）`setdefault IF_ACCOUNT_AUTO=0` + api 已 import 时同步 `_cfg.ACCOUNT_AUTO=False`（import 期固化 True → nanobanana 误可见，v7.7 已知预存根治）。
- vitest `exclude: e2e/**`（Playwright Test 不允许被 vitest import）。

### 升级说明

- 新增环境变量：`IF_HUMAN_INBOX_DB`（审批库路径）/ `IF_INTENT_EMBED_THRESHOLD`（embedding 命中阈值）/ `IF_DAG_RESUME_ENABLED`（断点续跑，缺省 0）。均已在 `deploy/.env.example` 同步。
- **审批决策端点为写操作，生产必须配 `IF_ADMIN_KEYS`**（未配置默认 403 拒绝，更安全）；`IF_ADMIN_KEY_OPEN=1` 仅限内网/本地运维。
- memory/human_inbox 连接语义对齐 WAL + autocommit（无行为变化，仅并发写锁窗口缩短）。

### 遗留（下轮候选）

- GitHub Release 页面创建需 PAT（本机 gh CLI 未装 / GH_TOKEN 未设；tag `v13.0.0` 已推远程，Release 需用户配置 token 后补发）
- DAG resume 仅内存 store 后端（sqlite 后端返回 400，续跑需反序列化快照，属增强）
- intent embedding 为 hash 桶字面重合（非语义向量）；原型向量可扩展多原型取 max
- 前端真实浏览器视觉验证待 Playwright 环境（jsdom 结构断言已覆盖）
