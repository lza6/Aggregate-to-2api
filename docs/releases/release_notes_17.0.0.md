# v17.0.0 发行说明

> 发布时间：2026-09-18 ｜ 基于 v16.1.0（`32390c3`）｜ 主题：自我进化 + 体验闭环

## 主题：从「能用/好用」到「自我进化 + 多场景」

v17 落地主线：技能沉淀闭环（保存 DAG run 为个人技能）+ 安全闸门前置（技能静态扫描）+ 黑匣子打开（教学化 explain）+ 记忆可解释（为什么命中）+ 桌面启动修复 + 电商合规护栏。

### 新增（B1a 技能工程化四件套）

| 项 | 内容 |
|---|---|
| 四件套规范 | 5 技能（critic/ecommerce/image_quality/ppt/prompt_refine）补齐 `SKILL.md frontmatter(name/description/version/security/inputs/outputs) + schema.json + validate.py + expected_results/`（黄金样例） |
| 一键门禁 | `scripts/validate_skills.py`（`--strict` CI 口径 / `--fix` 生成骨架），校验 frontmatter/schema/validate 执行/黄金样例，退出码非零即失败 |

### 新增（B1b 技能安全扫描闸门，SkillSpector 对标）

| 项 | 内容 | 开关 |
|---|---|---|
| 4 类静态扫描 | `scripts/skillspector.py`：prompt 注入 / 数据外泄 / 提权破坏（复用 `is_destructive_command` 共享黑名单）/ 供应链；0-100 风险分 + baseline 白名单 + `--json` | `IF_SKILL_SCAN_ENABLED`(1) |
| 沉淀前置闸门 | `api/agent/skill_scan.py` 封装 `scan_skill(content) -> SkillScanResult`，risk_score >= 阈值拒绝入库 | `IF_SKILL_SCAN_REJECT`(60) |

### 新增（B2 技能沉淀闭环·手动收藏 MVP，SkillClaw 对标）

| 项 | 内容 | 开关 |
|---|---|---|
| 保存为技能 | `POST /v1/agent/skills/save-from-run`（run_id/name/prompt_template/params/notes；保存前强制过扫描） | `IF_SKILL_SEDIMENT_ENABLED`(0) |
| 我的技能 | `GET /v1/agent/my-skills`（approved 只读） | — |
| 管理面 | `GET /v1/admin/skills` + `POST/DELETE /v1/admin/skills/{id}/approve|reject|delete`（admin key） | — |
| 存储 | 独立 SQLite `data/skills.db`（skills + skill_versions 版本化/checksum） | `IF_SKILL_SEDIMENT_DB` |
| 前端 | Agent 页成功 run 展开「保存为技能」按钮 + 「我的技能」区块 | — |

### 新增（B4 记忆可解释，mem0 explain 对标）

- `MemoryStore.query()` 每条记忆返回 `explain`（importance 档 / 访问新鲜度 / 未被取代），`/v1/agent/memory` 响应透传。

### 新增（P1-7 MCP 渐进工具暴露，smart-mcp-proxy 对标）

- 工具 `intent`（read/write/destructive）+ MCP 2025-06-18 `annotations` 完整映射（readOnlyHint/destructiveHint/idempotentHint/openWorldHint）
- `retrieve_tools(query)` 关键词过滤 + `describe_tool(name)` 详情（供渐进暴露/审计）

### 新增（P2-1 求解器加固，captcha-solver 对标）

- cf_clearance 回放元数据：`bound_domain`/`created_at` 写入求解结果 + `validate_replay()`（domain/UA/过期校验）；SSRF 逐 IP 守卫（既有实现）由测试锁定。

### 新增（B5b 桌面启动脚本修复）

- `desktop/start-desktop.bat`：`mock|real` 模式**真实生效**（此前 launcher 固定 mock）；cf_solver 就绪轮询（30×2s + 日志尾部）；healthz 失败输出状态码/响应体/launcher；旧 backend 窗口清理（标题+端口双保险）；`desktop/scripts/verify-start-modes.ps1` 静态验证 12 项 PASS。

### 新增（B3 教学化，learn-agent 对标）

- `api/agent/explain_templates.py`：8 类 DAG 节点大白话释义（what/why/io）+ 场景释义；前端 DagGraph 节点 `<title>` tooltip（hover 即学）。

### 新增（P1-5 电商合规护栏，commerce-agents 对标）

- `api/skills/ecommerce/fence.py`：绝对化用语/医疗功效红线拒绝 + 数据宣称提示 + `FenceResult`（替代方向建议），纯静态零 LLM。

### 修复

| 项 | 内容 |
|---|---|
| 技能单例运行时引用 | `agent_skills_admin` 改运行时取模块属性（`reset_store()` 后路由即用新实例，测试/配置切换不再串扰） |
| DAG image mock 测试 | `test_dag_multimodal_chain` 的 env patch 需 `reset_settings()`（Settings 缓存语义） |
| env.example 漂移 | 补齐 `IF_SKILL_SCAN_ENABLED/IF_SKILL_SCAN_REJECT/IF_SKILL_SEDIMENT_ENABLED/IF_AGENT_EXPLAIN_ENABLED`（config 双向校验闭环） |
| 前端保存 body | `saveSkillFromRun` 改 `JSON.stringify(payload)` |

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端新增测试 | B1a 14 + B1b 33 + B2 14 + B4 7 + P1-7 9 + P2-1 12 + B3 6 + P1-5 8 = **103** | 全绿 |
| 后端回归 | a-c/d/l-o/t-w 前缀 + batch 90 文件 + config/captcha/memory/mcp/skills/dag 专项 | 全绿（1 项 provider_probe loop flaky 与本次改动无交集，单跑全绿） |
| 前端 | `vitest run`（threads 池 + testTimeout=20000） | **296 passed / 28 files**（较 v16.1 增 3） |
| 前端构建 | `tsc -b && vite build` | 0 error，dist 重建 |
| landing 构建 | `vite build` | 0 error，dist 重建 |
| Lint | `ruff check api/ scripts/` | 0 error |
| 启动脚本 | `verify-start-modes.ps1` | 12/12 PASS |
| 版本 | 全链 15 处 → **17.0.0**（openapi + mcp serverInfo + e2e 契约同步） | — |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，0 真实付费上游调用（技能沉淀/扫描/教学化/合规均为本地纯函数或 Mock）。

### 升级说明

- **技能沉淀**：`IF_SKILL_SEDIMENT_ENABLED=0` 缺省关闭（零行为变化）；开启后 Agent 页保存按钮可用。
- **MCP**：tools/list 的 annotations 扩展为四字段（readOnlyHint 值不变，旧客户端兼容）。
- **cf_clearance**：求解结果新增 `bound_domain`/`created_at` 字段（追加，无破坏）。
- **桌面**：`start-desktop.bat real` 现真正关闭 mock（真实上游仍在预算/护栏内）；编码保持 GBK/CRLF。
- **待验证**：桌面真机 tauri build/NSIS 自升级（无 Rust 工具链环境）；真实视频上游；GitHub Release 需 token（已备 release notes）。