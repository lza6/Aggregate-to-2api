# v14.0.0 发行说明

> 发布时间：2026-09-15 | 基于 v13.1.1（`a4dfcd8`）| 审批导出/历史 + DAG 续跑 sqlite 化 + 记忆 supersede 巩固蓝本

## 主题：让审批可导出、让续跑落库可恢复、让记忆"新压旧"真正生效

### 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **审批导出 + 历史分页**（P1） | `HumanInbox.export(format=csv\|json)`（CSV：UTF-8 BOM + RFC 4180 转义 + ISO 时间；JSON：list[dict]）；`GET /v1/agent/human-inbox/export?format=csv\|json`（text/csv attachment / application/json）+ `GET /v1/agent/human-inbox/history?status&limit&offset`（分页 items/count/total）；两写读端点均挂管理 Key（`check_admin_key` scope="admin-human-inbox"） | 复用 `IF_ADMIN_KEYS` |
| **DAG 续跑 sqlite 化**（P2） | `DagRunSqliteStore.restore_run(run_id)` 从 nodes_json 快照反序列化 `DagRun`（节点/状态/attempt/condition/depends_on 还原）；`POST /v1/agent/dag/{run_id}/resume` 对 sqlite 后端恢复可续跑（不再 400）；未持久化执行配置（fail_fast/max_parallel）回退引擎默认 | 复用 `IF_DAG_RESUME_ENABLED` |
| **记忆 supersede 巩固蓝本**（P3） | mem_atoms 加 `superseded_by` 列（幂等迁移）；`consolidate` 生成同 (user_key, scene, content) L1 时标记旧记录 superseded；`query(L1)` 默认过滤 superseded（旧数据列缺失降级不过滤不崩）；`apply_decay()` hot/warm/cold 三档（hot <1d 提 importance、cold 超阈值淘汰、warm 不动），可挂 consolidation loop | `IF_MEMORY_APPLY_DECAY=0` |

### 修复（子代理产物复核 + 组合回归根治）

- **`sqlite3.Row` 无 `.get` 兼容**：P3 的 `r.get()` 破坏既有 memory 测试（6 个）→ 改回 `r["key"] if "key" in r.keys() else None`（Row 支持 in 判定）。**全量 2104/0 回归绿**。
- **`reset_human_inbox` 未同步模块级单例**：`api/routes/agent_human.py`/`agent_dag_exec.py` 用 `from ..agent.human_inbox import human_inbox`（import 期值拷贝）→ reset 重建 `_human_inbox` 后必须同步模块级 `human_inbox` 变量，否则 export/history 端点读旧库（跨用例残留 72 条）。**export/history 34 用例全绿**。
- ruff 清零：SIM118/SIM401（`in r.keys()` → `in r`；`r.get` → `r.get(key, None)` 兼容性以 Row 语义为准）。

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `pytest -m "not integration and not chaos and not slow"` | **2104 passed / 0 failed / 0 error / 1 skipped** |
| 集成+混沌 | `pytest tests/integration/ + tests/chaos/`（mock cf_solver） | **54 passed / 0 failed** |
| 新测试 | `test_human_inbox_export.py`(12) + `test_dag_resume_sqlite.py`(12) + `test_memory_supersede.py`(10) | **34 passed / 0 failed** |
| ruff | `ruff check api/ tests/ scripts/` | 0 error |
| 真实 E2E | `python scripts/e2e_v12.py`（全程 Mock） | **14/14 PASS** |
| 版本契约 | `test_openapi_contract.py` + dist 重建 | 全过（14.0.0 全链） |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，零真实付费上游调用。

### 升级说明

- 新增环境变量：`IF_MEMORY_APPLY_DECAY=0`（apply_decay 默认关）。已在 `deploy/.env.example` 同步。
- 导出/历史端点为读操作但含管理面数据，生产必须配 `IF_ADMIN_KEYS`；`IF_ADMIN_KEY_OPEN=1` 仅限内网/本地。
- 现有 `mem_atoms` 表自动加 `superseded_by` 列（幂等迁移）；旧库无列时 query 降级不过滤。

### 遗留（下轮候选）

- GitHub Release 页面（需 PAT；tag 已推远程）
- intent embedding 语义向量升级（当前 hash 桶字面重合）
- `captcha 统一 solved 协议`（cf_clearance 与 turnstile 客户端统一返回协议，下下轮）
