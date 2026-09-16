# g01_agent_ai_a 组扫描报告（40 目录）

> 扫描方式：ls 结构 + README 首部定位 + 关键模块源码侦察（仅只读分析，未改动任何文件）
> 主项目对标：听风AI（FastAPI/SSE 图像+对话网关，agent 化：意图识别/编排/RAG/记忆/工具/审批/断点续跑/MCP/skills）
> 当前关注：①agent 深度优化（黑匣子打开/教学化/小白易用/沉淀用户 skills）②扩展场景（图片/视频/电商/PPT/多模态）③工程规范/交互/安全/性能

---

## 500-AI-Agents-Projects
- 定位：500+ AI Agent 项目与用例的策展集合（按框架/行业分类的教学仓库）
- 技术栈：多框架（LangGraph/CrewAI/AutoGen/Agno）Python 示例 + web 导航站
- 亮点：1) 每个 agent 有独立可运行目录（`agents/01-web-research-agent` 等 22 个）即插即用；2) `crewai_mcp_course/` 分课 MCP 教学；3) 按行业/框架双维度索引
- 对主项目价值：无价值（纯资源集合，非可移植实现）
- 借鉴点：无代码可迁移；仅可当「agent 用例清单」翻查
- 评分：1

## ARUNAGIRINATHAN-K__awesome-ai-agents-2026
- 定位：470+ agent 工具/框架的结构化导航站（Vercel + Next.js 应用）
- 技术栈：Next.js + data/categories.json + resources.json（结构化清单）
- 亮点：1) 结构化数据层（`data/*.json`）驱动分类浏览；2) `ARCHITECTURE.md`/`DATA_SCHEMA.md` 文档化数据模型
- 对主项目价值：无价值（资源导航）
- 借鉴点：无
- 评分：1

## Agent-Reach（= Panniantong__Agent-Reach 同一项目，见后者详细条目）
- 定位：给 AI Agent 一键装互联网能力的接入层（与 Panniantong 目录为同仓库重复副本）
- 技术栈：Python 3.10+ / rich CLI / channels 插件式
- 亮点：同 Panniantong 条目，见下
- 对主项目价值：直接借鉴（同 Panniantong 条目）
- 评分：4

## AgentK
- 定位：自演化 AGI——Agent 协作并自主构建新 Agent/工具以完成任务（LangGraph 之上）
- 技术栈：Python + LangGraph/LangChain + Docker
- 亮点：1) **kernel 最小自举设计**：Hermes(编排)/AgentSmith(架构师)/ToolMaker(造工具)/WebResearcher 四个最小 agent 构成内核；2) 自我演化的产物是「普通 python 文件」落在 `agents/` 与 `tools/` 目录，进度可 git 追踪、人类可贡献；3) 鼓励 agent 为自己写测试
- 对主项目价值：局部借鉴（自演化哲学与主项目「沉淀用户 skills + critic 自反思」同向）
- 借鉴点：把「演化产物落成可 diff 的普通文件 + 可追踪」原则迁移到主项目 skills 库（每次新技能沉淀成 SKILL.md 文件可审查可回滚，而非只存在记忆里）
- 评分：3

## Agent_Memory_Techniques
- 定位：30 个可运行 Jupyter 覆盖全部 agent 记忆技术模式的教程集（NirDiamant）
- 技术栈：Python + Jupyter（对话缓冲/滑动窗口/摘要/向量/知识图谱/情景/语义/程序性记忆、Mem0/Letta/Zep/Graphiti/LoCoMo 基准、遗忘与衰减、记忆路由/检索模式/生产记忆模式）
- 亮点：1) 按「决策树 + 学习路径」组织（`images/decision_tree.svg`）降低选型门槛；2) 编号目录 01-30 渐进教学；3) 覆盖记忆评估与基准（LoCoMo）
- 对主项目价值：扩展方向参考（主项目已有 L1-L3 记忆，可对照 13/14/15/19 号补全层级、整合、压缩、遗忘策略）
- 借鉴点：主项目记忆层可补「遗忘与衰减（forgetting/decay）」「记忆整合（consolidation）」「记忆压缩（compaction）」三条 L3 强化机制；教学化上可学其决策树呈现
- 评分：3

## AlekseiUL__gpt-image-2-5-agent-kit
- 定位：面向 agent/操作者的本地 GPT Image 2.5 提示词/参考图/生成/编辑工具包（非官方）
- 技术栈：Python 3.10+ / CLI（`gpt-image25-agent`）/ PIL / 本地 dry-run
- 亮点：1) **dry-run 评审**：先出 `--review-markdown`/`--json` 的完整计划（prompt/模型/参考角色/参数/输出路径）再实调，agent 可读；2) **sha256 不可变收据**：`receipts.py` 记录 prompt hash、refs hash、输出元数据（宽高/格式/字节/sha256），请求全链路可审计；3) 本地优先无 token 的 dry-run 默认
- 对主项目价值：直接借鉴（主项目图像主链路可加此模式）
- 借鉴点：①图像生成前加「dry-run 计划评审」工具，让 agent 在真实调用前审查 prompt/参数/参考图（正好契合付费 API 红线下的「先验证再调用」）；②给每次生成请求写不可变收据（prompt_sha256 + 参考图 hash + 输出 hash），落到审计表，实现图像调用全链路可溯源（黑匣子打开）
- 评分：4

## AutoAgent-main
- 定位：零代码、自开发的 LLM Agent 框架——纯自然语言构建 agent/tool/workflow（HKUDS）
- 技术栈：Python + meta_agent 自生成机制（agents/tools/forms XML）
- 亮点：1) **自然语言驱动构建**：`agents/meta_agent/agent_creator.py` 教 LLM 用 create_agent/read_agent/delete_agent/run_agent/create_orchestrator_agent 原子工具自主建 agent；2) **表单驱动（XML agent form）**：agent 定义是可解析的表单，创建/编辑/校验结构化；3) 多 agent 强制「先建齐 agents 再建 orchestrator」
- 对主项目价值：直接借鉴（教学化/小白易用方向核心参照）
- 借鉴点：①把「创建 agent/skill」也暴露成 agent 可用工具（如 create_skill/update_skill），让用户在对话中沉淀自定义 skills；②agent 定义表单化（frontmatter + 正文），让 LLM 生成的结构可解析、可校验、可回滚——迁移到主项目 skills 库的创建链路
- 评分：4

## CelestoAI__agentor
- 定位：构建/部署长运行 AI agent 的 Python 框架——持久、可观测、安全
- 技术栈：Python + FastAPI（完整兼容的 MCP Server 装饰器 API）+ LiteMCP
- 亮点：1) **Durable Runs**：每次 run 是 append-only 事件日志，进程崩溃可 `resume(run_id)`，已完成的 run 可 `fork()` 出独立新 run（保留全 trace 与模型推理）；2) Tool Search API 降低工具上下文膨胀；3) MCP & tool 安全（FastAPI 兼容 decorator API）
- 对主项目价值：直接借鉴（主项目「断点续跑 + MCP 服务端」的增强参照）
- 借鉴点：①断点续跑升级为 append-only 事件日志 + fork 语义（不只续跑，还能从任意已存 run 分叉出新 run，契合 agent 工作台「复制/重放」需求）；②MCP server 采用 FastAPI 装饰器 API 与主项目 FastAPI 栈天然同构
- 评分：4

## Claude-Code-Agent-Monitor
- 定位：Claude Code & Codex Agent 活动实时监控 Dashboard（Hook 系统直插追踪）
- 技术栈：Node.js/Express/SQLite(WAL)/WebSocket/React 19/Vite/Tailwind + Grafana/Prometheus 集成
- 亮点：1) **Hook 直插**：通过 Claude Code & Codex 原生 hook 采集会话/工具使用/子 agent 编排，无需侵入 agent；2) 实时 WebSocket 推送 + 告警 + 远程推送（web-push）；3) 指标丰富：token 用量/价格/任务进度/会话活跃（`server/lib/token-usage.js`、`scoped-stats.js`）
- 对主项目价值：局部借鉴（监控面板方向；主项目已有 15 页管理面板 + telemetry）
- 借鉴点：①hook 采集模式迁移：主项目 agent 编排用 SSE 事件流已覆盖，可补「token 用量/成本实时看板」与 WebSocket 实时推送；②告警规则（alerts）可借鉴到主项目成本/熔断告警
- 评分：3

## CommerceAgentBench
- 定位：评估 agent 能否完成长时程电商业务流程（非问答）的 benchmark（Accio/阿里国际）
- 技术栈：Python + pytest 式 harness + mock 服务（Shopify/Stripe/Notion/Gmail/Jira/Reddit 等 20+ 本地 mock）+ LLM judge
- 亮点：1) **状态级验证器**：`verifiers/` 每任务一个（shopify_admin_v2.py/alibaba_publish_v2.py 等），检查「最终状态是否真正改变」而非输出文本；2) **可复现**：每任务 fresh container + 轨迹/trajectory.py 归一化 + mock 服务模拟 SaaS；3) 107 任务分 CLI/浏览器/文件/API-MCP 四类
- 对主项目价值：扩展方向参考（主项目若要建设 agent 回归测试，此为其蓝本）
- 借鉴点：①「状态验证器 + mock 服务」模式迁移：主项目 agent 每类任务配 verifier 检查落库/文件/外部系统真实状态（与 EcomAgent harness 同思想）；②任务分面（CLI/浏览器/API/MCP）可作主项目 agent 测试分面
- 评分：3

## CowAgent
- 定位：开源超级 AI 助手（Agent Harness）——主动规划任务、控制电脑/外部服务、创建运行 Skills、知识库与长期记忆、自我演化
- 技术栈：Python + 多模型 provider（openai/claudeapi/deepseek/...30+）+ 多渠道 channel + SQLite + MCP
- 亮点：1) **Self-Evolution 引擎（最值得借鉴）**：`agent/evolution/executor.py` —— 空闲会话的转录交给「隔离 review agent」（仅限 read/write/edit/ls/memory_search 受限工具集）审阅，产出 `[SILENT]` 即不动；变更前对 MEMORY.md/记忆文件/skills 做快照（backup_id 可 undo），变更后向用户会话注入 `[EVOLUTION]` 说明；并发上限 2 + workspace 级锁防并发冲突；内置 skills 白名单保护不可被改；2) **触发策略**：`trigger.py` 空闲>=N 分钟 + 轮次阈值 或 上下文超 80% token 预算即触发（对齐上下文压力下 consolidation 的业界做法）；3) **skills 系统**：Skill Hub 一键安装 + skill-creator 对话式创建，SKILL.md frontmatter（name/description）解析触发；4) **Deep Dream 记忆蒸馏**：三档（上下文→daily→MEMORY.md）+ 夜间蒸馏 + 混合关键词+向量检索
- 对主项目价值：直接借鉴（「沉淀用户自己 skills + 自反思演进」方向的最佳范本）
- 借鉴点：①主项目 critic 自反思升级为「隔离 review agent + 受限工具 + 快照回滚 + [SILENT] 保守默认」；②触发条件改为「空闲 + 轮次阈值 或 上下文压力 80%」，避免每次对话都反思（省 token）；③skills 创作走 skill-creator 对话式流程并落成可审查文件；④保护内置 skills 不可被演化覆盖（白名单）
- 评分：5

## EcomAgent
- 定位：面向电商运营的通用 Agent Runtime——任务输入→上下文装配→模型决策→工具调用→权限确认→执行→结果，统一闭环
- 技术栈：Python + FastAPI + WebSocket + React/TS + pytest
- 亮点：1) **PreToolUse 权限管线**：`permission/pre_tool_use.py` 可插拔检查器链返回 ALLOW/BLOCK/ASK，READONLY/ASK/EXECUTE 三模式（mode_manager.py）——按操作读写属性自动放行/询问/拦截；2) **Execution Policy**：错误分类（CLIENT/BUSINESS/TRANSIENT/FATAL，`error_classification.py`）+ 仅瞬态重试 + 幂等键（写操作）+ 分级超时 + 结果校验；3) **契约式回归 harness**：`harness/assertions.py` 对 AgentEvent 事件流做期望轨迹断言（load_skill 首步/工具名参数子集/重试次数/权限 ASK 流程/complete 收尾）；4) **SKILL.md 渐进式披露**：`sources/skill_registry.py` 菜单常驻 name+description，正文 load_skill 命中才注入，内置只读+用户可建可停；5) 记忆：Claude Code 式 MEMORY.md 索引 + 独立记忆文件 + Mem0 式 ADD/UPDATE/DELETE/NOOP 整合判定 + 用户纠正语气词自动归 feedback 类
- 对主项目价值：直接借鉴（主项目 agent 化「工程规范/安全/测试」维度的最优范本，且同为电商场景）
- 借鉴点：①PreToolUse 检查器链迁移：主项目工具调用前走 规则/RBAC/模式门 链式决策（主项目已有审批，可补 ALLOW/BLOCK/ASK 三态管线）；②错误分类表迁移：主项目 retry_policy 已有瞬态/非瞬态分类，可对齐 409/422/429/5xx 映射；③契约式事件断言 harness 迁移：用主项目现有 SSE 事件流做「期望轨迹匹配」回归测试（比 E2E 更轻更稳）；④记忆整合判定器（默认规则版 + 可换 LLM 版）可作主项目 L1-L3 中间层
- 评分：5

## Farama-Foundation__MAgent2
- 定位：大量像素 agent 在网格世界对抗/竞争的多 agent 强化学习环境库
- 技术栈：Python + PettingZoo API + C++ 内核
- 亮点：1) 大规模多 agent（万人级）强化学习环境；2) 维护型 fork 的工程实践
- 对主项目价值：无价值（RL 环境，与主项目 agent 编排无交集）
- 借鉴点：无
- 评分：1

## Forsy-AI__biosecurity-agent
- 定位：围绕任意目标构建「活体生物安全世界」的 AI agent——持续追踪源、链证据、后台更新
- 技术栈：TypeScript/React + pnpm workspace + Playwright 测试
- 亮点：1) **目标中心世界模型**：targets→sources→entities/relationships→world synthesis→live watch，Observed/Inferred/Simulated 三类 claim 始终区分；2) **后台 watcher 持续更新** + 终端暴露每条处理 lane（discovery/retrieval/claim extraction/synthesis），证据全程可检视；3) **状态持久恢复**：退出后本地 runtime 恢复 targets/watchers/world；4) 本地优先、外部内容视为不可信、动作需显式授权
- 对主项目价值：扩展方向参考（「持续后台 agent + 证据可检视」模式）
- 借鉴点：①主项目 RAG/记忆可引入「claim 分级（观测/推断/模拟）」标签，回答中区分事实与推测（黑匣子打开）；②后台 watcher 模式迁移到主项目「定时 RAG 增量」等长任务
- 评分：3

## GenericAgent
- 定位：极简自演化自主 Agent——约 3K 行种子代码 + 9 原子工具 + 约 100 行 Agent Loop，控制浏览器/终端/文件/键鼠/屏幕/移动设备
- 技术栈：Python + llmcore.py(1.2K 行) + agent_loop.py(132 行) + TMWebDriver.py + 插件 hook
- 亮点：1) **设计哲学「不预载 skills，去演化」**：每次解决新任务自动把执行路径结晶成可复用 Skill，长期形成个人技能树；2) 极简核心：agent_runner_loop 一个循环 + handler dispatch（`do_<tool>` 方法反射绑定），每 10 轮重置工具描述防上下文膨胀
- 对主项目价值：局部借鉴（教学化方向理念印证：自演化产出 skills）
- 借鉴点：①「任务执行路径 → 自动结晶为 Skill」可作主项目 skills 沉淀的自动化路径；②极简 loop 的教学价值：向小白用户展示 agent 工作台时可用「~100 行循环」做可解释教学
- 评分：3

## HKUDS__VideoAgent
- 定位：一体化视频智能框架——理解、编辑、生成（含 CosyVoice/fish-speech/seed-vc 音频 + videorag 检索）
- 技术栈：Python + 多模态工具集成（VideoEdit/ + tools/ 子模块）
- 亮点：1) 理解-编辑-生成三合一管线；2) VideoRAG 视频检索增强
- 对主项目价值：扩展方向参考（视频场景扩展）
- 借鉴点：主项目若扩视频生成，可参照其「工具子模块 + 需求解析」组织（先解析需求→选理解/编辑/生成路径）
- 评分：2

## LeAgent
- 定位：开源桌面 AI agent——流式 think-act 循环 + agentic 可视化工作流（ReactFlow DAG）+ 生成式 UI + 100+ 离线工具
- 技术栈：Python 3.11 后端（SQLite/PostgreSQL）+ React 19/ReactFlow 前端 + Agent Skills v1.0
- 亮点：1) **生成式 UI**：agent 流式输出声明式 UI 树（SlideDeck/KPI Board/Gallery/Stepper），`services/gen_ui/schema.py` 定义，docx/pptx/print_renderer 导出 PDF/PPTX——「聊天内出幻灯片再导出」直接打通 PPT 场景；2) **可视化工作流**：每个工具自动成为类型化 ReactFlow 节点，agent 设计/运行/精调 DAG，engine 分阶段批处理+独立分支并发+集中重试/退避/超时；3) Skills 渐进式披露 + HTTP skill registry；4) 声明式规则引擎
- 对主项目价值：直接借鉴（PPT/多模态扩展 + 可视化编排方向核心参照）
- 借鉴点：①生成式 UI 的「声明式 UI 树 → PPTX/DOCX 渲染」链路迁移为主项目 PPT skill 的交付物通道；②可视化 DAG 编辑器（ReactFlow + YAML 导出 + 自动类型化节点）可作主项目编排黑匣子打开的可视化前端
- 评分：4

## LiveAgent
- 定位：Local-First AI Agent 桌面客户端（Tauri 2）——多模型接入 + 本地工具执行 + MCP/Skills 生态 + 远程 Gateway
- 技术栈：Rust(Tauri 2) + React 19 + Go(agent-gateway) + crates/ 分层（agent-gateway/agent-gui/agent-ui/virtual-core）
- 亮点：1) Tauri 原生桥接 stdio/http MCP server 无限扩展工具；2) Skills 渐进式披露 + 按需加载 + install/create/package + ClawHub 生态；3) 持久记忆 Markdown + SQLite FTS 全文检索；4) 远程 Gateway 协作
- 对主项目价值：直接借鉴（主项目 Tauri2 sidecar 桌面端同构，可直接对齐能力集）
- 借鉴点：①MCP 桥接层设计（Tauri native bridge stdio/http）迁移到主项目桌面 sidecar；②Skills 的 install/create/package 三件套 + 市场生态对齐主项目 skills 库
- 评分：3

## LuaN1aoAgent
- 定位：认知驱动的自主安全 agent（授权渗透）——图记忆 + 持久事件/工件 + 证据回溯
- 技术栈：TypeScript/Node + Pi SDK + executor-sandbox-docker 沙箱
- 亮点：1) **P-E-O 架构**（Think in Graphs / Act Autonomously / Preserve Evidence / Stay Observable）：agent 边界显式、事件与工件持久、图记忆证据背书、工具动作可观测；2) Web workbench 只读观测表面（读持久图/事件/工件/运行时状态），CLI 发起的 run 不可被 web 停止（权限边界清晰）
- 对主项目价值：局部借鉴（「证据背书图记忆 + 可观测」与主项目黑匣子打开同向）
- 借鉴点：①「图记忆 + 事件/工件持久」的证据链模式可强化主项目记忆层可溯源；②沙箱执行环境（docker sandbox）可作主项目代码类 agent 工具的隔离参照
- 评分：3

## MathModelAgent
- 定位：专为数学建模设计的 Agent——自动完成建模并生成可直接提交论文
- 技术栈：Python 后端（FastAPI + uv）+ 前端 + 桌面版（内置 Claude Code + 全套 SKILLS）
- 亮点：1) **阶段化 skills 管线**：1start→2analysis-modeling→3coding-visual→4drawio→5writing→6verity 编号串行，每阶段 SKILL.md 定义输入/输出/阶段边界（「本阶段不负责什么」明示），前序产出真实数据/图表传给后序；2) **验证收尾 skill**：6verity 检查章节/标题顺序/图表引用/数值一致性/占位符/文件泄露/可复现性/编译，输出 VERIFY_REPORT.md，硬错误小范围修复否则标记回前序；3) 桌面版开箱即用（内置 skills + 填 Key 即可）
- 对主项目价值：直接借鉴（多场景扩展 + 教学化方向：把复杂工作流拆成教学化阶段管线）
- 借鉴点：①「阶段化 SKILL 管线 + 每阶段 SKILL.md 声明输入/输出/边界 + 验证 skill 收尾」模式迁移到主项目 ecommerce/ppt/image_quality/prompt_refine skills——每个 skill 明确「本阶段不负责什么」；②VERIFY_REPORT.md 机制可作主项目 agent 任务「验收报告」规范；③桌面版「内置 skills 开箱即用」对齐主项目桌面端
- 评分：4

## MobileAgent
- 定位：通义实验室 GUI Agent 家族（Mobile-Agent v1-v3.5/PC-Agent/E/GUI-Owl 系列）——视觉感知的移动/PC 设备操作 agent
- 技术栈：Python + GUI-Owl（GUI 基础模型）+ v3.5 支持 mobile/browser/computer_use 多面
- 亮点：1) **ToolCUA**（2026.5）：端到端 Computer Use Agent，2 阶段训练（轨迹感知工具合成→Online Agentic RL）学会「何时用 GUI 动作 vs 何时调工具」的最优路径编排；2) v3 多 agent 框架：planning/progress management/reflection/memory；3) GUI-Owl-1.5/32B/7B 开源 GUI 理解模型（token 高效 DOM/AX 树理解）
- 对主项目价值：扩展方向参考（GUI 操作/多模态理解方向）
- 借鉴点：①「GUI 动作 vs 工具调用」路径编排思路可迁移到主项目 agent 决策（浏览器操作 vs 调用 API）；②GUI-Owl 的「用可访问性树而非纯截图」token 高效理解与 agent-device 同思想（见下）
- 评分：2

## Panniantong__Agent-Reach
- 定位：给 AI Agent 一键装上互联网能力——多后端路由 + 自动选型安装体检 + 无感切换
- 技术栈：Python 3.10+ / rich CLI / channels 插件式 + MCP（Exa 等）
- 亮点：1) **多后端路由 + 无感切换**：「每个平台 = 首选+备选」多后端，某接入失效自动切下一个（实例：yt-dlp 被 B 站封 → bili-cli，用户零操作）；2) **doctor 自体检**：`doctor.py` 遍历 channels，每通道 `ch.check()` 自检（probe.py 区分 missing/broken/timeout 三态——which() 找到但 shebang 失效的经典坑）；单通道异常降级为 error 不拖垮全报告，输出边界统一脱敏（scrub_url_credentials 防 URL 泄露）；3) 换接入方式=调列表顺序，不重写代码
- 对主项目价值：直接借鉴（主项目代理池/上游轮换的同构思想，可迁移其健康体检与降级理念）
- 借鉴点：①主项目号池/代理池/上游可用「probe 三态（missing/broken/timeout）+ doctor 报告 + 无感切换」升级现状轮换；②体检查看「当前在用哪个后端」命令（agent-reach doctor）可作主项目 `/v1/health` 的诊断增强；③异常降级不拖垮全报告 + 输出脱敏对齐主项目日志脱敏纪律
- 评分：4

## PrimeIntellect-ai__prime-agent
- 定位：自改进 RLM（递归语言模型）harness——持久 Python 控制环境 + 持续 harness 状态
- 技术栈：TypeScript monorepo + Python REPL 内核 + verifiers/prime-rl 生态
- 亮点：1) **RLM 编程模型**：模型在持久 Python 内核里以代码方式组合能力（`ipython` 是唯一内置模型工具），Python 状态跨 tool call 与 compaction 存活；`rlm.spawn()` 生成真实子 agent 并行/后台，结果可编程取回；2) **/refine 证据背书改进**：review 当前轨迹后对补充 harness 状态（prompt/记忆/skill 描述/子 agent 规格）做「小步、证据背书」更新，绝不重写不可变基础系统提示词，快照支持回滚；3) 心跳/定时重入会话
- 对主项目价值：直接借鉴（自反思/黑匣子打开方向：refine 的保守证据更新 + 快照回滚是最佳实践）
- 借鉴点：①/refine 模式迁移到主项目 critic：自反思只改「补充状态」（记忆/skills/工具描述），绝不改基础系统提示词，且快照回滚；②「不可变基础提示词 + 可变补充状态」分层可作主项目 agent 提示词治理原则
- 评分：4

## Program-Intelligence-Agent
- 定位：银行积分计划问答 agent——每个数字都能溯源到查询结果，无模型臆造（Fibonacci 平台 demo）
- 技术栈：Python + DeltaStream 实时数据（Kafka→物化视图→MCP endpoint→agent→浏览器）
- 亮点：1) **数字溯源验证器**：`agent/grounding.py` 从回答文本抽所有数字（处理 1,234/12.5%/$1.2M/3k），与查询结果数值单元+SQL 字面量比对（含舍入容差），无法验证的标 warning badge 并列出；2) 「All N figures traced to query results」的可信展示层（headline→recommendation→hero tiles→full analysis）；3) 所有展示值必须先经查询结果检查（「nothing comes from the model's head」）
- 对主项目价值：直接借鉴（黑匣子打开/可信回答方向核心参照）
- 借鉴点：①grounding 数字溯源迁移到主项目 agent 输出层：回答中的数字/结论与工具返回/查询结果自动比对，未验证项打 warning 徽标（对电商/财务类 agent 尤其关键）；②「可展开 full analysis：推理+依据+caveats+所用查询」的答案结构迁移到主项目生成式报告
- 评分：4

## SWE-agent
- 定位：让任意 LLM 用工具自主修 GitHub 仓库 issue 的编码 agent 框架（Princeton）
- 技术栈：Python + swerex 远程执行 + yaml 配置 + 多解析器（FunctionCalling/JSON）
- 亮点：1) **工具过滤安全模型**：`sweagent/tools/tools.py` 的 ToolFilterConfig——blocklist（vim/emacs/nano/nohup 等交互/长驻命令）+ blocklist_standalone（裸 python/bash/sh）+ block_unless_regex（radare2 等须带 `-c` 才放行）；2) 单一 yaml 配置治理全 agent 行为（tools/prompts/history 全配置化）；3) 轨迹系统（trajectories/）+ run 系列工具（run_replay/compare_runs/remove_unfinished）
- 对主项目价值：局部借鉴（工具护栏 + 配置化方向）
- 借鉴点：①block_unless_regex 模式（危险命令须带白名单参数才放行）迁移到主项目代码/终端类工具护栏；②全 yaml 配置化可作主项目 agent 配置层治理参照
- 评分：3

## Tel-Agent
- 定位：把任意电话线/短信/邮件/WhatsApp/Telegram 等渠道接上任意 AI 模型的自托管多渠道 agent
- 技术栈：Python + FastAPI + SQLite/alembic + api/channels/*（每渠道一模块）
- 亮点：1) **渠道适配器层**：`api/channels/` 每渠道独立模块（whatsapp.py/telegram.py/email.py/sms.py/phone.py...）统一进出；2) agent/ 与 channels/ 解耦（会话/工具/路由分层）；3) 自托管 + BYO keys
- 对主项目价值：局部借鉴（多渠道扩展方向）
- 借鉴点：主项目若扩「多渠道消息进 agent 编排」，可参照其「channel 适配器 + 统一消息进出」分层（与主项目 providers/ 的多上游适配同构）
- 评分：2

## TencentDB-Agent-Memory
- 定位：腾讯云多形态 agent 记忆插件——L0-L3 分层记忆 + 记忆资产装配
- 技术栈：TypeScript + SQLite(standalone)/TCVDB+Redis(service) 双形态 + v1/v2 HTTP API + Hermes 集成
- 亮点：1) **L0-L3 分层**（与主项目记忆 L1-L3 几乎同构）：L0 原始对话→L1 原子事实→L2 场景块→L3 用户画像，异步管线逐层蒸馏；2) **分层检索 + 预算封顶**：通常 L2/L3 快速引导上下文，需要具体事实时 BM25+向量+RRF 回退 L1/L0，结果再按 item 数/字符预算/超时三重封顶，防记忆淹没上下文窗口；3) **记忆资产化 + ACL**：Chat Memory/Skills/Wiki/CodeGraph 统一注册为 Memory Asset，Fixed Binding + ACL 按 Team/User/Agent/可见性收敛权限——换 agent/框架只需重新装配（re-equip）不需重训
- 对主项目价值：直接借鉴（主项目记忆层 L1-L3 的检索/预算/ACL 增强参照）
- 借鉴点：①「L2/L3 快速引导 + 必要时回退 L1/L0 的 BM25+向量+RRF」检索策略迁移到主项目记忆检索（当前主项目已有 embedding，可补 BM25 与 RRF 融合）；②记忆注入的字符预算/条数/超时三重封顶直接落地主项目防上下文膨胀；③记忆按 Team/User/Agent ACL 装配可作主项目多租户记忆权限参考
- 评分：4

## Untrivial-ai__agent-orchestrator（= agent-orchestrator 同一项目，见 agent-orchestrator 条目）
- 定位：本地桌面编排工作台——给每个编码任务独立 agent/workspace/反馈环，Kanban 实时追踪（与 agent-orchestrator 目录同仓库重复副本）
- 技术栈：Go 后端（daemon/sqlc）+ React 前端 + Tauri 桌面
- 亮点：同 agent-orchestrator 条目
- 对主项目价值：直接借鉴
- 评分：4

## ZhengyiLuo__AgentsDock
- 定位：为 agentic AI 研究设计的 IDE 客户端（桌面 + 移动 + web），前端接 Claude Code 等 agent
- 技术栈：Swift(SwiftUI ZenithCore/ZenithDock) + 自托管后端 AgentsServer + React 移动端
- 亮点：1) agent 会话 + 文件预览 + workspace 一体；2) 跨平台（macOS/iOS/Windows/Linux/Android）
- 对主项目价值：局部借鉴（教学化/交互方向：把 agent 对话与工件并排展示）
- 借鉴点：主项目管理面板可参考其「会话 + 文件/工件预览」双栏布局让 agent 产出可视化（黑匣子打开 UI）
- 评分：2

## agency-agents（= agency-agents-main 同一项目）
- 定位：精心打磨的 AI agent 人格集合（The Agency）——从前端专家到 Reddit 运营，每个 agent 有人格/流程/可交付物
- 技术栈：Markdown agent 定义（可装进 Claude Code/Cursor/Codex/Gemini）+ 原生安装 app（agencyagents.app）
- 亮点：1) 按领域目录组织（academic/design/engineering/finance/game-dev/gis/healthcare/marketing/...）；2) 「人格驱动 + 交付物导向 + 生产就绪」的 agent 撰写标准（非通用 prompt 模板）；3) 一键安装到多 agent 客户端
- 对主项目价值：局部借鉴（skills/agent 编写规范方向）
- 借鉴点：①agent 定义「专业深度 + 人格 + 交付物 + 度量」四要素可作主项目用户自定义 skills 的撰写模板；②按行业目录组织可作主项目 skills 市场分类参照
- 评分：3

## agency-agents-main
- 定位：同 agency-agents（同一项目不同副本，内容一致）
- 技术栈：同上
- 亮点：同上；此副本未含 app 安装器
- 对主项目价值：局部借鉴（同 agency-agents）
- 评分：3

## agent（PentesterFlow）
- 定位：人类在环的渗透测试/漏洞挖掘 Agentic CLI——recon/枚举/验证/证据收集/报告全生命周期
- 技术栈：TypeScript/Node + ollama 本地模型 + skills 包 + Burp 集成 + 权限审批
- 亮点：1) **安全模型**：scoped target + 真实工具调用前请求审批 + 捕获流量需批准；2) **持续学习系统**：curatedMemory + session 压缩 + `#<fact>` 持久事实 + `/compact` 会话压缩进持久记忆 + `/memory add` 持久事实，resume recap 恢复上下文；3) skills 按域打包（graphql/jwt/race/ssrf/ssti/supabase/recon/...）
- 对主项目价值：局部借鉴（记忆压缩/审批/技能包方向的工程范本）
- 借鉴点：①「`#事实` 快速持久 + /compact 会话压缩 + resume recap」迁移到主项目 agent 记忆的轻量显式记忆通道；②scoped 授权 + 审批前置的安全模型与主项目审批机制同构可互相印证
- 评分：3

## agent-browser
- 定位：面向 AI agent 的开源浏览器自动化层——安全检视网页/截图/控制台/网络信号/验证 web app
- 技术栈：Rust 核心（agent_browser_core）+ TS CLI + MCP 接入（`agent-browser mcp`）
- 亮点：1) **安全默认**：无凭据自动化、无反检测、无私网抓取；2) CLI 与 MCP 双通道（check/snapshot/screenshot/console/network 子命令）；3) 截图覆盖保护（--force 才覆盖）+ JSON 输出契约
- 对主项目价值：扩展方向参考（agent 浏览器工具）
- 借鉴点：主项目若为 agent 加浏览器工具，可参照其「安全默认 + CLI/MCP 双通道 + 覆盖保护」边界
- 评分：2

## agent-deck-main
- 定位：AI agent 指挥中心——跨 10+ 项目同时监视/管理多个编码 agent 会话与 MCP 池
- 技术栈：Go 1.24 + conductor 桥 + skills（可装进 Claude Code）+ 桌面/TUI
- 亮点：1) MCP 池化（conductor 桥，bridge.py/plist 守护）；2) 会话 fork 管理；3) 以 skills 形式向 Claude Code 提供操作能力（agent-deck-help）
- 对主项目价值：局部借鉴（多 agent 会话管理方向）
- 借鉴点：MCP 池化思想可迁移到主项目 cf_solver/上游连接池管理；skills 化帮助入口可作主项目管理面板操作引导
- 评分：2

## agent-device
- 定位：移动 app 自动化与验证层（callstack）——给编码 agent 实时 app 反馈环，CLI/MCP/Node API 三通道
- 技术栈：TypeScript + Android/iOS/HarmonyOS 原生快照 helper + WebDriver/limrun provider
- 亮点：1) **token 高效 AX 快照**：agent 读可访问性树快照（AccessibilityTreeCapture/SnapshotInstrumentation）而非纯截图推理，通过 refs/selectors 动作；2) 证据留存供审查（session-journal/evidence）；3) 并行 worktree 设备分配协调 + 远程设备云
- 对主项目价值：扩展方向参考（移动/多模态理解）
- 借鉴点：①「AX 树快照 + refs 动作」比截图省 token 的思路可作主项目多模态 GUI agent 的感知层参照（与 GUI-Owl 互补）
- 评分：2

## agent-framework-go
- 定位：Microsoft Agent Framework Go 实现——生产级 agent 与多 agent 工作流（workflow 图编排）
- 技术栈：Go + workflow/（agentworkflow 图 + checkpoint + telemetry）+ MCP/A2A/AG-UI 生态
- 亮点：1) **图编排 + checkpoint**：workflow/checkpoint/manager.go 提供 in-memory/JSON 双实现 Commit/Lookup，session 级断点续跑；2) portable.go 跨语言可移植协议；3) observability（telemetry.go）
- 对主项目价值：局部借鉴（断点续跑 checkpoint 的参考实现）
- 借鉴点：checkpoint「按 sessionID + CheckpointInfo 提交/查找」的接口设计可作主项目断点续跑存储层参照（对齐现有 queue_store/lease_store）
- 评分：3

## agent-framework-main
- 定位：Microsoft Agent Framework 主仓库（.NET + Python 多语言）——从聊天 agent 到图编排多 agent 工作流
- 技术栈：.NET + Python + declarative-agents（agent/workflow 样本）+ schemas
- 亮点：1) 多语言一致 agent 模型（与 agent-framework-go 同一抽象）；2) declarative-agents/ 声明式定义样本
- 对主项目价值：局部借鉴（框架设计参照）
- 借鉴点：跨语言 agent 模型一致性思想可作主项目「一份技能定义多端复用」参考
- 评分：2

## agent-guardrails
- 定位：AI 编码 agent 的硬策略防护——危险命令在 shell 执行前被硬阻断，无论 agent 提议或人类当下批准
- 技术栈：Claude Code hooks（PreToolUse + jq）+ bash guard 脚本（cloud/database/terraform/kubernetes/git/prisma）
- 亮点：1) **硬阻断 > 人类在环审批**：文档论证「人在审批时不完全懂破坏范围」（Opus 5 ultracode 删光生产库案例），故在工具层硬 block；2) 策略表驱动：policies/*.md 明列「命令 × 会毁掉什么」（aws rds delete-db-instance → 数据库实例），脚本按模式匹配 exit 2 阻断（exit 0 放行）；3) 分域策略（云/DB/Terraform/K8s/Git/Prisma）
- 对主项目价值：直接借鉴（安全护栏方向，与主项目「禁止破坏性命令」纪律同向）
- 借鉴点：①「命令破坏清单（命令→会毁掉什么）+ 硬阻断」模式迁移到主项目 agent 代码/数据库工具护栏（DROP DATABASE/rm -rf/迁移 diff 硬 block）；②PreToolUse hook 阻断协议（exit 2 带消息）对齐主项目 PreToolUse 检查器链
- 评分：4

## agent-inspect
- 定位：TypeScript AI agent 的本地优先证据工具——执行树、确定性轨迹检查、可移植 Evidence v2，无需账户/采集器/默认上传
- 技术栈：TypeScript monorepo（core/eval/guardrails/harness/studio/tui/vscode/mcp-server/...适配器 SDK）
- 亮点：1) **执行树 + 确定性轨迹测试**：把 agent 运行转成可读执行树，CI 里做确定性轨迹断言（checks 引擎纯规则、稳定顺序、不出网不改输入）；2) **Evidence v2**：evidence.html + evidence.json（含 SHA-256 哈希完整性）+ zip 打包，可移植离线审查；3) **本地优先安全默认**：默认仅元数据，不上传，redact 包脱敏；4) 多适配器（ai-sdk/langchain/openai-agents/vitest/jest）
- 对主项目价值：直接借鉴（黑匣子打开方向的最强范本：轨迹回放 + 证据工件 + 确定性断言）
- 借鉴点：①「执行树 + 确定性轨迹测试」迁移到主项目 agent 编排（把 SSE 事件流渲染成执行树，CI 断言关键路径）；②Evidence 工件（html/json 含哈希）可作主项目 agent 任务「可移植审计包」交付物（配合 Program-Intelligence 溯源）
- 评分：4

## agent-orchestrator（= Untrivial-ai__agent-orchestrator 同一项目）
- 定位：从一处规划/运行/监督编码 agent 的本地桌面工作台——每任务独立 agent/workspace/反馈环 + Kanban 实时追踪
- 技术栈：Go 后端（daemon/internal/* 含 session_manager/workspacewatch/autoreview/reviewgateway）+ React 前端 + Tauri
- 亮点：1) **session 为核心对象**：任务/agent/worktree/对话/终端/文件/PR/CI/审查状态全程挂在会话上，Kanban 一张卡代表一个 session（状态/PR/审查证据/时间用量紧凑呈现）；2) **本地 daemon 观察**：daemon 监视 agent 活动与源码状态，workspacewatch 感知工作区变化；3) DESIGN.md 详细 UX 契约（卡片信息顺序/会话不确定状态如实传达/渲染层与 daemon 事实分层）
- 对主项目价值：局部借鉴（编排可视化/工作台交互方向）
- 借鉴点：①Kanban 会话卡 + 「一条派生状态行 + PR/审查证据链接 + 时间用量」信息架构可作主项目 agent 任务面板改版参照；②「渲染层只管视觉、daemon 事实与生命周期逻辑在后端」的分层可作主项目前端-后端职责切分纪律
- 评分：4

---

## 本组汇总：Top3 最值得主项目借鉴项

1. **CowAgent Self-Evolution（隔离 review agent + 快照回滚 + 受限工具 + 保守 [SILENT] 默认 + 空闲/上下文压力双触发）** — 主项目「critic 自反思 + 沉淀用户 skills」方向的完整范本：把自反思从「每次对话都反思」升级为「空闲 + 轮次/上下文压力触发的一次性保守审查」，改动前快照可 undo，内置 skills 白名单保护，产出可 diff 的普通文件。这是把黑匣子打开与教学化落地到可运维级别的关键。

2. **EcomAgent（PreToolUse 三态检查器链 + 错误分类执行策略 + 契约式事件断言 harness + SKILL.md 渐进式披露 + Mem0 式记忆整合判定）** — 与主项目同为「电商场景 + FastAPI + agent 工具调用 + 记忆」，几乎每一项都能直接映射：权限管线（ALLOW/BLOCK/ASK）、仅瞬态重试 + 幂等键、基于事件流的期望轨迹断言回归（比 E2E 轻且稳）、技能菜单常驻+正文按需注入、记忆写入的 ADD/UPDATE/DELETE/NOOP 四判定。

3. **黑匣子打开三件套：agent-inspect（执行树 + 确定性轨迹断言 + Evidence v2 哈希工件）⊕ Program-Intelligence-Agent（数字溯源 grounding 验证器 + 可展开 full-analysis）⊕ gpt-image-2-5-agent-kit（dry-run 评审 + sha256 不可变收据）** — 三者互补覆盖「轨迹可回放、结论可溯源、调用可审计」，是主项目「agent 深度优化（黑匣子打开）」最直接的迁移组合。

**次优（4 分）**：Panniantong__Agent-Reach（多后端路由 + doctor 三态体检 + 无感切换 → 主项目号池/代理池/上游轮换）、TencentDB-Agent-Memory（分层检索 BM25+向量+RRF + 字符预算封顶 + 记忆资产 ACL）、PrimeIntellect-ai__prime-agent（/refine 证据背书小步更新 + 快照回滚 + 不可变基础提示词）、LeAgent（生成式 UI → PPTX 导出 + 可视化 DAG）、agent-guardrails（命令破坏清单硬阻断）、MathModelAgent（阶段化 skill 管线 + 验证 skill 收尾）、AutoAgent（自然语言建 agent 工具化）、CelestoAI__agentor（append-only 事件日志 + resume/fork 持久运行）。
