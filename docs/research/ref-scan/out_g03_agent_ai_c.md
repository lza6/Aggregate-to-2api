# g03_agent_ai_c 组扫描报告（37 目录）

> 扫描人：g03 分析师｜扫描方式：只读分析（ls / README / 关键模块），未修改任何文件
> 主项目对齐方向：①agent 深度优化（黑匣子打开/教学化/小白易用/沉淀训练用户自己的 skills）②扩展场景（图片/视频/电商/PPT/多模态）③工程规范、交互、安全、性能借鉴

---

## easy-agent-main
- 定位：用 TypeScript 从零复刻 Claude Code 的开源工程（五层架构：交互/编排/核心循环/工具/模型通信）
- 技术栈：TypeScript / Node.js，`step/` 目录 12 个渐进式步骤
- 亮点：
  - 五层架构严格分层，`src/`（context/core/entrypoint/permissions/scripts/services/session/tools/types/ui/utils）与 Claude Code 高度同构
  - `step/step1~step12.js` 把"从 Agent Loop 到完整 Harness"拆成 12 个可运行快照，**渐进教学化**（与 learn-agent 思路一致但更工程化）
  - 明确把安全边界（permissions）、会话编排（session）、工具层（tools）独立成包
- 对主项目价值：扩展方向参考
- 借鉴点：主项目 DAG 编排/agent 教程若想"教学化"，可仿照 stepN.js 渐进快照模式做"一键演示/分步教学"；permissions/ 分层可作为 agent 权限安全设计的参考
- 评分：3

## hAcKlyc__MyAgents
- 定位：国产开源"桌面个人 Agent 工作台"（Tauri2 + React19），工作区/任务/技能/模型多供应商一体化
- 技术栈：Tauri v2 / React 19 / Rust，`specs/tech_docs/` 有完整架构设计文档体系
- 亮点：
  - **想法→任务状态机**：Thoughts+Task 中心、Cron 周期调度、"本地命令感知器"（低成本检查命中才唤醒 AI）——与主项目"任务/审批/DAG续跑"最贴近的可参考实现
  - `src/server/host-interaction.ts`：IM 场景（group/private）按来源类型做工具 deny 覆盖与交互能力归一化——渠道安全隔离设计
  - `bundled-agents/` + `bundled-skills/`（memory-gardener/memory-molt/task-alignment 等）——**"官方预置 agent/skill 包"分发模式**
  - `specs/tech_docs/` 覆盖 analytics/i18n/im_integration/auto_update 等——工程文档化极彻底
- 对主项目价值：直接借鉴（交互/任务/技能体系高度同构）
- 借鉴点：①Task 状态机+Cron+命令感知器唤醒模式可进主项目 agent 定时任务层；②IM 渠道工具 deny 可按来源分级（主项目 IM Bot 场景）；③bundled-skills 预置包模式可复制到主项目 skills 库分发
- 评分：4

## hermes-agent
- 定位：Nous Research 的"自带学习闭环"个人 agent（终端 TUI + 多渠道 gateway）
- 技术栈：Python，`agent/` 目录模块化（memory_manager / context_compressor / smart_model_routing / prompt_caching / skill_commands / credential_pool）
- 亮点：
  - **闭环学习**：复杂任务后自动创建 skill、skill 使用中自我改进、周期性记忆 nudges、FTS5 会话搜索 + LLM 摘要跨会话召回
  - `agent/smart_model_routing.py` + `agent/credential_pool.py`：模型路由与凭证池——与主项目 MAB-EWMA 路由可对照
  - 多终端后端（local/Docker/SSH/Modal/Daytona），服务器空闲近零成本——网关化部署
- 对主项目价值：直接借鉴（学习闭环/记忆正是主项目关注方向①）
- 借鉴点：①"任务完成后自动沉淀 SKILL"的触发-生成-入库流程可进主项目 skills 体系；②skill 在使用中自改进（写入 SKILL.md 修订日志）可移植；③periodic memory nudge 机制可增强主项目记忆巩固
- 评分：5

## hermes-agent-demo
- 定位：Spring Boot 4 + Spring AI 2.0.1 的多模型 Agent 运行时 demo
- 技术栈：Java / Spring Boot / Spring AI / SSE
- 亮点：
  - 子代理(Subagent)+MCP 委派、TODO 计划模式、Code Interpreter 沙箱（生成代码→沙箱执行→artifact 导出）
  - **Human-in-the-Loop**：命中 Write/Edit/Bash 白名单弹出审批——与主项目人机审批同思路
  - 外部工具平台预留（dify/n8n 对接为 tools_call）
- 对主项目价值：局部借鉴（主项目非 Java 栈，借鉴交互模式）
- 借鉴点：工具白名单审批交互、沙箱代码执行→artifact 预览的产物展示链路
- 评分：2

## hermes-agent-main
- 定位：hermes-agent 的完整主线版本（含可选 skills、acp_adapter 等）
- 技术栈：Python，`agent/` 26+ 模块，`skills/` 按 domain 分类 20+ 类
- 亮点：
  - `agent/skill_utils.py` + `skills/`（apple/creative/domain/github/mcp/red-teaming…）——**按领域组织的技能库**是"沉淀用户自己的 skills"的模板
  - `agent/context_compressor.py` + `prompt_caching.py`：上下文压缩与缓存工程
  - `acp_adapter/`：Agent Client Protocol 适配器（跨 agent 标准）
- 对主项目价值：直接借鉴
- 借鉴点：skills 按领域分类目录结构、acp_adapter 协议层（主项目未来可对外暴露 agent 标准接口）、模型元数据/usage 计价模块
- 评分：4

## hermes-agent-self-evolution-main
- 定位：用 DSPy + GEPA（遗传-帕累托提示词进化）自动进化 agent 的 skill/prompt/tool
- 技术栈：Python / DSPy / GEPA（ICLR 2026）
- 亮点：
  - **skill 进化闭环**：读当前 skill → 生成 eval 数据集（synthetic/golden/外部会话导入）→ GEPA 变异 → LLM-judge 多维打分（fitness.py：correctness 0.5 + procedure_following 0.3 + conciseness 0.2）→ 约束门禁 → PR
  - `evolution/core/constraints.py`：约束门禁（测试/尺寸/基准）防退化
  - 基于执行轨迹理解"为何失败"而非只知"失败了"（reflective mutation）
- 对主项目价值：直接借鉴（主项目 critic 自反思→可升级为"技能进化器"）
- 借鉴点：①SKILL.md 的自动进化流水线（变异→judge→门禁→PR）可直接指导主项目"训练用户自己的 skills"方向；②LLM-judge 多维 fitness 打分公式可复用到主项目 critic/评测
- 评分：5

## learn-agent
- 定位：从零搭建生产级 AI Agent Harness 的 20 章中文教程（每章一篇文章+可运行 TS 快照）
- 技术栈：TypeScript（教程语言），内容覆盖权限/Hook/Skill/上下文压缩/记忆/任务DAG/多Agent/Worktree/MCP
- 亮点：
  - **每章只加一个能力，P20 验证前 19 章在同一个 AgentRunner 协同**——"渐进叠加+总装验证"的教学法
  - 覆盖主项目全部 agent 关注点：四级压缩法、Skill 技能系统、Inbox 异步通信、Cron 调度器、去中心化认领
  - 理论文章+可运行代码双轨，直接可当主项目 agent 架构课的素材库
- 对主项目价值：直接借鉴（教学化方向的最强参考）
- 借鉴点：①主项目"小白易用/教学化"可复刻这套章节化教程+可运行快照；②四态权限决定（approve/deny/ask/ignore）与 Hook 生命周期可对照主项目审批
- 评分：5

## livekit__agents
- 定位：LiveKit 的实时多模态语音 agent 框架（服务器端可编程实时参与者）
- 技术栈：Python，STT/LLM/TTS/Realtime API 可插拔
- 亮点：
  - **多模态语音/视觉 agent**：语义转轮检测（transformer 判断用户说完）、RPC 数据交换、MCP 一行接入
  - 内置 job scheduling（dispatch API 把用户连到 agent）+ 内置测试框架（judges 评估）
  - WebRTC 全栈自托管
- 对主项目价值：扩展方向参考（主项目扩展"多模态/语音"场景的标杆）
- 借鉴点：若主项目扩展实时语音/视频 agent，其 dispatcher/job 调度 + 测试 judge 模式可移植；MCP 一行接入的插件设计
- 评分：3

## llama-agents
- 定位：文档中心的 Python agent/事件驱动工作流编排框架（llama-index 系）
- 技术栈：Python，packages/ 拆成 agentcore/appserver/client/control-plane/server/dbos 等 10+ 包
- 亮点：
  - **事件驱动 Workflow**：step 是 async 函数发/收事件，分支/循环/并行/持久化/失败恢复，纯 Python 无 DSL
  - 同库工作流可平滑升级：脚本 → FastAPI 内嵌 → 协调后端 → 复制扩容（"随你成长"）
  - `llama-agents-server` 把任意 workflow 包成 REST API（streaming+persistence+human-in-the-loop）
- 对主项目价值：局部借鉴（DAG 编排对照）
- 借鉴点：事件驱动 step 模型可对照主项目 DAG 编排；workflow 即 API 的"内嵌+独立部署"两用模式
- 评分：3

## llm-wiki-agent
- 定位：一个"编码 agent skill"——投喂文档自动构建互链知识 wiki
- 技术栈：纯 Markdown/目录+图谱（graph.json + graph.html），零 API 成本
- 亮点：
  - **知识自增殖**：`ingest raw/xxx.md` → 自动生成 index/log/overview/sources/entities/concepts/syntheses 结构
  - 交叉引用预建、矛盾自动标记、综合页（synthesis）自动生成
  - 输出人类可读的 Markdown wiki + vis.js 图谱，可浏览器打开
- 对主项目价值：扩展方向参考（知识库/记忆可视化）
- 借鉴点：主项目记忆层若做"跨会话知识沉淀"，可借鉴 ingest→wiki 结构（index/log/entities/concepts）与图谱可视化
- 评分：3

## mcp-agent-main
- 定位：用 MCP + 简单可组合模式构建 agent 的框架（lastmile-ai）
- 技术栈：Python，`src/mcp_agent/`（agents/app/core/executor/human_input/elicitation/oauth/telemetry/tracing）
- 亮点：
  - 完整实现 Anthropic《Building Effective Agents》全部模式且可链式组合
  - **Temporal 持久化 agent**：pause/resume/recover 无需改 API——与主项目 DAG 断点续跑同思路的工业级实现
  - `human_input/` + `elicitation/`：人机交互与需求澄清模块
- 对主项目价值：局部借鉴（DAG 续跑/审批）
- 借鉴点：Temporal 式持久化续跑语义（checkpoint 恢复）、human_input 审批模块可对照主项目人机审批
- 评分：3

## memguard-agent
- 定位：LLM Agent 记忆库投毒的 eBPF 实时检测与告警系统（叠加层 overlay）
- 技术栈：eBPF (kprobe) + Rust (libbpf) + 企业微信/ServerChan 告警
- 亮点：
  - **写入瞬间检测**记忆投毒（FARMA/MINJA 类攻击）：内核态 kprobe 捕获 vfs_write + 窗口匹配 15 条中英文签名
  - 对 Agent 零侵入、dry-run 默认安全上线、FS 补偿读解决 SQLite 整页写入盲区
  - 告警时间窗聚合防风暴
- 对主项目价值：局部借鉴（安全方向）
- 借鉴点：主项目记忆层（L1-L3 巩固+supersede）可增加"写入侧投毒签名检测"（无需 eBPF，可在应用层 memory store 写入钩子实现）；dry-run 默认安全的设计理念
- 评分：3

## mercury-agent
- 定位：Soul-driven AI agent（CLI/Telegram/Web 多渠道 24/7，31 内置工具 + Kanban + SQLite 第二大脑记忆）
- 技术栈：TypeScript / Node.js，`src/`（core/soul/memory/channels/capabilities/skills）
- 亮点：
  - `src/core/` 质量极高：execute-guard、memory-governor/memory-guard（记忆预算护栏）、stall-watchdog（卡死看门狗）、work-ledger、completion-verdict（完成判定契约）、file-lock、background-tasks——**每个都是主项目可对照的健壮性子系统**
  - `src/soul/identity.ts`：人格/身份文件驱动的角色系统
  - ADR 文档（DECISIONS.md）+ 架构文档完整；权限模式 Ask Me/Allow All
- 对主项目价值：直接借鉴（健壮性/护栏工程）
- 借鉴点：stall-watchdog（agent 卡死检测）、memory-governor（记忆写入预算护栏）、execute-guard（工具执行护栏）三个模块是主项目 agent 运行时的直接补强
- 评分：4

## microsoft__agent-framework-go
- 定位：微软 Agent Framework 的 Go 实现（生产级多 agent 工作流）
- 技术栈：Go，`agent/`（middleware/compaction/harness/skills/structuredoutput/session）+ `workflow/`
- 亮点：
  - **graph-based workflow**：顺序/并发/组协作/条件路由/子工作流/checkpoint/streaming/HITL/time-travel 全支持
  - middleware 管道（logging/OTel/context providers/tool approval/自动工具调用）
  - `agent/compaction/` + `agent/skills/` + `structuredoutput.go`：上下文压缩、技能、结构化输出独立成包
- 对主项目价值：局部借鉴（DAG 编排/中间件）
- 借鉴点：middleware 管道式工具审批与 OTel 埋点、compaction 独立包设计可对照主项目上下文管理
- 评分：3

## msitarzewski__agency-agents
- 定位："AI 特工局"——大量有性格/有流程的专家 agent 人格集合 + 桌面 App 一键安装到各 IDE
- 技术栈：Markdown agent 定义（多目录分类）+ 分发 App（macOS/Linux/Windows）
- 亮点：
  - **agent 人格工程**：每个 agent = 专长 + 独特 voice + 可交付流程，按 domain 目录（engineering/academic/design）组织
  - 桌面 App 浏览名册→一键安装进 Claude Code/Cursor/Codex/Gemini 等 7+ 平台并自动更新——**agent 市场的分发模式**
  - `divisions.json`：agent 名册索引
- 对主项目价值：直接借鉴（agent 生态/小白易用）
- 借鉴点：①主项目可做"预置 agent 人格库"+一键安装进环境的体验；②divisions.json 式名册索引可进主项目 agent 管理页
- 评分：4

## multi-agent-deep-researcher
- 定位：Langflow 可视化多 agent 深度研究流（13 节点 12 连接）
- 技术栈：Langflow / LangChain / LangGraph
- 亮点：
  - Agent 间信息流 + Web 搜索 + URL 检索研究工具链
  - 可视化编排导出为 JSON（可复用/共享研究流）
- 对主项目价值：无价值（浅 demo，价值已含于其它项目）
- 借鉴点：多 agent 研究流水线（搜索→URL 抽取→综合）可作为主项目 agent 扩展场景的原型参考
- 评分：1

## mythos-agent-pipe
- 定位：Claude Opus 的"先计划-执行-验证-交付"四阶段交付流水线（Plan/Execute/Verify/Ship）
- 技术栈：单页 HTML（index.html + WebSocket 状态仪表盘）
- 亮点：
  - 质量门禁思想：blueprint → execution → validation → artifact shipping，"Verify before ship"
  - 实时状态仪表盘 + AI 工单分诊 + 人工升级回退
- 对主项目价值：无价值（理念宣传单页，无工程实现）
- 借鉴点：Plan/Verify/Ship 四阶段门禁语义与主项目"审批+DAG续跑"理念一致，仅理念参考
- 评分：1

## oh-my-openagent
- 定位：多模型 agent 编排 CLI（Team Mode，多模型协作），主打"不被单一厂商锁定"
- 技术栈：TypeScript / bun，可对接 Kimi/GPT/OpenCode 等
- 亮点：
  - 多模型 Team Mode 编排（各 agent 用不同模型/角色）
  - 与 omo-herdr-dag 联动做实时 workflow DAG 可视化侧栏
- 对主项目价值：局部借鉴
- 借鉴点：多模型混排的 team 编排 + DAG 可视化侧栏可对照主项目 MAB 路由与 DAG 面板
- 评分：2

## okf-agent-memory
- 定位：基于 Google OKF v0.2 的 Git 原生持久项目记忆层（Go 实现）
- 技术栈：Go（零依赖）+ Markdown+YAML frontmatter + BM25 本地检索 + MCP 就绪
- 亮点：
  - **渐进式披露（Progressive Disclosure）**：层级 index.md + 链接图，agent 只加载所需概念——直击上下文膨胀
  - 100% Git 原生、零向量 API 成本、来源溯源（provenance）+ 信任层级（generated/verified）+ 过期元数据（stale_after）
  - 300µs 检索、4ms 图校验
- 对主项目价值：直接借鉴（记忆层设计）
- 借鉴点：①provenance/trust-tier/stale 元数据模型可升级主项目记忆 L1-L3；②渐进式披露（index+link graph）解决主项目记忆召回上下文膨胀；③本地 BM25 零 API 成本检索
- 评分：4

## okf-memory__okf-agent-memory
- 定位：okf-agent-memory 的镜像克隆（内容与上一致，git 元数据不同）
- 技术栈：同 okf-agent-memory（Go）
- 亮点：与 okf-agent-memory 代码内容一致（diff 仅 .git 内部差异），属重复收录
- 对主项目价值：与上条合并评估，不再重复
- 借鉴点：见 okf-agent-memory
- 评分：4

## open-ai-agents-hub
- 定位：开源"AI agent 中心"——浏览/构建/聊天 agent，含 LLM chat 与媒体生成（图片/视频/音频）agent
- 技术栈：Next.js 前端 + FastAPI 代理后端 + React Flow 画布
- 亮点：
  - **agent 即可复用可分享单元**：system prompt + 目标能力（chat/图像/视频/音频）+ 独立 profile 页/slug/会话历史——媒体生成与聊天同界面并列
  - Agent builder 可视化（React Flow 画布）创建/编辑 agent
  - 自带 Key 的薄代理层（无供应商锁定）+ 建议 agent 推荐端点
- 对主项目价值：直接借鉴（扩展场景"图片/视频/音频"高度对口）
- 借鉴点：①媒体生成 agent 与 chat agent 统一界面的 agent 库/构建器可进主项目；②slug+profile 分享页；③按意图推荐 agent 的端点可进主项目意图识别层
- 评分：4

## open-multi-agent-main
- 定位：TypeScript 多 agent 编排框架（`runTeam()` 一调到底：自动分解任务 DAG + 并行执行 + 综合）
- 技术栈：TypeScript，仅 3 运行时依赖（anthropic/openai/zod），27 源文件
- 亮点：
  - **coordinator 自动分解目标→任务 DAG（带依赖+指派）→并行跑→综合**——与主项目 DAG 编排同构的极简实现
  - `src/orchestrator/scheduler.ts`（352 行）+ orchestrator.ts（1022 行）可整读，教学价值高
  - `outputSchema`（Zod）结构化输出+失败自动重试一次；onTrace 回调零开销可观测；任务级 maxRetries+指数退避+token 计费
- 对主项目价值：直接借鉴（DAG/任务/计费）
- 借鉴点：①task 依赖解析+并行调度器实现可对照主项目 DAG；②onTrace 零开销可观测回调（runId 关联）可进主项目 SSE/trace；③Zod outputSchema 校验+重试模式
- 评分：4

## orca-agent
- 定位：DeepSeek 原生的终端编码 agent（Rust，TUI + `orca exec` 无头模式）
- 技术栈：Rust，crates/ 分 10+ 模块（approval/core/file-search/mcp/platform/provider/runtime/tools/tui/windows-sandbox）
- 亮点：
  - Windows 原生沙箱（orca-windows-sandbox + setup）——Windows 平台的受限沙箱能力预置
  - approval 独立 crate（工具审批）、mcp 独立 crate
  - 读取代码→编辑→跑命令→验证→完成 的闭环，TUI 与 headless 双模式
- 对主项目价值：局部借鉴（Windows 平台/审批）
- 借鉴点：Windows 沙箱提权模式（主项目 cf_solver/desktop 在 Windows 上可参考）；approval crate 的工具审批边界
- 评分：3

## page-agent
- 定位：阿里巴巴的 GUI agent——一行脚本给任意网页装上一个 AI agent（免浏览器扩展）
- 技术栈：TypeScript，纯页面内 JS
- 亮点：
  - 页面内 agent：无需扩展/无头浏览器/Python，DOM 操作全在页面内完成
  - 轻量（minzipped 小包）、一键集成
- 对主项目价值：扩展方向参考（网页自动化/多模态操作）
- 借鉴点：若主项目扩展"网页操作/电商页面自动化"，其 in-page agent 注入模型是低成本方案
- 评分：2

## pentest-agents
- 定位：Claude Code + 6 个 AI 编码工具的开源漏洞赏金框架（50 agents / 26 commands / 11 skills / 2 MCP servers）
- 技术栈：Python 3.10+ / Markdown 定义 / MCP，`providers/` 按 IDE 输出原生格式
- 亮点：
  - **跨 IDE 发射器**：scaffold.py 为每平台生成原生格式（CLAUDE.md/AGENTS.md/.codex/...）——多平台 agent 资产分发工程
  - skills 按漏洞类型组织（hunt-xss/rce/idor/oauth + hunting-methodology/triage-validation）——**方法论沉淀为 skill** 的范本
  - hooks 成本追踪（PreToolUse scope 检查 + PostToolUse/SubagentStop/Stop 计费）
  - 7-Question Gate 验证 + A→B exploit chain + 持久化 brain
- 对主项目价值：局部借鉴（安全/技能工程）
- 借鉴点：①"方法论→skill"（recon/hunting/triage）沉淀模式可进主项目 skills；②hooks 成本追踪体系（PreToolUse 拦截 + SubagentStop 计费）可对照主项目预算门禁
- 评分：4

## pi-agent-desktop
- 定位：Pi 编程智能体的原生桌面客户端（Electron，"个人极简版 Codex"）
- 技术栈：Electron + React + TypeScript，SSE 流式
- 亮点：
  - 桌面交互工程完整：会话浏览器/分叉( Branch )/克隆到 Git Worktree、Project Trust 409 握手授权、Extension UI Bridge（confirm/select/input/editor/notify 原生弹窗）
  - **LTM 长期记忆**：项目级 SQLite 记忆（memory_save/recall/forget），中文/日韩走 FTS5 trigram，agent_end 与 compact 前自动观察写入——与主项目桌面 Tauri sidecar 高度可对照
  - 消息队列（Enter steer / Alt+Enter 排队）、MCP/Skill 统一管理 UI
- 对主项目价值：直接借鉴（桌面端交互/记忆/信任）
- 借鉴点：①Project Trust 409 握手授权可进主项目桌面端安全模型；②Extension UI Bridge 的审批弹窗协议；③LTM FTS5 trigram 记忆检索（中文友好）可升级主项目记忆检索
- 评分：4

## pi-agenticoding
- 定位：Pi 的可组合工作流层（saved prompts/skills 定义任务工作流）
- 技术栈：TypeScript / npm 扩展包
- 亮点：
  - **Model Groups**：角色与供应商解耦（`model-groups/`：modality/constraints/router/store）——模型按能力槽分配
  - **handoff**（deliberate restarts）：下一阶段不拖拽旧 transcript 的干净交接；notebook 只承载 canonical 决策
  - 声明式策略：权限/上下文边界/短生命共享记忆都进 workflow 定义
- 对主项目价值：局部借鉴（工作流/上下文边界）
- 借鉴点：①handoff 的"刻意重启"可对照主项目 DAG 断点续跑（阶段间干净交接）；②model-groups 按能力槽（text/vision/code）路由可增强主项目模型路由
- 评分：3

## pi-interactive-subagents
- 定位：Pi 的异步子代理（多路复用器 pane 中后台跑，主 agent 不阻塞）
- 技术栈：TypeScript / cmux/tmux/zellij/WezTerm
- 亮点：
  - `subagent()` 立即返回，子代理在独立 pane 运行，状态 widget 实时显示（starting/active/waiting/stalled/running），完成后结果以异步通知 steered 回主会话
  - 卡死检测（stalled 状态）+ 并发多子代理独立回传
- 对主项目价值：局部借鉴（并行子代理 UX）
- 借鉴点：子代理状态机（含 stalled 卡死态）与"结果异步回灌主会话"的交互可对照主项目 DAG 并行节点 UI
- 评分：3

## pim-agent
- 定位：Pi 的 Bun 原生扩展包（web 访问/子代理/主题/fzf 补全/Telegram 模式），Terminal-Bench 2.0 达 37.8%
- 技术栈：Bun / TypeScript
- 亮点：
  - 精简系统提示词 + model-aware tools（按模型能力裁剪工具集）——低成本提分设计
  - Telegram 机器人模式 + 扩展包分发（pi install）
- 对主项目价值：局部借鉴
- 借鉴点：model-aware tools（按模型能力动态裁剪工具）可对照主项目 agent 工具集管理
- 评分：2

## prime-agent
- 定位：Prime Intellect 的"自改进 RLM Harness"（递归语言模型 + 持续 Harness 状态）
- 技术栈：TypeScript + Python 控制环境
- 亮点：
  - **RLM**：context 视为变量（prompt-as-a-variable）+ 递归子代理工具调用，常驻 REPL
  - **Continual Harness**：补充 prompts/memories/skill 描述/子代理规格存为持久态，通过小步证据支撑更新自我精炼（默认会话内局部）
- 对主项目价值：局部借鉴（agent 状态持久化）
- 借鉴点：harness 持久态（memory+skill 描述+子代理规格随会话自我精炼）可对照主项目记忆/技能沉淀
- 评分：3

## ragent
- 定位：面向 Agentic RAG 演进的生产级 Java AI 应用平台（后端转 AI 工程师学习站）
- 技术栈：Java / Spring AI，模块 agent/framework/mcp-server/rag/infra-ai/frontend
- 亮点：
  - **混合检索**（向量+关键词+知识图谱+联网 并行召回→去重→RRF 融合→Rerank）与树形意图识别、多知识库路由
  - 首包探测 + 熔断降级（模型档位）、Redis 公平排队/分布式并发控制（流量保护）
  - 回答溯源 + 用户反馈 + Trace + 管理后台（知识闭环）
- 对主项目价值：局部借鉴（检索/路由/流量保护）
- 借鉴点：①RRF 融合+去重+Rerank 混合检索管线可进主项目 RAG；②首包探测/熔断/公平排队可对照主项目 MAB+熔断+队列
- 评分：3

## remcocats__opencode-agents
- 定位：OpenAgents——计划优先 + 审批执行的开发工作流框架（多语言 TS/Python/Go/Rust）
- 技术栈：TypeScript + OpenCode CLI，registry.json + evals/
- 亮点：
  - **plan-first**：agent 先提计划再实施，逐步执行 + 每步校验；自动测试/类型检查/代码审查内建
  - 遵循上下文文件（coding standards 进入 agent 行为）；evals/ 有评估集
- 对主项目价值：局部借鉴
- 借鉴点：plan→approve→step-execute→validate 的工作流语义与主项目人机审批/计划模式一致，可对照 UI 与协议
- 评分：3

## tigerless-labs__agent-memory
- 定位：任意 agent 的长期记忆运行时（Markdown 存储单一事实源 + SQLite 索引缓存，零 API key）
- 技术栈：Python，packages/（adapters/cli/core/executor/harness/mcp）
- 亮点：
  - **两级架构合一**：检索引擎索引一个 agent 也能直接 ls/grep 的 Markdown 文件系统——图/向量精度 + 文件系统可读性兼得
  - 检索按路径回答（L0 列表：摘要+路径+锚点+得分），agent 按需深度展开（L0/L1 outline/full）——省上下文
  - 写入不依赖 agent 记性：会话边界自动写，睡眠时按价值 consolidate/forget
- 对主项目价值：直接借鉴（记忆检索 UX）
- 借鉴点：①按路径+分级深度展开（L0 列表）替代贴正文——主项目记忆召回直接可用；②会话边界自动写 + 睡眠 consolidate/forget 调度
- 评分：4

## tintinweb__pi-subagents
- 定位：把 Claude Code 式自主子代理/工作流编排带到 Pi 的扩展
- 技术栈：TypeScript，pi 扩展
- 亮点：
  - 功能密度极高：并行后台 agent（并发限流+分组 join）、FleetView 实时会话查看、**mid-run steering**（运行中注入消息重定向）、session resume、**SubagentWorkflow 脚本**（agent()/parallel()/pipeline()/phase() + gate: 命令验证 + resume 标签，node:vm 沙箱防 eval）
  - 三层记忆（project/local/user）、git worktree 隔离、工具 denylist、模型范围强制、事件总线 RPC、定时子代理（cron）
  - 优雅 turn 限制（wrap-up 预警再硬中断，产出干净部分结果）
- 对主项目价值：直接借鉴（子代理编排/工作流脚本）
- 借鉴点：①`SubagentWorkflow` 确定性脚本（agent/parallel/pipeline + gate 命令验证）是主项目 DAG 可视化的强大对照；②mid-run steering 可进主项目断点续跑交互；③优雅 turn 预警再中断
- 评分：4

## trae-agent-main
- 定位：字节跳动 Trae Agent——研究友好的模块化软件工程 agent（arXiv 技术报告）
- 技术栈：Python 3.12，trae_agent/（agent/prompt/tools）+ server/ + evaluation/
- 亮点：
  - **Lakeview**：对 agent 步骤生成简短摘要（黑匣子打开/可观测性）
  - trajectory recording 详细记录全部动作 + evaluation/ 消融实验支持（研究友好）
  - 多 LLM 供应商 + YAML 配置 + 交互/无头双模式
- 对主项目价值：局部借鉴（可观测性）
- 借鉴点：①Lakeview 步骤摘要可进主项目 agent 执行页（黑匣子打开）；②trajectory 录制→重放/评测可支撑主项目 critic 与技能训练
- 评分：3

## wild_agentos
- 定位：Rust 工业级 Agent OS（知识图谱内核 + 隔离契约 + Skill 市场）
- 技术栈：Rust / gRPC / Oxigraph 知识图谱 / 多模态路由
- 亮点：
  - **隔离契约（IsolationClaims）**：JWT 租户/项目 claims 裁剪 graph/blob/vector 目标，fail-closed——生产级多租户安全
  - **Skill 市场**：版本化包 + 不可变版本 + 安装/升级/回滚；**emergent-tool 提权管道**：生成的工具在 sandbox/judge 门禁 + 人工审批通过前保持不可信
  - 多模态能力槽（Chat Slot→XX 模型 / Vision Slot→YY 模型）+ 因果引擎 + 快照时间线回滚
  - Skill CI 门禁（验证 + golden 输入输出检查）
- 对主项目价值：直接借鉴（安全/技能市场/多模态）
- 借鉴点：①"生成的工具不可信，须 sandbox+judge+人工审批才提权"——主项目 MCP/技能扩展的安全模型直接可用；②Skill 包版本化市场（安装/升级/回滚）可进主项目 skills 库；③多模态能力槽路由对照主项目扩展场景
- 评分：5

## yangqiong-agent-harness
- 定位：纯 Java 企业级 AI Agent 运行时（ReAct + 六大范式引擎 + 子代理/多代理 + 断点持久化 + 权限护栏）
- 技术栈：Java 17 / Reactor 响应式，零 Spring 依赖，Maven 多模块
- 亮点：
  - 六大范式引擎含自动路由、断点持久化执行、全链路可观测与评测一体
  - 企业级定位：强类型编译期校验工具定义、JVM 并发底座、安全合规（审计/权限）
  - 通过 Java 工具 + MCP 零重写对接存量企业系统
- 对主项目价值：无价值（Java 栈与主项目 Python/TS 不匹配；但范式清单可参考）
- 借鉴点：断点持久化、自动路由、评测治理三大件的能力清单可对照主项目 DAG/路由/评测
- 评分：2

---

## 本组汇总：Top3 最值得主项目借鉴项

1. **hermes-agent-self-evolution-main（技能进化闭环）** — DSPy+GEPA 变异 → LLM-judge 多维 fitness（correctness 0.5/procedure 0.3/conciseness 0.2）→ 约束门禁 → PR 的 SKILL.md 自动进化流水线，加上 hermes-agent 主线"复杂任务后自动沉淀 skill + skill 使用中自改进"，**正好落地主项目关注方向①"沉淀训练用户自己的 skills"**，可与主项目 critic 自反思合并升级为"技能进化器"。评分 5。

2. **wild_agentos（安全边界 + Skill 市场 + 多模态能力槽）** — ①"生成的工具默认不可信，须 sandbox+judge 门禁+人工审批才提权"的 emergent-tool 管道，是主项目 MCP/skills 扩展的安全模型直接范本；②版本化不可变 Skill 包市场（安装/升级/回滚）匹配主项目 skills 库分发；③Chat/Vision 能力槽多模态路由支撑主项目扩展场景。评分 5。

3. **learn-agent（教学化 20 章 + 可运行快照）与 easy-agent-main（step1~12 渐进工程）** — "每章只加一个能力、最后同一个 Harness 总装验证"的渐进教学法 + 可运行代码快照，是主项目"黑匣子打开/教学化/小白易用"方向的**最强落地模板**；配合 hermes 的闭环学习与 open-ai-agents-hub 的媒体 agent 统一界面，即可覆盖主项目三个关注方向的骨架。评分 5/3。

**次优递补**：hAcKlyc__MyAgents（想法→任务状态机 + bundled-skills 预置包 + IM 渠道工具 deny）、mercury-agent（stall-watchdog / memory-governor / execute-guard 护栏三件套）、tigerless-labs__agent-memory（按路径 L0 列表分级展开的记忆召回）、tintinweb__pi-subagents（SubagentWorkflow 确定性脚本 + mid-run steering）、open-multi-agent-main（task DAG 调度器 + 零开销 onTrace）、okf-agent-memory（provenance/trust-tier/stale 记忆元数据 + 渐进式披露）。
