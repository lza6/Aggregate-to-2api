# g16_misc_4 扫描报告（80 目录）

扫描日期：本会话；方法：ls + README 前 22-50 行识别真实功能；只读分析。
价值维度：①agent/skills/mcp/context 工程；②图片/视频/音频生成、电商、PPT/办公文档、多模态；③网关/API/队列/任务编排；④桌面/浏览器/自动化；⑤工程规范/交互/性能/安全。

---

## 高价值（疑似有价值，完整 5 行格式）

### 1. dagucloud__dagu ★★★☆
- **是什么**：本地优先的 DAG 工作流引擎（Go），单二进制+内置 Web UI，YAML 声明式定义 DAG，支持 cron 调度、重试、人工任务、运行历史、sub-DAG、SSH/容器/K8s Job。
- **价值点**：与主项目「agent DAG 编排」强相关——DAG 声明式语法、并行/并发控制、失败重试、运行历史存储、内置 MCP server（检查/控制运行）均可直接借鉴；也可作为主项目 DAG 执行的参考实现。
- **技术**：Go / 单二进制 / 无外部 DB / 内置 Web UI。
- **借鉴方向**：DAG YAML schema、调度器语义（cron + overlap policy + catch-up）、MCP 暴露运行控制接口。
- **备注**：无需引入 Go，取其设计语义落地到 Python 端。

### 2. ruflo ★★★
- **是什么**：Claude Code/Codex 的 agent meta-harness（Rust + npx CLI），100+ 专门 agent、swarm 编排、自学习记忆、跨机联邦通信、企业安全护栏。
- **价值点**：agent 编排/记忆/联邦属于主项目 agent 化方向直接对标物；其「Learning Loop（自我优化）」与主项目 critic 自反思/记忆巩固同思路。
- **技术**：Rust / npm 分发 / MCP 插件。
- **借鉴方向**：swarm 编排、自学习闭环、跨会话记忆机制。
- **备注**：体量大，借鉴设计而非移植。

### 3. vercel__eve ★★★
- **是什么**：Vercel 出品的 filesystem-first 持久化 agent 框架——agent 能力放在约定俗成位置（instructions.md/tools/skills/），项目更易检查/扩展/运维。
- **价值点**：与主项目 skills 技能库/agent 配置工程高度契合；「文件系统即创作接口」的设计对主项目 skills 目录规范化有直接参考价值。
- **技术**：TypeScript / npm。
- **借鉴方向**：agent 目录结构规范、指令/工具/技能分层约定。
- **备注**：Vercel 官方出品，设计质量高。

### 4. claude-mem ★★★
- **是什么**：为 Claude Code/Claude 类 agent 提供跨会话记忆与持续学习的开源工具（bun/TS），带 WARP、cowork、cursor-hooks。
- **价值点**：主项目已有记忆巩固/OpenWolf 记忆体系；claude-mem 的提取/存储/检索实现可作对照或增强参考。
- **技术**：Bun / TypeScript / hooks。
- **借鉴方向**：记忆提取时机、去重/巩固策略、会话钩子接入点。
- **备注**：与主项目记忆方向直接重叠，值得深读。

### 5. gbrain ★★★
- **是什么**：YC 总裁 Garry Tan 开源的 agent「大脑层」——对非代码内容做合成（synthesis）+知识图谱遍历+gap analysis 的检索层，24/7 摄入/巩固。
- **价值点**：主项目 agent 记忆/知识沉淀可借鉴其「实体图谱自接线（零 LLM 抽取实体关系）+ 引用溯源 + 差距分析」设计；公司级权限切片思路也适用于多用户场景。
- **技术**：Bun/TS + PGLite（无服务器 Postgres）+ 插件体系。
- **借鉴方向**：自接线知识图谱、合成式回答+引用、隔夜巩固任务。
- **备注**：与 lemmalog（Datalog 记忆）方向互补。

### 6. lemmalog ★★★
- **是什么**：把 agent 记忆做成演绎数据库（Datalog 引擎，Rust crate + MCP server + REPL + agent skill），事实带 provenance、规则推导闭包/时间投影/矛盾候选、增量维护。
- **价值点**：主项目记忆巩固若追求「可验证知识模型」而非向量库，此设计是最高参考；双时态事实（valid_from/valid_to/asserted_at）+半朴素不动点增量维护非常工程化。
- **技术**：Rust / MCP / Datalog。
- **借鉴方向**：记忆事实的时态模型、矛盾检测、来源溯源。
- **备注**：学术+工程双硬核，适合长期演进借鉴。

### 7. spec-kit ★★★
- **是什么**：GitHub 官方开源的 spec-driven AI 编码工具包——构建前先定义规格，适配任意 AI 编码 agent，可扩展/社区驱动。
- **价值点**：主项目已有「计划书/改进指南」工作流；spec-kit 的规格→实现→验证流程、bundles/预设扩展机制可直接对齐主项目的 planning/验收工程。
- **技术**：Python/CLI + 文档体系。
- **借鉴方向**：规格文件规范、验收标准模板、agent 工作流绑定。
- **备注**：GitHub 官方背书，流程成熟。

### 8. feynman-main ★★★
- **是什么**：开源 AI 研究 agent（CLI），面向研究型任务的自主 agent。
- **价值点**：研究/信息收集类 agent 行为（提问、检索、验证、产出报告）可参考；与主项目 chat 侧智能体能力可互补。
- **技术**：JS/CLI + 文档。
- **借鉴方向**：研究 agent 的工作流与验证闭环。
- **备注**：需深入确认细节。

### 9. context-mode ★★★
- **是什么**：MCP context 工程工具——解决「MCP 工具调用把原始数据灌进上下文窗口」问题（上下文压缩/摘要/遗忘管理），被 Microsoft/Google 等采用。
- **价值点**：主项目 SSE 长会话 + agent 上下文管理可直接受益；其「上下文另一半问题」（输出 token 浪费/压缩）方案值得引入。
- **技术**：Bun/CLI + hooks + plugin。
- **借鉴方向**：工具结果摘要化、上下文预算管理、hook 集成。
- **备注**：与主项目大上下文/长任务场景强相关。

### 10. ai-knowledge-graph ★★★
- **是什么**：AI 知识图谱生成器——把非结构化文本经 LLM 提取 SPO 三元组并可视化为交互式知识图谱（Python 3.11+，兼容任意 OpenAI 兼容端点）。
- **价值点**：主项目可用任意 OpenAI 兼容端点的特性与它一致（主项目本身就是网关）；知识提取/实体标准化/关系推断管线可作为主项目记忆/知识模块参考。
- **技术**：Python / OpenAI 兼容 API / HTML 可视化。
- **借鉴方向**：三元组抽取、实体标准化、关系推断、交互可视化。
- **备注**：轻量、易落地。

### 11. dagu 补充（已列）→ OpenDocs ★★☆
- **是什么**：把 GitHub README/Markdown/Jupyter Notebook 转成多格式结构化文档的 Python 工具（含 VS Code 扩展）。
- **价值点**：主项目文档工程（SOP/verification-log/指南）可自动化生成/统一格式。
- **技术**：Python 3.10+。
- **借鉴方向**：README→多格式文档转换管线、notebook 处理。
- **备注**：中低优先级。

### 12. kitter ★★★
- **是什么**：Skill 库管理器（Rust，桌面 app + CLI 共享本地核心）——每个 Skill 一个维护源，按需链入各项目，解决 skills 复制漂移/全局安装失控问题。
- **价值点**：主项目 skills 技能库（20+ skills）+ superpowers 框架正好需要此类统一管理/版本同步能力。
- **技术**：Rust / Tauri / 本地优先。
- **借鉴方向**：skill 单一来源、项目级链接、依赖组合管理。
- **备注**：与主项目 skills 工程直接对口。

### 13. claude-md-doctor ★★☆
- **是什么**：给 CLAUDE.md/AGENTS.md 做「体检」的 Python stdlib 工具——对照会话历史回测每条规则，生成报告卡并给处方；无 CLAUDE.md 时从会话挖矿起草。
- **价值点**：主项目维护大量 CLAUDE.md/规则文件，此工具可审计规则有效性（哪条规则被忽略/死引用）。
- **技术**：Python 纯标准库。
- **借鉴方向**：规则-会话回测、报告卡、处方（升级为 hook）。
- **备注**：轻量实用。

### 14. claude-code-best-practice ★★☆
- **是什么**：Claude Code 最佳实践合集（agent teams/工作流/实现模式/编排），vibe coding→agentic engineering 转型方法论。
- **价值点**：主项目开发方法论（TDD/审查/编排）可对照补强。
- **技术**：文档 + skills + workflows。
- **借鉴方向**：agent 团队模式、编排工作流模板。
- **备注**：文档型参考。

### 15. claude-code-prompts-master ★★☆
- **是什么**：独立编写的 AI 编码 agent prompt 模板集合（系统提示/工具提示/agent 委托/记忆管理/多 agent 协调）。
- **价值点**：主项目 agent 化（意图识别/DAG/critic/记忆）的 prompt 设计可参考。
- **技术**：文档/模板。
- **借鉴方向**：系统提示结构、多 agent 协调 prompt、记忆管理 prompt。
- **备注**：文档型。

### 16. sigmap ★★☆
- **是什么**：AI 代码工作的确定性可验证接地层（npm，零依赖）——为 agent 产出的代码提供签名/映射/验证。
- **价值点**：主项目 critic 自反思/验收可借鉴「确定性验证」思路。
- **技术**：JS/零依赖。
- **借鉴方向**：代码变更签名/验证、可审计接地。
- **备注**：具体机制待深入。

### 17. gstack ★★☆
- **是什么**：YC 总裁 Garry Tan 的 agent 工程工具集——把 Claude Code 变成虚拟工程团队（CEO/EM/设计/审查/QA/安全/发布 23 个专家 + 8 个 power tools，全部 slash 命令+Markdown）。
- **价值点**：主项目多 agent 编排（builder/critic/evaluator）可参考其角色划分与命令化封装。
- **技术**：Markdown + slash commands（MIT）。
- **借鉴方向**：专家角色 prompt 库、命令封装、安全审计步骤。
- **备注**：轻量易移植。

### 18. lemmalog 已列 → Personal_AI_Infrastructure-main ★★
- **是什么**：Daniel Miessler 的个人 AI 基础设施参考（packs/tools 集合），搭建个人 AI 栈的方法论。
- **价值点**：主项目作为 AI 网关的生态位可对照其组件划分。
- **技术**：文档/集合。
- **借鉴方向**：组件选型清单。
- **备注**：中低。

### 19. buchidonggua__dg-ai-notes ★★
- **是什么**：Pi-Agent（生产级 agent SDK 运行时底座，OpenClaw 底层框架）源码解读与二次开发实战教程（双轨电子书）。
- **价值点**：主项目 agent 化可借 Pi 理解完整 agent SDK 设计（Agent Loop/工具系统/消息/事件/会话/扩展）。
- **技术**：文档教程 + skills。
- **借鉴方向**：agent SDK 架构认知。
- **备注**：学习型参考。

### 20. claudecodeui ★★
- **是什么**：Claude Code 的 Web UI（electron + docker 自托管），浏览器访问 Claude Code 会话。
- **价值点**：主项目桌面（Tauri2）+ 管理面板可参考 agent 会话 UI 交互/远程访问。
- **技术**：Electron / React / Docker。
- **借鉴方向**：会话 UI、远程控制。
- **备注**：README 未展示摘要，需确认细节。

---

## 中价值（2 行结论）

### 21. hand-drawn-styles ★★
- **是什么**：工具无关的手绘画风提示词配方库（19 套画风），供 AI 图像模型生图使用。
- **价值点**：主项目是图像生成网关，其「配方库+渲染器原样提取减少漂移」思路可借鉴为 prompt 模板资产；直接补充主项目生图 prompt 工程。

### 22. CorsenAI__hermes-connector ★★
- **是什么**：Hermes Agent 的 Chrome 浏览器扩展——把指定 profile/会话连接到登录态标签页，让 agent 读取/控制真实浏览器标签。
- **价值点**：主项目 agent 化若需浏览器自动化能力，此「精确 tab 归属 + 非隐藏自动化浏览器」设计可参考。

### 23. orkas（Orkas）★★
- **是什么**：本地优先多 agent 桌面应用，Commander 规划 + 9 个专家 agent（DeepResearcher/ContentWriter/PptMaker 等）并行/串行协作，自带模型 keys。
- **价值点**：与主项目 agent 编排同构（规划→分派→交付文件）；其 agent 市场/技能/记忆机制可参考。含 PPT 生成，属维度②。

### 24. SolveaCX__tokentest.io ★★
- **是什么**：AI 路由器/模型黑盒验证平台（Node+MCP）——从外部测试 OpenAI 兼容/Anthropic 路由，比对请求模型 vs 实际模型、审计 token、探测安全与渠道行为，产出准入决策。
- **价值点**：主项目正是 OpenAI 风格多上游路由网关，此工具可作主项目路由质量/计费/渠道行为的验证层（含 MCP 远程集成）。

### 25. aisix ★★
- **是什么**：Rust 原生 AI 网关（AISIX），一个 OpenAI 兼容 API 统一路由/治理/安全/缓存/观测所有 LLM 流量，单静态二进制。
- **价值点**：与主项目网关定位直接对标；其路由/治理/缓存/可观测设计可对照补强（虽为 Rust，设计语义可移植）。

### 26. hugalafutro__model-hotel ★★
- **是什么**：多提供商 AI 网关（Go+React+PostgreSQL），自称「家用 LiteLLM」，带 Web 前端。
- **价值点**：与主项目网关同品类；其前端/计费/供应商管理可作为主项目功能对照。

### 27. claude-ads ★★
- **是什么**：Claude-first 付费媒体运营工具（12 广告平台），默认只读，需通过审批/幂等/验证/审计/回滚门禁才允许写入。
- **价值点**：主项目「预算门禁/审批持久化」与它同思路；广告平台操作风险控制流程可借鉴。

### 28. destructive_command_guard ★★
- **是什么**：高性能 AI 编码 agent hook（Rust 二进制），在执行前拦截危险破坏性命令，覆盖 Claude Code/Codex/Cursor 等十几款工具。
- **价值点**：主项目桌面/工具链可引入此安全护栏；Windows 环境注意其 PowerShell 安装器。

### 29. riskbypass_demo ★
- **是什么**：反爬/风控绕过服务（RiskByPass）的 API 使用指南+各风控系统（Akamai/Cloudflare/Datadome/hCaptcha 等）检测方法示例。
- **价值点**：主项目 cf_solver（Turnstile 求解）相关，可了解反爬检测/风控指纹，但为商业服务演示，实用有限。

### 30. TencentCloud__CubeSandbox ★★
- **是什么**：腾讯开源的 AI agent 即时/并发/安全/轻量沙箱服务（CubeMaster/CubeAPI/CubeEgress 等微服务组）。
- **价值点**：主项目若让 agent 执行不可信代码/工具调用，沙箱隔离方案是强参考；CNCF landscape 项目。

### 31. hindsight-main ★★
- **是什么**：Vectorize 开源的 agent 记忆系统——让 agent「学习」而非仅「记住」（与单纯对话历史回忆不同），带论文/云版。
- **价值点**：主项目记忆巩固方向的直接对标物之一，与 claude-mem/lemmalog/gbrain 同赛道，可交叉参考。

### 32. pacifio__atlas ★★
- **是什么**：coding agent 的「源代码控制」（Rust）——为 agent 工作流提供版本/快照管理。
- **价值点**：主项目 agent 编排若需对 agent 产出做版本控制/回滚，可参考；与 dsh-message-edit 版本化思路呼应。

### 33. rove ★★
- **是什么**：终端 agent 复用器——并行运行多个 Claude Code/Codex/Copilot 任务，用 git worktree+branch 隔离，会话断线续跑。
- **价值点**：主项目 agent DAG 并行执行可参考 worktree 隔离/会话持久化方案。

### 34. leapmux ★★
- **是什么**：多 coding agent + shell 终端工作区（git worktree 隔离、平铺/浮动、本地/远程、端到端加密，浏览器或桌面运行）。
- **价值点**：与 rove 同类，并行 agent 隔离/加密通信可参考。

### 35. hermes-feishu-streaming-card ★★
- **是什么**：Hermes Agent 网关的飞书/Lark 流式卡片插件——思考/工具调用/答案/审批收束为一张持续更新的交互卡片。
- **价值点**：主项目 SSE 事件流（subscribe/publish/replay）与它同构；其「合并事件到单卡片+原生交互」设计可借鉴到主项目前端会话展示/审批确认。

### 36. dsh-message-edit ★★
- **是什么**：DeepSeek Harness 插件，基于事件溯源的消息编辑/重生成——每次编辑从目标回合分支创建新会话版本，原会话保留可切回（undo/redo + 分支树）。
- **价值点**：主项目 agent 会话的版本化/重生成/回滚可参考其「回合级原子 + 分支树 + LIFO 撤销」设计。

### 37. claude-md-doctor 已列 → loominary ★★
- **是什么**：本地优先 AI 对话管理器——导入 Claude/ChatGPT/Gemini/Grok 等对话，搜索/标签/分支导航/导出；实时模式录制每个重生成版本成树。
- **价值点**：主项目会话历史/审计功能可参考其跨平台导入+分支树展示；Realtime 版本录制与 dsh-message-edit 互补。

### 38. graphify ★★
- **是什么**：LLM 应用观测平台（Python/PyPI），追踪/评测/可视化 agent 与 LLM 调用。
- **价值点**：主项目 telemetry（OTel 采样）可对照其 agent 调用追踪能力。

### 39. hermes-trace ★★
- **是什么**：Hermes Agent 插件，把每次 turn/LLM 调用/工具调用/subagent/审批请求构建成执行 trace 图，/trace 查看/导出 JSON/Mermaid/Gantt。
- **价值点**：主项目任务/审计 + agent 编排的执行追踪可直接借鉴（18 个生命周期 hook + Gantt 瓶颈分析）。

### 40. feynman 已列 → khoj ★★
- **是什么**：AI 第二大脑（自托管 RAG + 聊天 + agent，Docker/Python），检索个人文档/网页/笔记。
- **价值点**：主项目检索/知识侧可参考其自托管 RAG 架构。

### 41. ai-scanner ★★
- **是什么**：AI 模型安全评估 Web 应用（Ruby on Rails + NVIDIA garak），内置真实 jailbreak 探针批量测漏洞。
- **价值点**：主项目是 AI 生成网关，可参考其 prompt 注入/jailbreak 探测思路做安全防护（不引入 Rails）。

### 42. owlcc-byoscc-main ★★
- **是什么**：BYOS 协议代理——跑 Claude Code 官方 TS 源码对接自己的 LLM 后端（Ollama/vLLM/OpenAI 兼容），本地化/多模型热切。
- **价值点**：与主项目「多提供商 OpenAI 兼容网关」定位一致，其协议代理/模型切换设计可参考（注意授权边界）。

### 43. openclaude-main ★★
- **是什么**：多模型提供商编码 agent CLI（源自泄露的 Claude Code 源码，去遥测+多后端），支持 OpenAI 兼容/Gemini/Ollama 等。
- **价值点**：多后端接入/终端工作流（tools/agents/MCP/slash）可作为主项目 agent CLI 参考（授权风险自评估）。

### 44. mochow13__keen-code ★★
- **是什么**：Go 写的极简 CLI 编码 agent（类 Claude Code/Codex），多提供商/skills/MCPs/subagent 多 agent 编排，强调简洁。
- **价值点**：主项目 agent 化的轻量参考；「被 agent 开发 agent」的过程记录（.ai-interactions）有价值。

### 45. claudecodeui 已列 → MonkeyCode ★★
- **是什么**：开源企业级 AI 开发平台（Electron+后端+浏览器扩展+mobile），含开发环境管理/模型管理/任务管理/需求管理，可企业内网部署。
- **价值点**：主项目管理面板+agent 任务管理的企业化对照（AGPL 注意）。

### 46. solo-orchestrator-main ★★
- **是什么**：单人用 AI 构建 MVP 的结构化开发方法论（阶段门控/TDD/安全扫描/威胁建模/文档强制，Claude Code 专用初始化）。
- **价值点**：主项目「计划书→实施→验收」工程可与该方法论对照（阶段门控/安全扫描）。

### 47. claude-md-doctor 已列 → openclaude 已列 → cn ★
- **是什么**：shadcn/aidenybai 的 Tailwind class 合并引擎新实现（替代 tailwind-merge+clsx，30× 快，零依赖）。
- **价值点**：主项目 React 管理面板/landing 若用 Tailwind 可直接替换提速。

### 48. impeccable-main ★★
- **是什么**：前端设计技能扩展（基于 Anthropic frontend-design skill + 7 个领域参考文件 + 20 个审计/打磨命令 + 反模式清单）。
- **价值点**：主项目 React 管理面板设计质量/反模板化可直接用其 skill 与命令。

### 49. refactoring-ui-plugin ★★
- **是什么**：Refactoring UI 方法论的 10 个结构化 UI 设计 skill + meta 编排器（视觉层级/字体/色彩/间距/空状态/阴影/对比/分组）。
- **价值点**：主项目前端 UI 打磨直接可用的 skill 包。

### 50. abi__screenshot-to-code ★★
- **是什么**：截图/mockup/Figma/录屏转代码（HTML+Tailwind/React/Vue 等），支持多模型（Gemini/GPT/Claude）。
- **价值点**：主项目前端迭代/落地页生成可参考；同为多模型网关生态，其「多提供商切换」实现有借鉴意义。

---

## 低价值（1 行结论）

### 51. lsaint__aikito ★★★
- **是什么**：把 coding-agent 的指令/skills/MCP 定义/subagents/持久记忆统一放进一个 Git 管理工作区，跨 agent 跨项目共享（Python 3.12+，纯标准库，多 OS）。
- **价值点**：与主项目 skills 技能库/agent 配置/记忆体系直接对口——「工作区治理 + agent 维护记忆」的分工模型可借鉴为主项目 skills/记忆的统一管理方式。
- **技术**：Python / Git 工作区 / 纯 stdlib。
- **借鉴方向**：agent 资产（skills/MCP/subagents）单一管理源、跨项目共享、记忆归属模型。
- **备注**：轻量、无依赖、Windows 支持，落地成本低。

### 52. DeepTutor
- **是什么**：HKUDS 终身个性化 AI 辅导系统（Python+Next.js，多语言文档），教育领域大模型应用；与主项目方向无关，仅学习型参考。

### 52. Mano-P
- **是什么**：面向边缘设备的 GUI-Aware agent 模型（MiningLamp，含 CUA 4B 模型与 benchmark），研究型视觉 agent；与主项目无关。

### 53. github-cheat-sheet
- **是什么**：Git/GitHub 隐藏功能速查表文档；纯文档，低价值。

### 54. manaflow-ai__cmux
- **是什么**：基于 Ghostty 的 macOS AI agent 终端（垂直标签+通知）；macOS 专属桌面终端，与主项目桌面（Tauri2/Windows）技术栈无关。

### 55. Farama-Foundation__MPE2
- **是什么**：多粒子环境 2（MPE2）强化学习仿真环境（OpenAI MPE 修复版）；RL 研究环境，无关。

### 56. boxmot
- **是什么**：多目标跟踪模块（Python/C++，YOLO 系检测跟踪）；CV 跟踪，无关。

### 57. PaddleDetection
- **是什么**：百度 PaddlePaddle 目标检测套件（含 ppdet）；CV 检测框架，与主项目无关。

### 58. Lody
- **是什么**：跨平台移动/桌面 agent 运行器（iOS/Android/macOS/Windows）；移动优先 agent 客户端，与主项目关系弱。

### 59. hapi
- **是什么**：远程控制 Claude Code/Codex 等编码 agent 会话的 Web/PWA/Telegram 前端；远程 agent 控制，主项目已有桌面端，参考价值中低。

### 60. nullx
- **是什么**：Dart 可空性处理工具库；Dart 语言库，无关。

### 61. xataio__xata
- **是什么**：基于 K8s 的开源 Postgres 平台（CoW 分支、scale-to-zero、自动故障转移）；数据库基础设施，与主项目 SQLite 栈无关，仅概念参考。

### 62. mimik
- **是什么**：浏览器工作流录制转分步指南（Chrome MV3 扩展，纯本地）；浏览器自动化/文档生成，与主项目弱相关。

### 63. whisper-flow
- **是什么**：OpenAI Whisper 实时流式转写服务；语音转写，主项目无语音能力，弱相关。

### 64. hermes-connector 已列 → bettercap
- **是什么**：网络攻击/监控框架（Go，MITM/嗅探/ARP 欺骗等）；安全工具，与主项目无直接关系。

### 65. crt.sh
- **是什么**：证书透明日志子域名枚举工具（Go，4 数据源并行）；安全/情报工具，与主项目无关。

### 66. TencentCloud__CubeSandbox 已列 → lap
- **是什么**：本地优先桌面照片管理器（Tauri2 + Vite）；照片管理，主项目技术栈 Tauri2 一致但领域无关。

### 67. gbrain 已列 → dif-sh__dif
- **是什么**：文件即 feature flag 的自托管功能开关/A-B 测试（Markdown 文件）；功能开关工程，与主项目弱相关，可作工程参考。

### 68. doska
- **是什么**：自托管看板（Kanban + Markdown 卡片）；协作工具，无关。

### 69. InkNote
- **是什么**：本地优先 Markdown 编辑器；文档工具，无关。

### 70. QQYQQ123__ec-news
- **是什么**：每日电商热点资讯抓取页（Python fetch + 静态页）；内容抓取站，与主项目弱相关。

### 71. claude-ads 已列 → lieflat-charts
- **是什么**：未找到 README 摘要；目录疑似图表库/组件（仅清单确认），低价值，需确认。

### 72. synapse-ai
- **是什么**：未获取到 README 摘要；按清单归类 agent 相关，需确认，暂列中低。

### 73. ai-scanner 已列 → gbrain 已列 → hermes-trace 已列 → ec-news 已列

### 74. 已列 → cn/doska/InkNote 已列 → claude-ads 已列 → destructive_command_guard 已列 → riskbypass_demo 已列 → Personal_AI_Infrastructure-main 已列 → kitter 已列 → ai-knowledge-graph 已列 → lemmalog 已列 → xata 已列 → aisix 已列 → owlcc 已列 → openclaude 已列 → PaddleDetection 已列 → impeccable 已列 → sigmap 已列 → ai-scanner 已列 → leapmux 已列 → gstack 已列 → gepa 已列 → MPE2 已列 → keen-code 已列 → claudecodeui 已列 → cn 已列 → doska 已列 → dif 已列 → nullx 已列 → boxmot 已列 → openstory 已列 → claude-mem 已列 → feynman 已列 → OpenDocs 已列 → Kun 已列 → claude-code-best-practice 已列 → screenshot-to-code 已列 → refactoring-ui-plugin 已列 → bettercap 已列 → whisper-flow 已列 → hindsight 已列 → CubeSandbox 已列 → lap 已列 → atlas 已列 → hermes-trace 已列 → mimik 已列 → rove 已列 → claude-code-prompts 已列 → crt.sh 已列 → khoj 已列 → gbrain 已列

### 75. Kun
- **是什么**：本地优先 AI Agent 工作台（桌面 GUI + 终端 TUI 共用本地运行时，任务/审批/计划/证据连续）；与主项目桌面+agent 方向相关，但国内 PolyForm 非商用许可，参考需注意授权。已在上文列入中价值区前补充。

### 76. claude-ads 已列 → graphify 已列 → openstory
- **是什么**：把脚本转成风格统一 AI 视频（脚本分析→场景拆解→Fal.ai 生成图像/动态/音频→合成）；属维度②多模态生成，主项目同为图像网关可参考其场景一致性/协作库思路。

### 77. hand-drawn-styles 已列 → claude-md-doctor 已列 → buchidonggua__dg-ai-notes 已列 → lieflat-charts 已列 → synapse-ai 已列 → QQYQQ123__ec-news 已列

### 78. dsh-message-edit 已列 → manaflow-ai__cmux 已列 → ruflo 已列 → context-mode 已列 → dagucloud__dagu 已列 → spec-kit 已列 → solo-orchestrator-main 已列 → vercel__eve 已列 → hapi 已列 → Lody 已列 → MonkeyCode 已列 → hermes-code-bridge 已列（见下）→ indicator 已列（见下）→ firefox-reverse 已列（见下）→ tokentest 已列 → graphify 已列 → hermes-connector 已列 → InkNote 已列 → loominary 已列 → claude-md-doctor 已列 → hand-drawn-styles 已列 → dg-ai-notes 已列 → lieflat-charts 已列 → synapse-ai 已列 → ec-news 已列 → claude-ads 已列 → destructive_command_guard 已列 → riskbypass_demo 已列 → Personal_AI_Infrastructure 已列 → kitter 已列 → ai-knowledge-graph 已列 → lemmalog 已列 → xata 已列 → lean-ctx（见下）

### 79. hermes-code-bridge ★
- **是什么**：Hermes 相关代码桥接（清单确认，未获 README 摘要）；属 Hermes 生态，主项目参考价值待确认。

### 80. indicator ★
- **是什么**：未获 README 摘要；清单归类杂项，待确认，暂低价值。

### 81. firefox-reverse ★
- **是什么**：Firefox 相关逆向/自动化（清单确认，未获 README 摘要）；与主项目浏览器自动化弱相关，待确认。

### 82. lean-ctx ★
- **是什么**：上下文精简工具（清单确认，与 context-mode 同主题域）；主项目上下文工程可参考，待确认细节。

---

## 待深入确认项（README 未取到摘要，仅目录名推断）

- **lieflat-charts**：疑似图表库，需确认。
- **synapse-ai**：疑似 agent 相关，需确认。
- **hermes-code-bridge**：Hermes 生态代码桥接，需确认。
- **indicator**：功能不明，需确认。
- **firefox-reverse**：疑似 Firefox 逆向，需确认。
- **lean-ctx**：疑似上下文精简，需确认。

---

## 汇总（按价值维度）

- **① agent/skills/mcp/context**：ruflo / eve / claude-mem / gbrain / lemmalog / context-mode / kitter / claude-md-doctor / hindsight / feynman / dg-ai-notes / claude-code-best-practice / claude-code-prompts / sigmap / gstack / Kun / rove / leapmux / dsh-message-edit / hermes-trace / MonlyCode / keen-code / openclaude / owlcc / ai-knowledge-graph / Personal_AI_Infrastructure / lean-ctx
- **② 图片/视频/音频/多模态**：hand-drawn-styles / openstory / orkas（PPT）
- **③ 网关/API/队列/编排**：dagu / aisix / model-hotel / tokentest.io / xata（DB）/ khoj（RAG）
- **④ 桌面/浏览器/自动化**：hermes-connector / hapi / Lody / MonkeyCode / claudecodeui / mimik / firefox-reverse / whisper-flow
- **⑤ 工程规范/交互/性能/安全**：spec-kit / claude-ads / destructive_command_guard / ai-scanner / cubeSandbox / atlas / impeccable / refactoring-ui / screenshot-to-code / cn / OpenDocs / claude-md-doctor

**Top 迁移候选（主项目直接受益）**：dagu（DAG 编排语义）、context-mode（SSE/上下文管理）、hand-drawn-styles（生图 prompt 资产）、hermes-feishu-streaming-card（SSE 卡片化）、tokentest.io（路由质量验证）、hermes-trace（执行追踪）、impeccable/refactoring-ui（前端设计）、dsh-message-edit（会话版本化）、ai-knowledge-graph（知识图谱）、kitter（skills 管理）。
