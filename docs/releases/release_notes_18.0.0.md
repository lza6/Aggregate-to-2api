# v18.0.0 发行说明

> 发布时间：2026-09-19 ｜ 基于 v17.0.0（`e0ee3b8`）｜ 主题：自动进化 + 多场景扩展

## 主题：从「手动沉淀」到「自动进化」

v17 落地手动基座（技能四件套/安全扫描/沉淀/教学化）；v18 主线：技能**自动**沉淀（证伪实验先行 + 重放验证）、记忆 RRF 检索融合（压测决策）、MCP 渐进暴露落地、PPT 可编辑产物、视频 Mock 任务模型。

### 新增（P0-1 技能自动沉淀，SkillClaw/SkillOpt 对标）

| 项 | 内容 | 开关 |
|---|---|---|
| 证伪实验先行 | `scripts/sediment_probe.py`：5 好/坏技能重放区分度 **0.306 > 0.15** → 自动沉淀可尝试（Mock 确定性评估器，零 LLM） | — |
| 自动沉淀 | `api/agent/skill_sediment_auto.py`：DAG run succeeded 终态 → 候选生成（规则模板；仅 `IF_SKILL_AUTO_BUDGET_USD>0` 才预算门禁 LLM）→ `scan_skill` 闸门 → 重放 gate_score → 草稿入库（source=auto） | `IF_SKILL_SEDIMENT_AUTO`(0) |
| 四重前置 | 开关/状态/幂等（source_run_id 唯一）/上限（`IF_SKILL_MAX_DRAFT`=50） | — |
| 挂载 | `agent_dag.py` run 终态 `maybe_sediment_run`（失败静默降级） | — |
| 验证 | `tests/test_sediment_probe.py` 6 + `tests/test_skill_sediment_auto.py` 9 | 全绿 |

### 新增（P0-2 记忆 RRF 检索融合，mem0/ai-memory 对标）

- `mem_atoms_fts` FTS5 虚表 + 同步触发器（INSERT/UPDATE/DELETE 幂等）+ `_rrf_merge` 纯函数（RRF k=60）
- `query(mode="auto|plain|rrf")` 双模式：`IF_MEMORY_RRF=0` 缺省纯 SQL 零回归；rrf 双路（importance + BM25）融合，结果不足时 FTS 扩充，explain 追加「RRF 融合命中」，FTS 不可用自动降级
- 压测 `scripts/bench_memory_rrf.py`：1000 条 P95 plain=110.9ms / rrf=126.3ms（本机慢 + touch 开销，未达 50ms 目标）→ **按 RT-4 决策保持纯 SQL 缺省，RRF 实现留开关可回滚**（诚实记录）
- 验证：`tests/test_memory_rrf.py` 8 全绿

### 新增（P1-3 MCP 渐进暴露落地，smart-mcp-proxy 对标）

- `retrieve_tools`/`describe_tool` 注册为 MCP 工具（read intent，tools/list 8 工具）；`IF_MCP_TOOL_APPROVAL=0` 缺省全可见零回归
- 审批流：`/v1/admin/mcp-tools`（清单含 expose 状态）+ `POST /{name}/expose|hide`（admin key）；开关开时新工具（expose=False）需审批后对客户端可见
- 验证：`test_mcp_tools_meta.py` 14 全绿

### 新增（P1-2 PPT 可编辑产物生成，ppt-master 对标）

- `api/skills/ppt/generate_pptx.py`（python-pptx 1.0.2，OOXML 可编辑）：大纲 → PPTX bytes（封面 + 一页一观点 + 备注）
- `POST /v1/skills/ppt/generate`（`IF_PPT_GENERATE=0` 缺省关）；requirements.txt 声明 python-pptx
- 验证：`tests/test_skill_ppt.py` 5 全绿（PK 头 + slide 数 + 备注）

### 新增（P1-1 视频 Mock 任务模型，zack-d/Pixelle 对标）

- `api/providers/video_mock.py`：submit→task_id，poll 按任务 duration 推进 progress（queued→rendering→completed + mock URL）
- `POST /v1/video` + `GET /v1/video/{task_id}`（`IF_VIDEO_ENABLED=0` 缺省关）
- SSE 逐帧/DAG video 节点/真实 falai 动作族后置（本版交付可用 Mock 任务模型，诚实标注）
- 验证：`tests/test_video_tasks.py` 5 全绿

### 修复

- `api/routes/video.py` 相对导入错误（`.video_provider` → `..providers.video_provider`，曾致 app 无法 import）

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端新增测试 | probe 6 + auto 9 + rrf 8 + mcp 14 + ppt 5 + video 5 = **47** | 全绿 |
| 组合回归 | 本批 10 文件 114 用例 | 全绿 |
| 前端 | vitest 295/296（CostsPage recharts 既有环境 flaky，单跑 3/4） | 前端零改动 |
| Lint | `ruff check api/ scripts/` | 0 error |
| **真实 E2E** | `scripts/e2e_v12.py`（扩至 38 段） | **38/38 PASS**（含 17 视频/18 PPT/19 MCP 渐进暴露） |
| 版本 | 全链 14 处 → **18.0.0** + dist 重建 | 契约同步 |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，0 真实付费调用（自动沉淀 LLM 摘要预算缺省 0；视频/PPT Mock）。

### 升级说明

- **自动沉淀**：`IF_SKILL_SEDIMENT_AUTO=0` 缺省关；开启后 succeeded run 自动生成草稿（扫描闸门 + 重放分 + 审批前置），与 v17 手动收藏共存。
- **记忆**：`IF_MEMORY_RRF=0` 缺省纯 SQL 零回归；开启后 rrf 融合（FTS5 虚表自动建）。
- **MCP**：tools/list 现 8 工具（新增 retrieve_tools/describe_tool）；`IF_MCP_TOOL_APPROVAL=1` 时新工具需 admin 审批。
- **PPT/视频**：端点缺省 404（`IF_PPT_GENERATE=1`/`IF_VIDEO_ENABLED=1` 开启）。
- **待验证**：桌面真机 tauri build/NSIS 自升级（无 Rust 环境）；i18n 9 页全覆盖（v17 已接 6 区域 + Agent，9 页替换为独立批次）；SSE 逐帧/真实视频 provider。