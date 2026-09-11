# v12.0.0 发行说明

> 发布时间：2026-09-12 | commit `cf471a0` | tag `v12.0.0`（历史 tag `v11.0.0` 补打于 `b46c5f5`）

## 主题：MCP 协议化 + 付费红线代码化 + 技能可发现性

### 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **MCP 协议化**（P1-M1） | `api/mcp/` 新包：`POST /v1/mcp` JSON-RPC 2.0 单端点（initialize / tools/list / tools/call / ping / 通知 202）；5 工具白名单：skills_list、skills_get、dag_plan、dag_status（只读）+ generate_image（受控生图，Mock 优先）；完整错误码契约（-32600/-32601/-32602/-32700） | `IF_MCP_ENABLED=0` |
| **硬预算门禁**（P1-M11） | `api/agent/budget_guard.py`：dispatch 前成本估算 + 三态模式（off/observe/enforce）；enforce 超预算 402；预算口径 = `IF_COST_BUDGET_USD` − 当日 chat_usage 花费；接线 image 真实付费路径 | `IF_BUDGET_GUARD_MODE=off` |
| **Fence 清洗层**（P1-M10） | `api/utils/fencing.py`：四类威胁清洗到不动点（零宽/bidi/变体选择符、C0/C1 控制符、伪造角色边界、伪造工具标签）；`sanitize_value` 递归 dict/list | `IF_FENCING_ENABLED=0` |
| **单技能详情端点**（P1-M5） | `GET /v1/agent/skills/{name}`（body 预览）；`GET /v1/agent/skills` 补齐 `IF_AGENT_SKILLS_ENABLED` 开关（此前 docstring 声明未实现） | `IF_AGENT_SKILLS_ENABLED=1` |
| **场景技能** | `api/skills/ecommerce/SKILL.md`（电商视觉文案 SOP：转化驱动力诊断/Campaign Style Lock/五维自审）+ `api/skills/ppt/SKILL.md`（PPT 大纲生成） | — |
| **E2E 探针** | `scripts/e2e_v12.py`：一体化真实 HTTP 验收（12 项断言） | — |

### 修复

- **发版补账 P0**：版本号全链 10.0.0 → 12.0.0（12 处）+ `desktop/package.json` 补 name/version 字段 + frontend/landing dist 重建
- **config 收敛 P0**：`IF_MOCK_UPSTREAM` 进 Settings 工厂；agent 五文件运行时读取统一走 `get_settings()`（测试钩子 `reset_settings()` 生效）
- `test_config_validate` 双向一致性闭环：3 个新开关同步进 `deploy/.env.example` + `.env.production.example`

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `pytest -m "not integration and not chaos and not slow"` | **2004 tests, 0 failed, 0 error, 1 skip** |
| ruff | `ruff check api/ tests/ scripts/` | 0 error |
| 真实 E2E | `python scripts/e2e_v12.py` | **12/12 PASS**（含 MCP 三工具、DAG run 全节点 succeeded） |
| 契约测试 | `pytest tests/test_openapi_contract.py` | 20 passed（版本注入验证） |

付费红线：全部验证走 `IF_MOCK_UPSTREAM=1`，零真实付费上游调用。

### 升级说明

- 新增 3 个环境变量（均缺省关闭，零行为变化）：`IF_MCP_ENABLED` / `IF_BUDGET_GUARD_MODE` / `IF_FENCING_ENABLED`
- 生产建议：`IF_FENCING_ENABLED=1` + `IF_BUDGET_GUARD_MODE=enforce`（需同时配置 `IF_COST_BUDGET_USD>0`）
- MCP 开启前建议过一遍工具白名单评估（对齐 OWASP-MCP hard-gate：先只读，受控生图按需）

### 遗留（v12.0.1 待办）

- 自反思 critic 循环深化（critic 节点已在 DAG/规划器中，反思-重生成闭环待做）
- 流式工具调用循环（`_extract_tool_candidate` 复用）
- human_input WS 真通道（`ws_events.py` 底座已备）
- 前端 reactflow 节点图 + black-box 推理轨迹面板
- GitHub Release 页面创建（gh CLI/token 缺失，tag 已推远程）
