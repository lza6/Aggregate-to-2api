# g02_agent_ai_b 组扫描报告（40 目录）

> 主项目「听风AI」关注：①agent 深度优化（黑匣子打开/教学化/小白易用/skills 沉淀）②扩展场景（图片/视频/电商/PPT/多模态）③工程规范/交互/安全/性能。
> 扫描方式：ls 结构 + README 首部 + 关键模块源码（graph/engine/gates/memory/tools）。只读分析，未修改任何文件。

---

## agent-orchestrator-main
- 定位：ComposioHQ 的并行 AI 编码 agent 编排层——每个 agent 独立 git worktree/分支/PR，从 dashboard 监督 CI 修复与 review 评论闭环。
- 技术栈：TypeScript/pnpm workspace（packages: ao/cli/core/plugins/web）＋ tmux/Docker 运行时。
- 亮点：
  - agent-agnostic 抽象：注入层独立（Claude Code/Codex/Aider），`packages/core/src/session-manager` 管理会话生命周期。
  - "只有需要人判断时才拉人进来"——人工监督点收敛在 dashboard，agent 自治完成其余。
  - 纯本地编排 + 3,288 测试用例（README badge），工程验证完备。
- 对主项目价值：局部借鉴（DAG 编排 + 人机审批已有类似骨架）。
- 借鉴点：worktree 隔离的并行任务执行思路可映射到主项目「多任务并行」；dashboard 把「各 agent 进度」汇成一屏监督的交互可参考 frontend 管理面板。
- 评分：4

## agent-sphere
- 定位：Java 生态的 AI agent 编排平台，闭环 Perceception → Planning → Execution → Feedback，多模型提供商 + MCP + 浏览器自动化。
- 技术栈：Java 21/Spring Boot 3.4/PostgreSQL/Redis + React 19 前端 + UmiJS + Ant Design 6。
- 亮点：
  - 多 agent 编排时主聊天内联渲染子 agent 卡片，实时逐子 agent 步骤、自动滚动（README ui-multi-agent.png）。
  - 可嵌入 chat widget（shadow DOM + OIDC SSO + REST + SSE timeline 聊天），白标嵌入能力成熟。
- 对主项目价值：扩展方向参考（前端交互）。
- 借鉴点：SSE timeline 聊天 + widget 嵌入模式可对照前端 ChatPlayground；子 agent 卡片内联渲染与主项目 DAG 可视化互补。
- 评分：3.5

## agent-swarm
- 定位：desplega 的"让公司 AI 原生"的 agent 编排引擎，Slack→PR 等业务工作流自动跑。
- 技术栈：Bun + apps（ui/templates-ui/evals）、Docker（app/worker 分离）、charts/。
- 亮点：
  - UI 与 worker 分离部署（`Dockerfile` + `Dockerfile.worker`），多实例水平扩展。
  - 自带 evals 评估集（apps/evals），工作流改动可对照评测。
- 对主项目价值：扩展方向参考。
- 借鉴点：evals 目录把工作流行为固化为可测评集，主项目 agent 技能/DAG 变更可补类似 eval 基准。
- 评分：3

## agent-systems-benchmark-state
- 定位：Agent Systems Benchmark 的协调状态库——把多 agent 任务的声明、租约、修订、对账做成可验证的状态机。
- 技术栈：Python/pyproject + uv，工具 `tools/handoffctl`。
- 亮点：
  - 任务声明锁定（claims）＋ leases ＋ revisions ＋ reconciliation 的持久任务状态机，脱离单 chat 上下文存活。
  - 通用协调器故障/竞态/恢复测试（tests/），vendor 版本签名校验防篡改（coordinator.vendor.json）。
- 对主项目价值：直接借鉴（任务/租约状态持久化）。
- 借鉴点：主项目 DAG 续跑/断点续跑可升级为 claims+leases 模型，防止多 worker 重复执行同节点；竞态恢复测试模式对齐 tests/chaos。
- 评分：3.5

## agent-teams-ai
- 定位：免费桌面 app 管理 AI agent 团队，聚合多 provider（Claude Code/Codex/OpenCode/Cursor/Copilot 等），免注册 UI 优先。
- 技术栈：Electron + Vite + pnpm（src/, agent-teams-controller/, mcp-server/, landing/）。
- 亮点：
  - 多 provider 桌面端统一入口 + 任务详情动画演示；mcp-server 包把 agent 团队能力 MCP 化。
  - 免费模型零配置起步，降低小白门槛极低。
- 对主项目价值：扩展方向参考（桌面端交互，主项目已有 Tauri 托盘）。
- 借鉴点：任务详情视图的"目标/状态/迭代/原因"字段设计与主项目人机审批/断点续跑 UI 可融合。
- 评分：2.5

## agentchat-main
- 定位：agent 技能（skill）——用一份 SKILL.md 教 AI agent 在 S2 streams 上做 agent 间群聊，无服务器无中间件。
- 技术栈：Node + S2 SDK + agentskills 技能格式；test-harness 做协议符合性测试。
- 亮点：
  - "协议即技能"：把整份通信协议写成一个 SKILL.md（主产物），agent 直接按技能实现协议。
  - 类型化消息路由（bug_report/prompt_report/dx_feedback 分流到不同 stream）。
  - 邀请用 Base64url 无凭据、chmod 600 配置，安全细节扎实。
- 对主项目价值：直接借鉴（skills 范式，契合"沉淀训练用户自己的 skills"）。
- 借鉴点：主项目 agent 间的多 agent 协作协议可仿照写成 SKILL.md 沉淀；类型化消息路由可进 MCP 服务端。
- 评分：3

## agentfiles
- 定位：Obsidian 的 AI skills 管理器——跨 17 个编码工具浏览/创建/编辑/安装 skills，带成本仪表盘。
- 技术栈：Obsidian 插件（主 JS）＋ skillkit analytics（@crafter/skillkit）。
- 亮点：
  - Dashboard 推出 burn rate（消耗速率）、context tax（上下文税）、health metrics——把 skill 占用上下文的成本显性化。
  - 分步向导（stepped wizard：选工具→类型→命名）创建 skill，极大降低小白沉淀技能门槛。
  - Marketplace 安装（skills.sh），与目录即插即用。
- 对主项目价值：直接借鉴（skill 沉淀/教学化方向核心对标）。
- 借鉴点：主项目可做「skills 管理页」：上下文税/成本指标 + 分步创建向导 + 从对话中把某次成功做法一键沉淀为 skill。
- 评分：4.5

## agentic-inbox
- 定位：完全跑在 Cloudflare Workers 上的自托管邮箱 + AI 邮件 agent（收/发/管 + agent 起草回复）。
- 技术栈：React Router 7 + Workers + Durable Objects + SQLite + R2 + Workers AI + Agents SDK。
- 亮点：
  - 每邮箱一个 Durable Object 隔离 + SQLite，天然多租户隔离；Email Routing 收信全 Serverless。
  - AI agent 读/搜/起草集成进邮件产品本身。
- 对主项目价值：扩展方向参考（邮箱池自动化已有，但架构是自建反向）。
- 借鉴点：邮箱池若想 Serverless 化或隔离升级可参考 DO-isolation 粒度。
- 评分：2.5

## agentic-project-management-main
- 定位：APM CLI——把项目管理原则带进 AI 工作流，用上下文保持技术解决 LLM context window 填满问题。
- 技术栈：TypeScript/npm CLI，支持多 assistant（Cursor/Claude CLI 等）的 markdown 目录。
- 亮点：
  - 面向 context 极限设计：结构化 agent 团队 + 上下文保留技术，context 满后平滑切换到 fresh session 不丢关键上下文。
  - "项目经、开发、临时专家、配置专家"角色化分工。
- 对主项目价值：局部借鉴（上下文管理）。
- 借鉴点：主项目 DAG 续跑/记忆可借鉴"会话交接清单"模式，把续跑所需上下文压缩成结构化交接文件。
- 评分：3.5

## agentic-rag-for-dummies（与 -main 为同一仓库双份）
- 定位：教学向模块化 Agentic RAG 教程——LangGraph + 会话记忆 + human-in-the-loop 澄清，notebook 化。
- 技术栈：Python 3.11+/LangGraph 1.2+/Qdrant/Ollama+OpenAI+Anthropic+Google 提供商抽象。
- 亮点：把 HITL 澄清设计为 RAG 图的一个正式节点（query clarification），教学价值强。
- 对主项目价值：扩展方向参考。
- 借鉴点：RAG 澄清节点（LLM 不确定时反问用户）可进主项目 RAG 分支；教程式 notebook 分层可借鉴教学化。
- 评分：2.5（-main 重复，评分 2）

## agentmemory-main
- 定位：ai 编码 agent 的持久记忆系统（TT 型）——跨 agent 共享的可检索、可版本化记忆数据库。
- 技术栈：TypeScript + iii-engine + MCP（41 个 MCP 工具）+ benchmark/ 自评测。
- 亮点：
  - 4-tier 记忆攻读 Working → episodic → semantic → procedural，配 Ebbinghaus 强度衰减 + 分层淘汰（hot/warm/cold/evictable）。
  - 三重流检索 BM25 + vector + knowledge graph；记忆版本化 supersede（Jaccard>0.7 判定相似）、`supersedes/extends/derives/contradicts` 关系带置信度级联传播 stale。
  - 可量化的证据：240 条观测/30 会话 Recall@10=64%、MRR 满分、省 92% token（README）；581 测试。
- 对主项目价值：直接借鉴（主项目 `api/agent/memory.py` 已参考其 L0-L3 分层 + supersede + 衰减，但仍有差距）。
- 借鉴点：①episodic/semantic/procedural 类型化四层（主项目现为场景/人格聚合，无程序性记忆）②知识图关系传播 staleness（supersede 只清了单条，未传播到依赖节点）③三重流检索 BM25+向量+图（主项目仅 SQL 查询）④跨 agent 实例同步（主项目单点）。
- 评分：5

## agentplane-hermes-plugin
- 定位：Hermes 与 AgentPlane 协议 v2 的 worker-lane 桥——Hermes 管 LLM episode，AgentPlane 管工程任务状态。
- 技术栈：Python/pyproject + Hermes native 插件。
- 亮点：
  - 明确职责边界：插件是 transport adapter，永不改 AgentPlane 任务文件、永不直接写 Hermes DB——分离可得可审计。
  - 命令面最小（doctor/run/supervise/approve），`AgentSemanticResult v2` 结构化结果原子写路径。
- 对主项目价值：扩展方向参考。
- 借鉴点：主项目若接多个外部 agent 执行器，可参照"结果类型 + 原子写路径 + supervisor 边界"的适配器约定。
- 评分：3

## agents-main
- 定位：wshobson 的 Claude Code 插件全家桶——182 个专业 agent + 149 个 skill + 16 个多 agent 编排器 + 96 命令，77 个单用途插件。
- 技术栈：Claude Code 插件体系 + Smithery。
- 亮点：
  - 渐进式披露（progressive disclosure）：skill 只在需要时被加载，minimal token usage——插件按需激活。
  - 单用途插件 + 24 类目组织，粒度小、可组合（前端/安全/SEO/业务运营等全覆盖）。
  - 明确三层模型策略（Opus/Sonnet/Haiku 分工）。
- 对主项目价值：直接借鉴（skills/agent 组织范式）。
- 借鉴点：主项目技能库可套用"单用途 + 渐进式披露 + 分模型路由"组织；面向小白的 agent 模板可参照其职责描述模板。
- 评分：4

## agentseal
- 定位：AI agent 安全工具包——red-team prompts、检测 MCP 投毒、扫描 skill 文件、追踪有毒数据流。
- 技术栈：双发行 Python(pypi) + JS(npm)；PROBES.md 目录 225+ 基础 probes + 86 Pro(45 MCP + 28 RAG + 13 多模态)。
- 亮点：
  - 完整攻击探测分类目录：82 提取（系统提示窃取）+ 143 注入 + MCP/RAG 专用（PROBES.md 逐条 severity），覆盖语言切换/编码技巧/多轮升级等对抗路径。
  - 本地无 key 即可扫（agentseal guard），`scan --prompt` 对本机模型做对抗测试。
- 对主项目价值：直接借鉴（安全护栏方向）。
- 借鉴点：主项目 MCP 服务端 + skills 输入可用其 probe 分类做基准：对 LLM 端点做注入/提取基线测试；把 skill 文件扫描（古毒/后门关键字）做进 CI。
- 评分：4

## agentsys-main
- 定位：agent 分布式运行与编排系统 + 插件 marketplace（19 plugins/47 agents/40 skills 跨仓库）。
- 技术栈：TypeScript/Node、npm、3,583 测试、5 平台适配（Claude Code/Codex/OpenCode/Cursor/Kiro）。
- 亮点：插件以独立仓库分发、agentsys 是中心 installer/marketplace；测试量大覆盖 5 平台。
- 对主项目价值：扩展方向参考（插件分发组织）。
- 借鉴点：若主项目 skills 需要多 agent 平台共存，参照"独立仓库 + 中心清单"分发模型。
- 评分：3

## agenttrail
- 定位：本地开源可观测层——把 coding agent 的 plan/tool 调用/文件改动变成实时项目地图（live board）。
- 技术栈：TypeScript + CLI(npx) + 本地 browser UI。
- 亮点：
  - 核心洞察："plan 说意图，filesystem 说实际摸到了什么"——把二者对比成 live 进度地图，直接暴露"默默重开了已完成部分"这类 agent 隐患。
  - hooks 需用户同意才接，无 telemetry、无账号、崩溃自愈（autostart 自举）。
- 对主项目价值：直接借鉴（agent 黑匣子打开，当前主项目最关注方向之首）。
- 借鉴点：主项目 agent 执行页加"计划 vs 实际产物"视图：对比 DAG 声明产物与 worker 实际写文件/调用工具差异，diff 出"声称完成但没真做"。
- 评分：4

## ai-agents-from-scratch
- 定位：教学仓库——不用框架从第一性原理构建 AI agent，讲 LLM 到底怎么变成 agent。
- 技术栈：Node + node-llama-cpp 本地模型；examples 渐进（intro → simple-agent → react-agent → ...）。
- 亮点：
  - 教学法：code/explanation/concept 三元分离 + 配套网站做"图 vs 地形"双入口。
  - 先讲 why 再讲 how，构建父路径可视化。
- 对主项目价值：扩展方向参考（教学化方法）。
- 借鉴点：主项目"小白易用/教学化"可借用其"示例递进 + 概念讲解分离"手段做 agent 能力教程。
- 评分：3

## alibaba__page-agent
- 定位：GUI Agent——让每个 web 页面内置自己的 AI agent（浏览器扩展/脚本注入）。
- 技术栈：TypeScript/包管理器 + Chrome 扩展（page-agent-ext）＋ npm 分发。
- 亮点：把 GUI agent 以"页面脚本"形态内嵌，跨页面无感可用；文档（docs/）配套完整。
- 对主项目价值：扩展方向参考（浏览器/GUI 自动化），但主项目无浏览器方向，相关性中低。
- 借鉴点：若未来做网页操作型 agent（如电商代下单）可参考其 DOM 感知与脚本注入范式。
- 评分：3

## all-agentic-architectures（含 -main 双份）
- 定位：35 种生产级 agentic 架构的「图书馆 + 活教科书」——每种架构 end-to-end 实现 + 对照 benchmark 排行榜。
- 技术栈：Python/pyproject + mkdocs + benchmarks/ + evaluators/tracing/llm/memory/tools 统一支撑层。-main 为 notebook 版（01_reflection.ipynb … 17 个教学 notebook）。
- 亮点：
  - 架构模式库全覆盖：react/reflection/reflexion/planning/pev/blackboard/tree_of_thoughts/self_rag/corrective_rag/graph_rag/memgpt/lats/self_discover/debate/ensemble/rlhf/meta_controller/dry_run/swe_agent/voyager...（src/agentic_architectures/architectures/ 37 文件）。
  - 每个架构接入统一 evaluator 并被 leaderboard 排名——哪种任务用哪种架构有数据支撑，直接服务"选型不是拍脑袋"。
  - provider-agnostic + deterministic-picker discipline。
- 对主项目价值：直接借鉴（agent 编排教学化 + 架构选型证据化）。
- 借鉴点：主项目 DAG 的每类节点（意图/工具/记忆/RAG）可建"架构选型对照表"：相同输入下不同编排结构的成功/时延打分；把 37 个模式中最贴近的 5-8 个（ReAct/Reflexion/multi_agent/blackboard/ToT）做成教学页。
- 评分：4.5

## arteemg__sky-agent
- 定位：一键部署到云的 Telegram agent（fork + Railway + 2 环境变量即可跑）。
- 技术栈：Python 3.12/pyproject + Docker + Railway + Telegram bot。
- 亮点：极致降低部署门槛——"编辑文件=改代码"的哲学，agent 由 agent.yaml 驱动。
- 对主项目价值：扩展方向参考。
- 借鉴点：小白易用可借鉴其"最少配置跑起来"的部署链路，但主项目无 Telegram 方向。
- 评分：2

## astron-agent
- 定位：iFLYTEK 企业级 agentic workflow 开发平台开源版——工作流编排 + 模型管理 + MCP/RPA + 团队协作 + 高可用。
- 技术栈：后端 Java/Spring 生态 + 前端 console(React) + `core/` 多服务（workflow/agent/memory/knowledge/plugin/tenant）。
- 亮点：
  - 节点类型体系极完整（`core/workflow/engine/nodes/`：llm/agent/decision/if_else/iteration/loop/mcp/knowledge/rpa/pgsql/message/params_extractor/variable_aggregation/text_joiner/global_variables/cache_node...），企业少开发。
  - DSL 引擎（dsl_engine.py）用 pydantic 强类型定义 Value/InputSchema/RetryConfig，节点执行分布化 + 重试/错误分级（CONTINUE_ON_ERROR_* 节点类）。
  - LLM 输出 JSON 清洗器（decision_node._custom_parser 处理未转义换行/引号/反斜杠），工程细节扎实。
- 对主项目价值：直接借鉴（编排节点体系 + 工程规范）。
- 借鉴点：主项目 DAG 节点可对照补 if_else/iteration/loop/variable_aggregation/conditional 等通用节点（现在侧重 agent 专用节点）；LLM JSON 清洗 + retry_config 分层（stream 型/non-stream 型失败语义）可移植。
- 评分：4

## awesome-agent-cortex
- 定位：agent 生态分层的 curated 地图（Build/Operate/Remember/Own 四层），目录收集类。
- 技术栈：Markdown + 目录。
- 亮点：把记忆/上下文工程/知识图/身份/支付/可观测分层串成"主权的 agent 栈"心智模型。
- 对主项目价值：扩展方向参考（选型地图）。
- 借鉴点：作为 skill/依赖选型的索引工具。
- 评分：2

## awesome-agent-orchestrators
- 定位：agent 编排工具 curated list（并行编码 agent/自主循环 runner/多 agent swarm/编排基建）。
- 技术栈：单 README curated list。
- 亮点：按"怎么用"分类（terminal/desktop/autonomous loop/multi-agent swarm…）而非按技术栈，选择导向明确。
- 对主项目价值：扩展方向参考。
- 借鉴点：选型索引。
- 评分：2

## awesome-ai-agent-incidents
- 定位：真实世界 AI agent 安全事故语料库——零点击 Copilot 渗透、AI C2 通道、MCP 投毒、CVE 库、OWASP Agentic Top10。
- 技术栈：Markdown curated corpus。
- 亮点：The Promptware Kill Chain（提示件杀伤链）+ MCP 攻击向量 + OWASP Agent Memory Guard 等防御框架索引。
- 对主项目价值：直接借鉴（安全基线参考，尤其 MCP 安全）。
- 借鉴点：主项目 MCP 服务端上线前对照其 MCP 攻击向量清单过一遍；安全文档引用 kill chain 术语统一评审语言。
- 评分：3.5

## awesome-codex-subagents-main
- 定位：136+ Codex 子代理收集（10 类目）。
- 技术栈：Markdown curated list + voltagent 生态（又指 agentskills 12k/skills、Claude Code 14k/subagents）。
- 亮点：子代理按类别 + 用途索引，可作为子代理模板素材库。
- 对主项目价值：扩展方向参考。
- 借鉴点：为小白提供开箱即用的子代理模板（翻译/审查/测试等），可复用其描述文案。
- 评分：2.5

## awesome-hermes-agent
- 定位：Hermes Agent（Nous Research 自改进 agent）的独立生态目录（skills/插件/记忆 provider/桥）。
- 技术栈：Markdown curated + Hermes 生态复核状态表。
- 亮点：生态层划分（runtime/memory/surface/bridge）配 runtime-map 图，状态都带"上次复核日期"。
- 对主项目价值：扩展方向参考。
- 借鉴点：目录维护节奏可参照（每条资源带 review 日期，避免 stale）。
- 评分：2

## callstack__agent-device
- 定位：给 AI coding agent 的移动端 app 自动化与验证层（iOS/Android/HarmonyOS/tvOS/web 等）。
- 技术栈：TypeScript npm 包 + MCP server + 多平台 transport（android 用工具/linux/apple）。
- 亮点：
  - 让 agent 用「无障碍快照」而非截图推理，token 高效；ref/selector 精准操作 + 证据留存供评审。
  - 设备访问跨 agent 协调（并发抢占），契约文档化。
- 对主项目价值：扩展方向参考（多模态验证），主项目无移动端方向，相关度低。
- 借鉴点：若未来做 app 侧截图验证可参考 accessibility-snapshot 思路。
- 评分：2.5

## can4hou6joeng4__boss-agent-cli
- 定位：面向真人与 AI agent 的招聘平台 CLI——终端向导 + 福利筛选 + 双角色（求职/招聘）工作流 + JSON 信封。
- 技术栈：Python ≥3.10/pyproject + uv + MCP server + evals/。
- 亮点：
  - 双角色工作流（真人 vs agent 不同交互面）+ JSON 信封（结构化工具输入输出约定，agent 可直接对接）。
  - 终端向导（wizard/）把复杂表单变分步问答，小白友好；自带 evals。
- 对主项目价值：局部借鉴（受控命令面 + 信封）。
- 借鉴点：主项目公开 API 输出用「JSON 信封」稳定契约（已有响应封装，可补全字段级契约测试）；CLI/向导式交互可参考做成 agent 教学引导。
- 评分：3.5

## claude-agent-acp
- 定位：Anthropic 官方 ACP adapter——把 Claude Agent SDK 变成 agentclientprotocol 兼容客户端可用的 agent。
- 技术栈：TypeScript/npm + Agent Client Protocol + MCP。
- 亮点：
  - provider-neutral 扩展设计：goal-extension（会话级长目标与 prompt 解耦，status: active/paused/blocked/limited/complete + iterations + lastReason）、permission-extension、session-failure-extension——全部走 `_meta` 能力协商。
  - 子代理会话需双边能力协商后才暴露，结构化协议约束交互。
- 对主项目价值：局部借鉴（协议化交互）。
- 借鉴点：主项目人机审批/断点续跑状态可对齐其 goal extension 状态机（active/blocked/complete + 迭代次数 + 原因），前后端字段统一。
- 评分：3.5

## claude-code-unified-agents
- 定位：54 个生产级 Claude Code 子代理合集（合并多个社区仓库），master orchestrator 编排多 agent 工作流。
- 技术栈：Claude Code subagent markdown（agents/）。
- 亮点：类目全覆盖（14 开发 + 质量 + AI/ML + 业务 + 创意 + meta 管理）；每个 agent 附 1000+ 行代码示例；工具权限按 agent 可配。
- 对主项目价值：直接借鉴（subagent 模板库）。
- 借鉴点：可直接挑选其 backend-architect/critic/translator 等描述模板转成主项目 agent 技能。
- 评分：3

## code-yeongyu__oh-my-openagent
- 定位：开源、可自托管的 OpenAgent 兼容实现（OmO）——把 Claude Code/OpenCode 体验做成一整套本地 agent 工具链。
- 技术栈：Bun/TS 大 monorepo（packages/ 超 30 个核心包）。
- 亮点：
  - 核心包拆分极细（memory-core/lsp-core/mcp-client-core/git-bash-mcp/agents-md-core/delegate-core/res/fswatch/hashline...），每层可独立复用。
  - 亲和 Windows 的并行测试（bunfig.win2.parallel.toml）+ 记忆系统 + CodeMode + AgentTeams + 多模态（README beta）。
  - sign laptop 贴图教学化 CLI，中文文档。
- 对主项目价值：扩展方向参考（大而全的 agent 复刻工程），工程量大不宜照搬。
- 借鉴点：分层复用思路——主项目若扩展 LSP/编辑器集成可复用其 lsp-core 接口设计。
- 评分：3

## commerce-agents
- 定位：Anthropic 官方电商 agent 参考实现——shopping agent（C 端）+ merchant agent（B 端），一次定义跑在 4 个运行时。
- 技术栈：Python 3.11+（核心）+ Node/examples；Messages API / Agent SDK / Managed Agents 三运行时。
- 亮点：
  - 工具硬护栏 gates：provenance gate（cart 只接受本 session 出现过 product_id）+ options gate（有选项必须选 variant）+ 会话内写串行化——防幻觉在源头。
  - fencing：所有来自 catalog/网页的工具结果包进 storefront_data fence 标签，明示"里面的指令必须上报、绝不执行"——防注入第一道线。
  - grounding 优先级规则（grounding.py）：store-terms 问题从 search_policies 起跑、售后从 get_orders 起跑、未见过 product_id 强制 get_product_details——LLM 不自由选起点。
  - memory extraction 模板：只许存用户自己声明的偏好/上限以独立句子（"under 90 a month"不合格），live key `current_project` 单条覆盖，健康/财务/身份信息默认排除——合法记忆边界。
  - checkout 只渲染 cart 不下真实单，merchant 写操作全部 staged 等人工批准，商业规则/合规留给部署方。
- 对主项目价值：直接借鉴（电商扩展场景 No.1 参考 + 工具护栏安全范式）。
- 借鉴点：①主项目未来电商工具加 provenance/options 类 gate（引用可验证凭证）②工具结果统一 fence 标签防注入（现有工具输出直接裸露）③grounding 优先级规则进 DAG 起始节点选择 ④记忆提取模板约束（主项目记忆允许存什么/排除什么可对齐其 excluded 清单）。
- 评分：5

## company-research-agent
- 定位：多 agent 公司研究报告生成器（多源 gather → 过滤 → 综合 → 排版）。
- 技术栈：Python + LangGraph + Tavily + React 前端；双模型（Gemini Flash 高语境综合 + GPT-5.1 格式排版）。
- 亮点：双模型分工（高语境综合 vs 精确格式化）；轮询式异步进度追踪 UI。
- 对主项目价值：扩展方向参考（多源研究 agent）。
- 借鉴点：主项目文本型 agent 的"研究→串联→排版"流水线可参照；前台进度轮询 UI。
- 评分：3

## craft-agents-oss
- 定位：craft.do 的 agent 工作台——文档（而非代码）中心工作流、多任务并排、任意 API/服务直连、会话共享，Claude Agent SDK + Pi SDK 双跑。
- 技术栈：Bun monorepo（apps: electron/cli/viewer/webui + packages: core/server/server-core/session-mcp-server/messaging-gateway/ui）。
- 亮点：
  - 文档中心（document-centric）而非 terminal 中心的工作流，外壳非 CLI（更贴近主流用户）。
  - 用 agent 自己构建 agent（dogfooding）：定制即 prompt。
  - session-mcp-server + messaging whatsapp worker：会话可被 MCP/消息渠道暴露。
- 对主项目价值：扩展方向参考（交互范式）。
- 借鉴点：主项目管理面板若强化 agent 多任务并排视图可参考其 viewer/webui 交互；"定制即 prompt"哲学契合小白易用。
- 评分：3.5

## donglongjun886__product-review-agent
- 定位：电商平台商品内容治理的复杂风险调查 agent——只接管机审判不了的「复杂低置信案件」，输出 PASS/REJECT/HUMAN_REVIEW 三分类裁决。
- 技术栈：Python 3.11+ / LangGraph / Pydantic / litellm / 6 个调查工具 + 双层架构（pr.agent 子图 + 确定性 overlay）。
- 亮点（本项目最强的「安全降级 + 可审计」设计）：
  - 三层分离流程：机审初筛（快便宜）→ 三分流（明确正常/明确违规/复杂低置信）→ 只有复杂案件进 agent，把 agent 成本框在长尾。
  - "LLM 只产 Proposal，确定性 overlay 收口"：decide 节点中 LLM 只输出 DecisionProposal，`run_decision_overlay`（guardrails/gate.py）用硬规则 + 10 类弃权归因码（R1–R5）确定性重算 decision_confidence，任何改判写入 overrides——谁降级了、为什么，全程可审计。
  - 预算护栏（budget.py：LLM 调用/工具/token/延迟四维限制）+ 收敛检测（converge.py）+ 工具去重（dedup.py）+ degraded 降级传播——图唯一回环 plan→tools→reevaluate→plan，退出全靠确定性条件。
  - evidence 强引用不变量：evidence_ids 必须指向 state 中真实证据，policy_id 只能引用真实证据，LLM 臆造被 gate 拦截。
  - human-in-the-loop 回流（HUMAN_REVIEW 决策落 null 回传案例库/政策库/评测集，闭环迭代）。
- 对主项目价值：直接借鉴（电商扩展 + 安全将判定收口的范式对主项目 critic/DAG 都有意义）。
- 借鉴点：①主项目 critic/自反思节点可套"LLM 提案 + 确定性 overlay"双层收口（现在 critic 输出基本靠 LLM 自证）②预算四维护栏（现有 budget_guard 可补 token/延迟）③三分类 + 弃权归因码补主项目审批流 ④证据强引用防幻觉。
- 评分：5

## dsh-agent-teams
- 定位：把一个 DeepSeek Harness 会话变成"队长 + 可持久子 agent 团队"的插件——依赖感知任务拆解 + DM 直聊协调 + 自动共享调度 + 实时 Web UI。
- 技术栈：TypeScript（cordis 插件系统）+ dsh-agent/dsh-tools 生态。
- 亮点：
  - 镜像 Claude Code AgentTeams 全流程的协调工具集：create team → add members → create tasks(dependencies) → claim/assign → work → report → status → delete（`agent_teams_*` 13 个模型可见工具，tools.ts）。
  - 质量门控纯函数层（quality-gates.ts）：requirements 1–4 轮、code 3 轮、repair 最多 2 次 + PathClassification（in_scope/out_of_scope/undeclared/illegal）路径审计——写文件不得越界。
  - 持久状态（state.ts）+ mailbox 收发 + 冲突任务取消（cancelUnfinishedTask）+ 退役成员护栏（retired member guard）防复活发消息。
- 对主项目价值：直接借鉴（多 agent 编排 + 质量门控，主项目 agent 团队方向核心对标）。
- 借鉴点：①主项目多 agent 并行可加路径分类审计（agent 写文件是否越界，DAG worker 现在无此护栏）②任务依赖 + claim/assign 状态机进人机审批队列 ③质量门控轮次上限（requirements/code/repair 各限 X 轮）防死循环。
- 评分：4

## dsh-plugin-subagent-director
- 定位：为 DSH 子代理指定供应商/模型 + 用「角色模板」规划主/子代理分工，四级回退链决定模型路由。
- 技术栈：TypeScript/cordis 插件 + test/vitest。
- 亮点：
  - 四级回退链：单次调用参数 > 角色绑定 > 插件默认 > 继承主代理（未配置零侵入）。
  - 角色模板 = 职责描述（给主代理看）+ persona（注入子代理）+ 可选模型绑定；主代理系统提示自动注入角色清单（"知道何时委派给谁"）。
  - 受控模型选择：provider/model 只从 allowedModels 授权列表取，未授权路由丢弃回退——不越权用模型。
- 对主项目价值：直接借鉴（子代理角色模板化 + 模型授权控制）。
- 借鉴点：主项目 skills/子代理可引入「角色模板」概念（对外职责描述 + 注入 persona 分离）；模型路由受 allowedModels 白名单约束（现有 MAB 路由是自动选，白名单防越权可补）。
- 评分：3.5

## easy-agent
- 定位：开源终端原生 coding agent（TS）——Claude Code 风格但代码库可读、可扩展，官方教程化（37 阶段 roadmap + step/ 快照）。
- 技术栈：TypeScript + tsup + React/Ink 终端 UI + MCP + skills + subagents + Agent Teams + 插件。
- 亮点：
  - 教学化构建：37 阶段从 model 通信推到发布，每阶段有独立 step/ 快照，新人按 stage 顺序读即学会完整 agent 架构——「黑匣子打开」做得最彻底的参考。
  - 模块边界清晰：agents/builtIn、commands/queryEngine、permissions、sandbox、services（api/mcp/skills）、session/state 分层。
  - skills 服务带条件加载（services/skills/conditional.ts）与 budget（budget.ts），skill 也受预算约束。
- 对主项目价值：直接借鉴（教学化 + 模块结构映射）。
- 借鉴点：①主项目 agent 教学页可仿其 stage 拆解（每块发一个可运行 snapshot）②skills 条件加载 + budget 对齐主项目技能库（主项目 skill 无加载预算）③QueryEngine 多轮编排状态机可对照。
- 评分：4.5

---

## 本组汇总：Top3 最值得主项目借鉴项

1. **commerce-agents（Anthropic 官方）—— 工具护栏 + 防幻/防注四件套（评分 5，电商扩展 No.1）**
   `gates.py` 的 provenance gate + options gate、`fencing.py` 的 storefront_data fence 标签、`grounding.py` 的起点优先级规则、`memory.py` 的提取边界模板。主项目扩展电商工具链时直接照搬这套"可验证引用 + 结果围栏 + 强制起点 + 记忆边界"；其"checkout 只渲染不下单/写操作 staged 等批准"与人机审批流天然契合。

2. **product-review-agent —— 「LLM 仅提案 + 确定性 overlay 收口」可审计裁决范式（评分 5，架构与精益）**
   `nodes/decide.py` + `guardrails/gate.py` 把最终判定从 LLM 手里拿回确定性代码：10 类弃权归因码（R1–R5）写进 overrides、决策置信度确定性重算、evidence/policy 强引用防臆造、四维预算护栏、收敛/dedup/degraded 降级传播；配合三层机审分流（只把复杂案件交给 agent）。对主项目 critic 自反思节点（现靠 LLM 自证）与审批流是直接升级路径。

3. **agentmemory-main —— 记忆系统的下一级形态（评分 5，主项目记忆已引用其 L0-L3/supersede/衰减，尚未拉平的部分）**
   剩余差距：episodic→semantic→procedural 类型化四层、知识图关系（supersedes/contradicts 等带置信度）级联传播 staleness（现在 supersede 只清单条）、三重流检索 BM25+向量+图、跨 agent 同步。三项可直接落进 `api/agent/memory.py`（521 行）的 v15 候选。

**提名 4-6（横跨 ①②③）：**
- **agentfiles（评分 4.5）**：burn rate/context tax dashboard + 分步向导一键沉淀 skill——正是主项目"小白易用 + 训练用户自己的 skills"的现成交互范本。
- **easy-agent（评分 4.5）**：37 阶段教学化 + skills 条件加载/预算约束，是"黑匣子打开"最彻底的参考。
- **all-agentic-architectures（评分 4.5）**：37 种架构模式库 + 各架构 benchmark leaderboard，可直接生成为主项目 agent 教学的"选型证据"页。