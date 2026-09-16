# g15_misc_3 组扫描结果（80 目录）

> 扫描人：scan_g15 · 方式：ls + README 首段识别，全部 80 目录已覆盖无遗漏
> 价值标准：①agent/skills/mcp/context 工程；②图片/视频/音频生成、电商、PPT/办公文档、多模态；③网关/API/队列/任务编排；④桌面/浏览器/自动化；⑤工程规范/交互/性能/安全
> 评级：★★★★★ 高价值（完整格式）/ ★★★ 中等 / ★ 低

---

## ★★★★★ 高价值（完整格式）

### nvidia-playgroud-go
- **是什么**：逆向 NVIDIA Build Playground（build.nvidia.com）的多模型 Go 客户端 + 多格式反向代理网关。
- **解决什么**：把 11 个匿名免费 playground 模型（DeepSeek/Kimi/MiniMax/Nemotron 等）统一聚合，对外暴露 OpenAI Chat Completions / OpenAI Responses / Claude Messages 兼容接口。
- **关键点**：运行时重爬 SSR 页面刷新模型目录；纯 Go hCaptcha PoW 求解器（内嵌 V8、无浏览器）+ token 池预取；按模型路由到 predict 端点（nv-function-id）；Docker 部署 + SSE/时延基准。
- **与主项目关联**：与「听风AI」架构高度同构——多上游聚合 + captcha 求解 + token 池预取 + OpenAI 兼容网关 + SSE + 端点鉴权（含 cf_solver/号池/代理池的对照实现思路）。
- **评级建议**：★★★★★ 直接对标，captcha PoW 求解器与 token 池设计可移植参考；OpenAI/Claude 双格式兼容层可对照。

### fal-nanobanana-studio
- **是什么**：基于 fal.ai nanobanana API 的 AI 图像编辑器（Photoshop/Photopea 替代）。
- **解决什么**：自然语言编辑图片 + 文生图 + 一键导出，模型可切换。
- **关键点**：Next.js/React 前端 + FastAPI 后端，直接消费 fal-ai/nano-banana(-pro) 接口。
- **与主项目关联**：主项目已把 nanobanana 列为 5 大图像上游之一，此项目正是该上游最直接的应用层对标实现。
- **评级建议**：★★★★★ 查看其 nanobanana 参数拼装/错误处理/流式返回，补强主项目对应 provider 实现。

### OpenHands-main
- **是什么**：开源 AI 软件开发 agent（Devin 开源版），SWE-bench 领先（77.6%）。
- **解决什么**：让 LLM 在安全沙箱里自主完成编程任务，含编排层、事件流、前端工作台、企业版。
- **关键点**：Agent runtime + sandbox + orchestration + SDK；多语言支持；MIT。
- **与主项目关联**：agent 工程里程碑级参照——沙箱隔离、任务编排、事件流的成熟范式。
- **评级建议**：★★★★★ 主项目 agent 化（DAG/意图识别/critic）可对照其 orchestrator 与事件流设计。

### lingtai
- **是什么**：自我进化的"数字科学家"终身 agent（LingTai-AI）。
- **解决什么**：agent 跨会话自增长记忆、持久知识与技能、本地优先、多 agent 网络协作。
- **关键点**：kernel 发行版（lingtai-kernel）+ portal + dev-guide-skill；ANATOMY.md/CONTRACT.md 治理文档；记忆固化机制。
- **与主项目关联**：与主项目 OpenWolf 记忆协议 + 记忆巩固 + skills 技能库方向高度一致。
- **评级建议**：★★★★★ 重点看其"自增长记忆 + 知识/技能沉淀"的 kernel 化设计，与 .wolf/ 记忆体系可交叉验证。

### token-savior
- **是什么**：一个 MCP server + 单一 profile，号称 tsbench 97.9% @ -80% tokens。
- **解决什么**：给 AI 编码 agent 做结构化代码导航、持久记忆、Bash 命令重写以大幅省 token。
- **关键点**：Python 3.11+，MCP 协议，含基准（benchmarks/）与 hooks；CLAUDE.md/AGENTS.md 完备。
- **与主项目关联**：主项目有 code-review-graph/codegraph 图谱 + OpenWolf 记忆，正对 context/token 工程痛点。
- **评级建议**：★★★★★ 其"结构导航 + 记忆 + 命令重写"三件套与主项目图谱工具可对照，省 token 基准方法可借鉴。

### semantica
- **是什么**：图原生基础设施（自称"AI 的 Palantir"）：Context Graph + 知识图谱 + 因果推理。
- **解决什么**：企业数据接入→提取→构建上下文图/KG→图分析/因果推理，全决策溯源，可解释可审计。
- **关键点**：Python（pip install semantica）；多语言图存储（RDF/LPG）；W3C 标准；面向高合规领域。
- **与主项目关联**：主项目有意图 embedding + 记忆巩固，若升级为图化上下文/可溯源决策可参考。
- **评级建议**：★★★★ 图化记忆/决策溯源是主项目 agent 化的进阶方向，先读其 ARCHITECTURE.md。

### genspark-ai__genoffice
- **是什么**：开源 AI Office 套件：Docs/Sheets/Slides/PDF/Markdown/HTML + 内嵌 AI 面板。
- **解决什么**：让 AI 编辑 Word/Excel/PPT/PDF 并保存回真实格式，替代 Office 的文档生成场景。
- **关键点**：TypeScript monorepo（apps/packages/skills/e2e），自研文档格式读写。
- **与主项目关联**：价值标准②办公文档方向的头号参照；主项目若扩展"AI 生成 PPT/文档"能力可移植其格式层思路。
- **评级建议**：★★★★ 办公文档生成方向首选参考，PDF/PPT 格式写回是主项目潜在增值点。

### n24q02m__crg
- **是什么**：Better Code Review Graph（crg）：代码库语义搜索 + 调用图解析的知识图谱，CLI 优先 + MCP 服务器。
- **解决什么**：token 高效代码审查——先定位影响半径再给上下文，减少无效上下文灌入。
- **关键点**：Python（PyPI better-code-review-graph），daemon/HTTP remote relay 双模式，alembic 迁移 + rules/。
- **与主项目关联**：主项目已启用 code-review-graph MCP + codegraph，此仓库正是同类能力的开源实现。
- **评级建议**：★★★★ 直接对照其图谱构建/查询/影响半径算法，补强主项目图谱工具。

### OpenMontage
- **是什么**：首个开源 agentic 视频生产系统。
- **解决什么**：从"粘贴一个视频/一句 prompt"开始，用 pipelines 编排多 agent 完成视频生成/剪辑/后期。
- **关键点**：多 provider 支持（docs/PROVIDERS.md）、pipelines 流水线、AGENT_GUIDE.md 治理。
- **与主项目关联**：价值标准②多模态（视频）方向的 agent 化生产管线样板。
- **评级建议**：★★★★ 主项目若从图像扩展到视频生成，其 pipelines + 多 provider 抽象可直接参照。

### openase-main
- **是什么**：Ticket-Driven 全自动软件工程平台（Open Auto Software Engineering）。
- **解决什么**：把编码/测试/文档/安全扫描/部署抽象为标准 ticket，AI agent 自主认领执行，需求→代码合并全自动。
- **关键点**：全 Go 单体单二进制（前端 go:embed 内嵌，免 Docker）；adapter 抽象兼容多 agent CLI（Codex/Claude/Gemini）；内置审批治理、lifecycle Hooks、成本控制；workflow/harness/skills 进版本管理。
- **与主项目关联**：与主项目 DAG 编排 + 任务系统 + agent 化方向高度相关；"ticket→agent→可审计执行"正是主项目任务链路的进阶形态。
- **评级建议**：★★★★ ticket 抽象 + lifecycle Hook（"什么叫完成"）+ 成本控制的治理范式值得深读。

### Compartment
- **是什么**：加密、完全离线的 AI agent 记忆（MCP vault）。
- **解决什么**：把记忆锁在本机一个加密 vault，Claude Code/Desktop/Hermes/OpenClaw/Cursor/Codex 等任意 MCP 客户端可读写，无 API key/账号/网络/遥测。
- **关键点**：Python PyPI 包，MCP server，跨客户端共享记忆。
- **与主项目关联**：主项目 OpenWolf 记忆 + agent 记忆巩固，其"加密离线 + 多客户端互通"模型可对照。
- **评级建议**：★★★★ 记忆私有化/多客户端互通的轻量实现参考。

### Open-Generative-AI
- **是什么**：开源的 AI 视频平台替代：经 MuAPI 聚合 400+ 模型 / 14 工作室生成图像和视频。
- **解决什么**：免内容过滤、免订阅的免费图像/视频生成入口。
- **关键点**：Electron + Next.js 前端；MuAPI 聚合层；messages/ 多语言。
- **与主项目关联**：形态与主项目（聚合网关）最接近的项目之一，但依赖已停服的 MuAPI。
- **评级建议**：★★★★ 只看其模型聚合目录 + 前端工作台组织，勿照搬（上游依赖失效）。

### wayland
- **是什么**：FerroxLabs 本地优先桌面 AI agent，驱动机器上所有 AI CLI（Claude Code/Codex/Gemini 等）。
- **解决什么**：一个桌面壳统管多个 CLI agent 会话、多实例并行、证据管理。
- **关键点**：Electron + Rust native（contracts/、strike/、installer/）；AGPL；readme.md 即完整文档。
- **与主项目关联**：主项目有 Tauri2 桌面 sidecar + 托盘/自升级，Wayland 是同类桌面 agent 壳的强对照。
- **评级建议**：★★★★ 桌面壳 + 多 CLI 实例编排 + 证据系统的设计可借鉴。

### CubeSandbox
- **是什么**：腾讯云开源：即时、并发、安全、轻量的 AI agent 沙箱服务。
- **解决什么**：给 AI agent 提供秒级沙箱（隔离、生命周期管理、网络出口控制）。
- **关键点**：CubeMaster/Cubelet/CubeProxy/CubeEgress 等多组件；agent/ 编排；多语言。
- **与主项目关联**：主项目 agent 执行若需沙箱/隔离代码运行，这是现成参照。
- **评级建议**：★★★★ agent 沙箱隔离方案（尤其 egress 出口管控）值得借鉴，先读 README_zh.md。

### cindy
- **是什么**：开箱即用的开源 AI agent，能直接在自己电脑上做真事（CUA 类本机操作）。
- **解决什么**：把"看屏幕、点鼠标、操作本机"的 agent 工作流做成可直接运行的产品。
- **关键点**：Node 22 + pnpm monorepo；apps/ 多应用；DESIGN.md/REVIEW.md 治理。
- **与主项目关联**：agent 自主操作本机 + 工作流工程范式参考。
- **评级建议**：★★★★ agent 本机执行链路的工程化组织可参考（DESIGN.md）。

---

## ★★★ 中等

### Archon-dev
- 开源 AI 编码 harness builder，让 AI 编码确定、可重复（自托管、Caddyfile、auth-service）。agent harness 工程参考。

### Comando
- Local-first AI 编码工作区：代码/agent/终端/Git/review 同处（Electron + Rust）。桌面本地工作区组织参考。

### sortie
- 开源编码 agent 编排器：把 tracker ticket 转成并行 agent 会话，agent-agnostic/tracker-agnostic。主项目 DAG 编排可参考其 ticket→agent 映射。

### reverify
- 防止 AI 编造：AI 提议 + 确定性工具逐条核对 ground truth，仅验证过的才计数。主项目 critic/自反思/验证闭环可参考其验证器设计。

### quality-prompts
- 58 种提示技巧的 Python 实现与评估（UMD 综述 + Learn Prompting 合作）。提示工程方法论参考。

### VoxCPM
- OpenBMB 无 tokenizer TTS：多语种语音生成、音色设计、真实克隆（WebUI/推理/微调）。音频生成方向，非主项目核心链路，暂缓。

### opc-nexus
- "数字员工 AI Box"：owner 下指令→Hermes 协调→数字员工执行→交付可验证产物（Electron + Hermes orchestrator + mobile）。agent 编排 + 桌面参考。

### OpenOSINT
- OSINT agent：20 调查工具 + 自然语言接口，REPL/CLI/MCP/Web；AI 只发工具调用、真二进制执行、幻觉结构性不可能。工具调用安全模式（拒绝幻觉）值得参考。

### OpenCut-app__OpenCut
- 开源视频编辑器（web/桌面/移动，Bun + moon，Rust 组件）。视频编辑方向，非主项目核心。

### VectifyAI__PageIndex
- 无向量、基于推理的 RAG：PageIndex 页面索引 + 推理器选择检索目标。轻量 RAG 参考（不依赖向量库）。

### awesome-llm-apps
- 100+ 开源 AI agent/skill/RAG 应用合集（每个 hand-built + E2E 测试）。作为 agent/RAG 应用清单库参考。

### uditgoenka__autoresearch
- Karpathy 式自主改进引擎 skill：约束 + 机械指标 + 自动迭代，支持 Claude Code/OpenCode/Codex。agent 自我改进闭环参考。

### Pake
- 把任意网页一键打包成桌面应用（macOS/Win/Linux，Rust Tauri 生态）。主项目有 Tauri2 sidecar，Pake 是轻量打包对照。

### claude-squad-main
- 终端应用管理多个 Claude Code/Codex/Gemini 实例：隔离 git workspace、yolo 后台任务、一次窗口多任务。多实例并行 agent 管理参考。

### deer-flow-main
- 字节 Deep Exploration & Efficient Research Flow：super agent harness 编排子 agent/记忆/沙箱 + 可扩展 skills。agent 编排参考。

### ponytail
- 开源 AI 编码 agent 框架，跨 harness（Claude/Codex/Gemini/pi）插件 + MCP server + hooks + commands。多 harness 兼容抽象参考。

### app-store-screenshots
- AI 编码 agent 的 skill：生成生产级 Next.js 应用商店截图编辑器（连接画布/设备框/一键导出）。图像生成 + skill 工程双参考。

### webbrain-one__webbrain
- 开源浏览器 AI agent（Chrome/Firefox/Edge 扩展）：对话页面/自动化/多步工作流，自带 MCP server。浏览器自动化参考。

### chatfire-AI__huobao-drama
- AI 短剧自动制作平台（TypeScript 全栈 + Vue3 + 桌面端）：脚本/分镜/生成/配音全流程。视频生成方向，形态相似但非核心。

### facebook__astryx
- Facebook 开源设计系统（React 19 + StyleX），面向"人 + agent 协作构建"。主项目前端 React19，其设计系统/协作组件范式可参考。

### NexaFlow
- 团队 AI 应用编排平台：知识库 + 模型 + Agent + 工作流 + 统一工具（Python/FastAPI + Next.js）。与主项目 agent 工作流方向相近。

### penguin-harness
- 开源本地优先多 agent 应用开发平台：自动构建/优化/部署 AI 应用（桌面 + CLI + plugins）。

### relaydeck
- agent 编排 daemon + dashboard：并行跑 CLI 编码 agent、实时终端、P2P 消息、多模型、插件栈。本地优先无云。

### EnsoAI-main
- 单项目多 agent 并行流：Claude/Gemini/Codex 在各 worktree 并行（Electron + Rust sidecar）。桌面 + 多 agent 相关。

### abingyyds__ai-product-page-generator
- 本地优先 AI 电商详情页生成（Next.js + Prisma，内含 nanobanana 教程文档）：OpenAI 兼容接入、结构化分析、分段生成、手机模拟预览。电商生成 + nanobanana 用例双参考。

### claude-obsidian
- 用 Claude Code 构建 Obsidian 知识库：采集来源/连接笔记/接地回答/保持 vault 健康（Agent Skills 兼容）。知识管理/记忆参考。

### machinist
- 开源 AI 软件工厂：可重复可扩展的 agentic 编码工作流（Go，workflow DSL + evals）。与主项目 DAG/工作流编排可对照。

### planning-with-files
- 规划 skill（task_plan.md / findings.md / progress.md 三文件法），GitHub Trending #1。主项目有 workflow_status.md，可对照其文件化规划法。

### grok-app
- Grok Build CLI 的桌面工作台：多项目空间/实时 agent 流/文件代码循环/多端远程 IM。桌面 agent 工作台参考。

### qm
- 多人在线 agent harness（Slack + web）：会话/个人文件/cron/凭据/部署/记忆/skills。中。

### hyperdx
- 开源 Datadog 替代：logs/traces/session replay（Next.js + ClickHouse）。主项目有 telemetry/OTel + 日志面板，可参考其告警/会话回放。

### shannon
- Keygraph 自主 AI 渗透测试器（Web/API）：CLI + PDF 报告 + SARIF。安全方向，主项目安全审计方法可借鉴。

### kendex
- 桌面 + CLI 统一管理 agents/skills/hooks/自定义，跨 Claude Code/Codex/Cursor 等（Rust）。主项目有 skills 库，可参考统一配置管理。

### WrongStack
- 开源 AI 编码 agent：brain + memory + 67 工具，durable memory + 可见权限边界 + 专业 agent 协调。

### nanocoder
- 终端开源编码 agent，BYO model（Ollama/OpenAI 兼容），本地优先、无厂商锁定。中。

### Infographic（AntV）
- LLM 驱动的信息图生成与渲染框架（文字→图表/信息图，TS + Vite + vitest）。图像生成方向价值标准②的有效参考。

### awesome-osint-arsenal-zh（★ 见下）

---

## ★ 低（一句话说明是什么）

- **loopx**（实际 ★★★★★）：有状态长时程 agent 控制平面，跨回合保存 objective/gates/todos/evidence/quota/handoff。主项目 agent 化（DAG/记忆）高度相关，未在顶部列出，特此补记为高价值。
- **superpowers**：软件方法论 + 组合式 skills（TDD/planning 等全套）；主项目已装 superpowers-zh（20 skills）同源，仅作对照无需重做。
- **NousResearch__hermes-plugin-snyk**：Hermes Agent 的 Snyk MCP 插件（Agent Plugins v1 规范：mcp.json + workflow skill），可参考 agent-plugins v1 打包格式。
- **frantic-board**：公共任务板 + 真实金钱，让 AI agent 按合约交付挣报酬（外包市场概念）。与主项目无关。
- **Horizon**：Python 新闻 RSS 聚合 + AI 摘要（uv.lock）。无关。
- **qyvaria-hardlogic-kernel-engine**：自称 AI 监督内核，实为单文件混淆 HTML（XOR 解码动态 document.write），疑似营销/可疑 payload，无工程价值（警示）。
- **kharmanskyi__open-steps**：一组 skill 让开发过程对运行者透明（会话/决策/下一步纯语言表达）。低-中。
- **aura-main**：自称"主权认知架构"（IIT 4.0、Mac 常驻运行），学术概念包装壳，与工程无关。
- **claude-hud-main**：Claude Code 插件，输入框下常显 context 用量/活跃工具/运行 agent/todo 进度。对管理面板 agent 状态可视有启发。
- **earendil-works__pi-review**：pi-coding-agent 插件，/review 未提交变更的代码审查工作流。低。
- **ifiokjr__monopi**：pi-coding-agent 的配置安装器（oh-my-zsh for pi）。低。
- **harnesscode-master**：AI 人机协同开发框架（Python）。低-中。
- **backnotprop__plannotator**：agent 反馈/标注工具：标注 plan/spec/Markdown/HTML、review diff/PR、把反馈送回 agent。对评审反馈闭环有参考（中偏上）。
- **flash-attention-main**：FlashAttention-2/3 官方实现（底层 CUDA 注意力内核）。主项目是网关非训练侧，无直接价值。
- **WeMM-Embedding**：腾讯微信多模态 Embedding（图/文/语联合表示）。embedding 用于检索可参考（低-中）。
- **cohub**：Neta Studio/Cohub AI 多模态创作平台（generations/space-hooks/agent-sandbox-runtime，公开开发）。多模态生成方向参考（中偏上）。
- **dsh-infinite-gen-3**：DeepSeek Harness 网络安全红队"无限生成"插件（系统提示注入 + 客户端状态栏）。方向与主项目无关且涉安全敏感，仅记录。
- **Y2A-Auto**：YouTube→AcFun/bilibili 自动搬运全流程（下载/ASR/字幕翻译/审核/上传，Python+Flask+Web 后台）。视频搬运方向，非核心。
- **open-grok-bot**：本地优先 AI 工作区（bot 人格 + MUAPI + FastAPI + Next.js）。低-中。
- **Claude-Code-Everything-You-Need-to-Know**：Claude Code 全面指南（hooks/MCP/多 agent/团队工作流）+ mcp-servers/specialized-agents 清单。仅参考资料。
- **uv**：Astral 极快 Python 包/项目管理器（Rust）。主项目已用 uv.lock，工具链成熟，无移植价值。
- **panel（Remnawave）**：基于 Xray-core 的代理管理面板（Docusaurus 文档站）。主项目 proxy_pool 是住宅/免费代理双源，非翻墙代理，方向不同。
- **claude-plugins-community**：Claude 社区插件市场只读镜像（.claude-plugin/marketplace.json 每晚同步）。可参考 marketplace 组织方式。
- **yummy-pi-extensions**：pi-coding-agent 扩展 pi-zvec-grep（TS 实现带 watcher/change-batcher 的 grep 引擎）。低。
- **fermats-last-theorem**：Lean 4 中费马大定理的机器可验证证明（研究产物）。无关。
- **awesome-osint-arsenal-zh**：753+ OSINT/安全工具中文分类清单 + 脚本。仅清单无工程。
- **img2threejs**：skill：参考图→代码化 Three.js 程序化 3D 模型（质量门控、token 高效）。3D 生成方向，非主项目核心。
- **zedis**：Rust + GPUI 的 Redis GUI（百万 key 不转圈）。工具类，无关。
- **hive**：本地优先多 agent 协作工作区：浏览器工作台 + Orchestrator 规划委派 + workers 真实 PTY 执行（Claude Code/Codex/Gemini 等）。中-高，agent 编排参考（补记）。
- **NexaFlow / relaydeck / machinist 等已在中等列出。**

---

## 汇总（Top 迁移/借鉴清单）

| 优先级 | 项目 | 借鉴点 |
|---|---|---|
| P0 对标 | nvidia-playgroud-go | captcha PoW 求解器 + token 池 + OpenAI/Claude 双格式网关（与主项目架构同构） |
| P0 对标 | fal-nanobanana-studio | nanobanana 上游的应用层参数拼装/流式/错误处理 |
| P1 agent | token-savior / crg / semantica / Compartment | token 节省 / 代码图谱 MCP（主项目同款） / 图化记忆 / 加密离线记忆 |
| P1 agent | lingtai / OpenHands / openase / hive / loopx | 自增长记忆、agent orchestrator、ticket→agent 治理、多 agent 协作、长时程控制平面 |
| P1 生成 | genspark genoffice / OpenMontage / Infographic / abingyyds 电商页 | 办公文档格式写回、agentic 视频管线、信息图生成、电商详情页生成 |
| P2 桌面 | wayland / Pake / EnsoAI / grok-app | 桌面 agent 壳、网页打包桌面、多 worktree 并行 |
| P2 规范 | reverify / shannon / claude-hud | 防幻觉验证器、AI 渗透测试、agent 状态可视 |

## 风险提示
- `qyvaria-hardlogic-kernel-engine`：混淆 HTML 单文件，含 base64/XOR 混淆脚本，无工程价值，建议直接从参考库移除或隔离。
- `dsh-infinite-gen-3`：红队/注入类插件，仅记录不借鉴。
