# g19_misc_7 组扫描结果（80 目录）

扫描范围：`D:/参考项目/` 下 misc 杂项组 80 个目录。价值分级：**高**（直接对标主项目核心能力，优先细读）/ **中**（可借鉴特定模块）/ **低**（一句话说明）。

---

## 高价值项目（建议细读源码）

### 1. headroomlabs-ai__headroom
- **是什么**：AI agent 的上下文压缩层（context compression layer），Rust 核心 + Python/npm 发布，含自研 ML 模型（kompress-v2-base，HuggingFace）。
- **解决什么问题**：把 agent 的长提示词/上下文压缩（示例 55,957 token → 24,340 token，关键行保留），降低 token 成本、减少噪音、突破上下文窗口。
- **对主项目价值**：**高**。主项目 agent 化有"记忆巩固/上下文管理"，headroom 的压缩算法（结构化 token 裁剪、关键指令保留、可量化压缩比）可直接借鉴到意图识别前的 context 精简，降低每次请求成本。
- **可借鉴点**：压缩保留策略（关键行字节级保留）、压缩比评估 benchmark 体系、Rust 高性能路径。
- **风险/注意**：压缩会丢失信息，需结合主项目 SSE 事件流做保真度评估；模型推理本身有成本。

### 2. tingly-box
- **是什么**：Go 写的 Agent-First 模型网关（agent gateway）：统一端点桥接任意 provider、一键配置 Claude Code/OpenCode/Codex 等 agent、优化上下文、路由请求、内置远程控制与安全集成。
- **解决什么问题**：多 provider 接入 + agent 请求路由 + 上下文优化 + 远程控制，与主项目"聚合上游 + OpenAI 风格接口 + MAB 路由"是同一问题的另一实现。
- **对主项目价值**：**高**。主项目网关核心（5 家图像上游 + 路由引擎）可直接对标 tingly-box 的 provider 桥接设计、agent 接入配置、上下文优化策略。
- **可借鉴点**：provider 统一端点协议、agent 一键接入配置、远程控制 API。
- **风险/注意**：Go 技术栈，仅借鉴架构与协议设计，不引代码。

### 3. mission-control
- **是什么**：自托管 AI agent 控制平面（Builderz Labs）：调度任务、检查运行、审查失败、跟踪费用、协调多个 agent 运行时（OpenClaw/Claude Code/Codex），前端 dashboard + SQLite 后端。
- **解决什么问题**：把分散在各 agent 的任务/运行/失败/费用统一到一个本地控制台。
- **对主项目价值**：**高**。主项目有管理面板 + 任务/审计 SQLite + DLQ/慢任务页，mission-control 的"任务流水线 + 失败审查 + 费用跟踪 + SQLite 本地仪表盘"几乎同构，可对照补齐主项目缺的"agent 运行时协调"视角。
- **可借鉴点**：任务流水线状态机、SQLite 面板数据模型、多运行时适配层。
- **风险/注意**：需确认其 SQLite 并发模型与主项目 aiosqlite 差异。

### 4. bernstein
- **是什么**：开源 AI agent 治理层（governance layer，Python 3.12+）：为 agent 提供策略/审批/审计的中间层，PyPI + Docker 发布。
- **解决什么问题**：agent 自主行动的治理——什么能做什么不能做、审批流、审计留痕。
- **对主项目价值**：**高**。主项目 v15 已做"工具调用安全护栏"、鉴权、审批持久化，bernstein 可作为治理层的完整参考实现（策略定义、审批、审计）。
- **可借鉴点**：治理策略 DSL、审批工作流、审计追踪。
- **风险/注意**：需对比主项目现有 Fence/护栏避免重复建设。

### 5. FailproofAI__failproofai
- **是什么**：agent 可观测性与执行防护层：hook 12 个 agent harness（Claude Code/Codex/Hermes/OpenClaw 等），捕获每次运行、在执行前阻止危险工具调用，39 条内置策略，零延迟本地运行。
- **解决什么问题**：跨 harness 统一的可观测 + 工具调用安全拦截。
- **对主项目价值**：**高**。与主项目 v15.1"工具调用安全护栏"直接对标，其 39 条策略库、多 harness hook 机制、零延迟设计可作升级参考。
- **可借鉴点**：危险工具调用模式库、hook 注入点设计、本地策略引擎。
- **风险/注意**：Next.js + Rust（crates/）混合架构，借鉴策略定义而非整体迁移。

### 6. memanto
- **是什么**：Memory Agent——管理其他 agent 记忆的"记忆管家"：决定保留什么、冲突处理、过期回收、谁需要知道，Python 实现（arXiv 论文背书）。
- **解决什么问题**：多 agent/长会话下记忆的取舍、冲突、过期与传播，让记忆是"被管理的数据"而非"堆叠的文本"。
- **对主项目价值**：**高**。主项目 agent 化含记忆巩固（OpenWolf），memanto 的"记忆 Agent"角色划分、冲突解决、过期策略可补强主项目记忆层。
- **可借鉴点**：记忆生命周期管理（保留/冲突/过期/广播）、Memory Agent 架构。
- **风险/注意**：重 agent 编排，轻量场景可能过度设计。

### 7. gbrain-master
- **是什么**：个人知识库"大脑"：会议/邮件/日历/通话/想法全部流入可搜索知识库，agent 每次响应前读、每次对话后写，PGLite（无服务器，2 秒建库）。
- **解决什么问题**：给 agent 持久化的个人生活/工作记忆底座。
- **对主项目价值**：**高**。主项目有"记忆巩固"模块，gbrain 的"响应前读取 + 对话后写入 + PGLite 无服务器 + 集成全家桶"是成熟的记忆持久化模式。
- **可借鉴点**：PGLite 免服务器记忆存储、导入/embedding/集成的 30 分钟装配流程、schema 设计。
- **风险/注意**：依赖前沿模型（Claude Opus/GPT-5.4），小模型会崩，参考时注意门槛。

### 8. claude-context / claude-context-master（zilliztech，同源）
- **是什么**：MCP 插件，给 Claude Code 等 coding agent 加语义代码搜索（语义向量索引整个代码库，搜索结果直接进上下文）。
- **解决什么问题**：代码库上下文获取——从"多轮文件发现"变成"语义检索直达"，解决上下文窗口限制与 RAG 检索。
- **对主项目价值**：**高**。主项目已有 codegraph 图谱做代码检索，claude-context 提供的是"语义搜索 + MCP 注入上下文"的完整实现，其 VS Code 插件/npm 包/向量化策略可对照。
- **可借鉴点**：语义索引管线、MCP 工具暴露、上下文注入格式。
- **风险/注意**：与 codegraph 功能重叠，作为替代方案对比而非引入。

### 9. Claude-Code-Source-Study
- **是什么**：Claude Code 源码深度分析教程（34 章、逐文件逐函数拆解、精确到行号）：系统提示词工程、多 Agent 编排、工具系统、权限安全、Bridge IPC、远程会话、终端 UI、记忆/扩展。
- **解决什么问题**：从 Anthropic 生产级 AI 产品源码中学习 agent 全栈工程范式。
- **对主项目价值**：**高**。主项目 agent 化（意图识别/DAG 编排/critic/记忆）的知识点全覆盖，是直接可读的学习地图。
- **可借鉴点**：权限安全模型、工具系统设计、IPC 协议、多 agent 协调。
- **风险/注意**：教程性质，需按主项目实际架构落地。

### 10. ECC（Everything Claude Code）
- **是什么**：agent harness 操作系统（hooks/commands/agents/config 全插件体系），v2.2.1。
- **解决什么问题**：把 Claude Code 扩展成可编程的 agent 工作台。
- **对主项目价值**：**高**。**本项目已在使用 ECC 插件系统**（skills/hooks/commands），其 hooks 架构、agent 定义、配置体系是主项目开发环境的运行底座。
- **可借鉴点**：已在用；其 hooks 设计可反哺主项目前端/desktop 的自动化。
- **风险/注意**：外部依赖版本升级需回归验证。

---

## 中价值项目（可借鉴特定模块）

### 11. icarus-plugin
- **是什么**：Hermes Agent 插件：agent 共享记忆（markdown 文件）、训练数据提取、模型替换流水线（"remember your work, train your replacement"），Obsidian 仅作可选查看器。
- **对主项目价值**：**中高**。主项目记忆巩固可借鉴其"训练数据提取 + 模型替换"进阶玩法；共享记忆格式可参考。
- **可借鉴点**：共享记忆文件格式、训练数据抽取管线。

### 12. goose / goose-main（Block 开源，两个副本）
- **是什么**：开源本地 AI agent（桌面 app + CLI + API），Rust 核心，面向代码与工作流。
- **解决什么问题**：本地优先的通用 agent 运行时。
- **对主项目价值**：**中高**。主项目 agent 化可参考其桌面/CLI/API 三端架构与扩展（recipes）机制。
- **可借鉴点**：三端一体化 agent 结构、recipe 扩展模型。goose-main 为旧版副本，看 goose 即可。

### 13. deepseek-harness
- **是什么**：DeepSeek 官方开源 agent harness（`dsh`），everything-is-a-plugin 架构，基于 Cordis（时空可组合编程范式），Python/多语言。
- **解决什么问题**：插件化、可组合的 agent harness 底座。
- **对主项目价值**：**中高**。主项目 agent 化（MCP 服务端、skills 库）的插件化架构可借鉴 Cordis 的组合范式。
- **可借鉴点**：everything-is-a-plugin 注册/生命周期、Cordis 组合模型。

### 14. open-swe
- **是什么**：LangChain 开源"软件工厂"，基于 Deep Agents + LangGraph：给定需求自动完成软件工程任务闭环。
- **解决什么问题**：用 LangGraph 图编排把 agent 串成可复现的软件生产流水线。
- **对主项目价值**：**中高**。主项目有 DAG 编排/意图识别，open-swe 的 LangGraph 图编排、Deep Agents 递归 agent 模式可参考。
- **可借鉴点**：DAG 节点设计、agent 自省/递归改进、evals 体系。

### 15. openscience
- **是什么**：开源科学研究 AI 工作台：给目标→读文献→假设→写代码→跑实验→查询科学数据库→写报告，浏览器工作区，模型无关。
- **解决什么问题**：把"科研闭环"agent 化。
- **对主项目价值**：**中高**。主项目 agent 化（DAG 续跑、critic 自反思）与其"研究循环"编排同构，前端工作区交互可参考。
- **可借鉴点**：长流程 agent 编排、工作区 UI、evals。

### 16. alphaXiv__OpenResearch
- **是什么**：本地优先的研究 agent 工作台（Rust CLI + 各平台安装包），把 Claude Code/Codex/OpenCode/Cursor 变成能读文献、做假设、跑实验、产研究产物的 agent。
- **对主项目价值**：**中高**。与 openscience 同类，Rust 轻量 CLI 形态 + 多 agent 驱动模式可参考主项目 desktop sidecar 设计。
- **可借鉴点**：多编码 agent 统一驱动层、本地优先存储。

### 17. hyperresearch
- **是什么**：深度研究 harness：16 步 tier-adaptive 流水线，单提示词产出带来源溯源的对抗审计报告；每个来源进持久化、可搜索的 vault，会话递进积累。
- **对主项目价值**：**中高**。主项目 DAG 编排 + 记忆巩固可借鉴其"16 步流水线 + 来源 vault"的组合。
- **可借鉴点**：多步研究流水线、来源溯源审计、持久化 vault。

### 18. nuphus
- **是什么**：本地优先 AI Agent 桌面端（Tauri v2 + Rust + React 18）：识别屏幕、操作鼠标键盘、控制窗口、读写文件、调度浏览器，手机作第二块屏幕实时同步。
- **解决什么问题**：给 LLM 真实桌面执行力，隐私本地化。
- **对主项目价值**：**高（Tauri 桌面路径）**。主项目已有 Tauri2 sidecar，nuphus 的"桌面控制 + 跨设备同步"能力可作 v16+ 桌面增强的路线图参考。
- **可借鉴点**：Tauri/Rust 桌面 agent 集成、屏幕识别/键鼠控制、跨设备会话同步。
- **风险/注意**：Alpha 阶段，功能稳定性需自行评估。

### 19. monocode
- **是什么**：coding agent 桌面 UI（Tauri），聚合 Claude Code/Codex/Cursor/Grok/OpenCode/Pi 等订阅，tab 即会话。
- **对主项目价值**：**中**。主项目 Tauri 桌面可参考其多 agent 会话聚合 UI。
- **可借鉴点**：多 provider 会话管理、composer 交互。

### 20. Porabuild__Poracode
- **是什么**：跨平台 app（Android/iOS/Web/Chrome 扩展/Capacitor）：一个窗口并排运行 14 种 AI coding agent，内置 MCP 让 agent 相互编排。
- **对主项目价值**：**中**。移动端 + MCP 互编排形态可参考。
- **可借鉴点**：多 agent 并列编排、MCP 互调。

### 21. moon-code
- **是什么**：Kimi Code CLI 的桌面 GUI（Electron）：项目文件树 + Diff、内置开发浏览器（框选批注回传 agent）、子 Agent 绑定任意 OpenAI 兼容第三方模型降本、用量 50/80/95% 阈值可视化、断线自动恢复。
- **解决什么问题**：CLI agent 的可视化工作台 + 降本 + 稳定性。
- **对主项目价值**：**中高**。主项目桌面/Tauri 可借鉴"子 Agent 跑第三方便宜模型""断线恢复""用量阈值通知"三个能力，均与主项目预算门禁/成本页直接相关。
- **可借鉴点**：子 agent 模型路由降本、断线续传、套餐用量可视化。

### 22. Minke / See-Sol-Lab__DeepSeekGUI（同类）
- **是什么**：均为 DeepSeek Harness 的桌面工作区（Minke: Electron/lencx；DeepSeekGUI: 本地工作台，Windows/Linux）。
- **对主项目价值**：**中**。本地 LLM 工作台形态可参考，但主项目是聚合网关非本地推理，价值有限。
- **可借鉴点**：desktop 配置面板、本地模型会话管理。

### 23. mco
- **是什么**：Python CLI 编排层：把同一任务并行发给多个 coding agent/模型，对比原始答案后再行动（审查/实现/架构/CI 检查）。
- **对主项目价值**：**中**。主项目路由引擎的多节点对比可借鉴其"多模型并行 + 结果对比"交互。
- **可借鉴点**：多 agent 并行结果聚合、对比报告生成。

### 24. crewAI-main
- **是什么**：Python 多 agent 编排框架（角色/任务/流程/工具，最流行的 crew 框架之一）。
- **对主项目价值**：**中**。主项目已自研 DAG 编排，crewAI 的角色-任务模型可作对照/启发（不建议引入重依赖）。
- **可借鉴点**：crew 角色分工、任务依赖声明、流程编排。

### 25. loop-engineering
- **是什么**：agent 循环工程框架："Stop prompting. Design the loop. Get a score."——把 agent 设计成带循环/反馈/评分的系统，含 skills/patterns/gate.yaml。
- **对主项目价值**：**中**。主项目 critic 自反思/自测可借鉴其"循环 + 评分 + 门禁"的闭环设计。
- **可借鉴点**：loop 设计模式、gate 门禁配置。

### 26. autoresearch
- **是什么**：把 Claude Code/OpenCode/Codex 变成自主改进引擎（Karpathy autoresearch 实现，skill 形式）：约束 + 机械指标 + 自主迭代。
- **对主项目价值**：**中**。主项目"自反思/持续改进"可借鉴其 metric 驱动迭代 loop。
- **可借鉴点**：metric 定义、自主迭代循环。

### 27. oh-my-hermes
- **是什么**：Hermes agent 的"oh-my-zsh"式技能工作流层：36 skills、7 agents，可自主运行于 VPS/笔记本。
- **对主项目价值**：**中**。skills 库组织方式（curated + 自主运行）可参考主项目 skills 技能库整理。
- **可借鉴点**：skills 分类与封装、agent 工作流模板。

### 28. headcount
- **是什么**：Claude Code 技能/部门库："加一个部门，而不是加一条提示词"——16 部门、172 skills，可搜索 org-chart。
- **对主项目价值**：**中**。主项目 skills 库的组织/检索可参考其部门化分类。
- **可借鉴点**：skills 元数据组织、org-chart 检索 UI。

### 29. chops
- **是什么**：macOS 应用：在 Claude Code/Cursor/Codex/Windsurf/Copilot/Aider 等之间统一发现、组织、编辑 skills 与 agents（内置 monospaced 编辑器，frontmatter 解析）。
- **对主项目价值**：**中**。多工具 skills 互操作与 frontmatter 编辑体验可参考。
- **可借鉴点**：多工具 skills 发现/同步、frontmatter 编辑器。

### 30. kandev
- **是什么**：并行任务管理与 agent 编排工具：自定义 workflows/agent profiles/runtimes/prompts/review gates，支持移动端远程访问、服务化运行。
- **对主项目价值**：**中**。主项目任务系统可借鉴其 review gates 与远程访问。
- **可借鉴点**：review gate 流程、任务并行调度、移动远程访问。

### 31. vicoa
- **是什么**：跨平台 agent 平台（桌面 + CLI + 移动 iOS/Android，可自托管），多语言。
- **对主项目价值**：**中**。跨端 agent 产品形态可参考。
- **可借鉴点**：跨端同步架构、自托管配置。

### 32. wigolo
- **是什么**：本地优先的 web 智能 MCP server：无 key、无云、无计费的网页搜索/浏览，适配 Claude Code/Cursor/CrewAI/LangChain/n8n 等任意 MCP 客户端。
- **对主项目价值**：**中**。主项目 MCP 服务端可借鉴"本地优先无 key 工具"设计（与付费 API 红线契合）。
- **可借鉴点**：MCP server 封装、无 key 搜索实现、多客户端适配。

### 33. crawl4ai
- **是什么**：LLM 友好的开源网页爬虫/抓取器（Python，Playwright 驱动），输出 LLM 结构化格式，支持渐进式爬取。
- **对主项目价值**：**中**。agent 化数据采集/研究可用；主项目如做网页类任务可引入。
- **可借鉴点**：LLM 结构化输出、反爬/动态页处理。
- **风险/注意**：重依赖（Playwright），按需引入。

### 34. seedance-2.0
- **是什么**：Seedance 2.0 视频生成的 agent skill：规划镜头、绑定参考图、从已接受片段续作，生成"导演级"视频 prompt，provider 负责生成。
- **对主项目价值**：**中**。主项目是图像生成网关，视频生成是天然下游扩展方向；其 skill 化 prompt 编排可参考。
- **可借鉴点**：视频 prompt 编排 skill、参考绑定/续作工作流。

### 35. shuyu-labs__BigBanana-AI-Director
- **是什么**：AI 一站式短剧/漫剧生成平台：Script-to-Asset-to-Keyframe 工业化工作流，一句话生成完整短剧，控制角色一致性/场景连续性/镜头运动（深度集成 AntSK API）。
- **对主项目价值**：**中高**。主项目图像网关的下游视频/短剧应用场景样板，其"脚本→资产→关键帧"流水线编排值得参考。
- **可借鉴点**：角色一致性控制、多镜头工作流、生产流水线编排。
- **风险/注意**：依赖 AntSK 私有 API；授权 CC BY-NC-SA 4.0，商用注意协议。

### 36. PreenCut
- **是什么**：AI 视频剪辑工具（Python + Whisper + LLM + Gradio）：语音转写→LLM 分段摘要→自然语言查片段→智能裁剪/SRT 导出/批处理。
- **对主项目价值**：**中**。Whisper 集成 + 自然语言媒体检索范式可参考（与 OpenSuperWhisper 的 Whisper 用法互补）。
- **可借鉴点**：Whisper 转写管线、自然语言视频检索、SRT 导出。

### 37. OpenSuperWhisper
- **是什么**：macOS 实时语音转文字（Whisper.cpp + Parakeet 双引擎）：全局快捷键/鼠标触发、按住录音、拖放文件队列、多语言自动检测。
- **对主项目价值**：**中**。语音输入可作主项目 ChatPlayground/desktop 的输入增强，Whisper 本地集成模式可参考。
- **可借鉴点**：实时转写架构、全局快捷键触发、双引擎切换。

### 38. ziguishian__MxPage
- **是什么**：AI 原生电商图文工作台：电商详情页、小红书图文、批量商品页面生成，支持本地私有化部署（Next.js + Prisma）。
- **对主项目价值**：**中**。主项目图像网关的电商下游应用样板，批量生成 + 私有化部署与主项目定位契合。
- **可借鉴点**：批量图文生成流水线、电商模板渲染。

### 39. sie（Superlinked Inference Engine）
- **是什么**：自托管推理引擎：把 agent 调用的所有开放模型放在自建集群统一服务（Rust 核心 + Python 工具链）。
- **对主项目价值**：**中**。主项目聚合的是外部上游，sie 是自托管推理聚合，架构对标可参考其集群统一服务设计。
- **可借鉴点**：多模型统一服务、推理路由。

### 40. Claudable
- **是什么**：把 CLI agent（Claude Code 等）连接成可远程控制的 web 应用：Next.js + Electron + Stripe 计费，可视化构建并即时部署。
- **对主项目价值**：**中**。主项目前端管理面板可借鉴其"CLI agent 远程控制 + 可视化构建"交互。
- **可借鉴点**：agent 远程会话管理、web terminal。

### 41. texera
- **是什么**：Apache 大数据工作流系统（Scala/Akka + 前端拖拽）：工作流编译、执行、数据科学可视化，含 agent-service、notebook 迁移等微服务。
- **对主项目价值**：**中**。主项目 DAG 编排可参考其工作流编译/执行微服务切分。
- **可借鉴点**：工作流编译器、执行引擎、微服务拆分。
- **风险/注意**：JVM 重型栈，仅架构借鉴。

### 42. FankChen__tracecrate
- **是什么**：隐私优先、纯客户端的 AI trace 工作台：把 agent 运行 trace 文件变成可搜索时间线、指标、启发式诊断、并排对比；无后端/遥测/账号。
- **对主项目价值**：**中**。主项目有任务审计/日志/SSE 事件流，tracecrate 的 trace 文件格式 + 诊断视图可参考做 agent 运行复盘。
- **可借鉴点**：trace 时间线可视化、启发式诊断、无后端分析。

### 43. EmpiricaAI__empirica
- **是什么**：AI 认知基础设施（Python + MCP）：测量 AI 所知、门禁其所为、跨会话累积学习；衡量"预测 vs 真实"差距。
- **对主项目价值**：**中**。主项目记忆巩固/预算门禁可借鉴其"认知测量 + 行动门禁"框架。
- **可借鉴点**：跨会话测量、校准、门禁策略。

### 44. mirrord
- **是什么**：把本地进程放进实时 K8s 集群运行：本地跑代码，但流量/文件/环境变量经目标 pod 路由，适合 agent 写代码时读取真实集群上下文。
- **对主项目价值**：**低中**。与主项目核心无关，但"agent 读真实环境上下文"理念可用于主项目 agent 化调试。
- **可借鉴点**：本地/远端上下文桥接。

### 45. web-check
- **是什么**：网站综合分析工具（API + Svelte 前端）：安全头、SSL、DNS、技术栈、CSP 等一键检测。
- **对主项目价值**：**低中**。主项目有 Security 页，web-check 的检测项清单可作为安全审计功能参考。
- **可借鉴点**：安全检测项集合、报告展示。

### 46. hi77x__appgraph
- **是什么**：把公开 GitHub 仓库变成交互式架构图（页面/API 路由/服务/数据库/外部服务），React Flow 可视化。
- **对主项目价值**：**低中**。主项目前端可参考其架构图可视化（docs 展示）。
- **可借鉴点**：架构图生成管线、React Flow 交互。

### 47. filiksyos__gitreverse
- **是什么**：把公开 GitHub 仓库 → 单条 synthetic user prompt（供 Cursor/Claude Code vibe code 从零重写项目）：拉元数据 + 文件树 + README → LLM 生成对话式 prompt。
- **对主项目价值**：**低中**。反向提示词工程工具，趣味性强，对主项目 agent 化参考有限。
- **可借鉴点**：仓库上下文摘要压缩为 prompt 的技巧。

### 48. LifeOS
- **是什么**：AI 驱动个人生活操作系统（danielmiessler）：目标状态管理 + 个人知识管理（Obsidian 体系）。
- **对主项目价值**：**低中**。偏个人知识管理/生活方式，主项目记忆模块可借鉴其"当前状态→理想状态"结构化。
- **可借鉴点**：结构化目标/状态建模。

### 49. vibe-code-common-sense / vibe-coding-cn
- **是什么**：agentic coding 经验方法论（英文文档/skill + 中文社区指南两版本）：把 agent 当笨蛋直到项目证明反之，含项目启动/架构锁定等最佳实践。
- **对主项目价值**：**低中**。工程规范/方法论文档，可作主项目开发流程参考。
- **可借鉴点**：项目启动护栏、agent 信任边界管理。

---

## 低价值项目（一句话说明）

- **nuclei-templates**：ProjectDiscovery 的 Nuclei 漏洞检测模板库（cloud/dast/dns/http/network 等 YAML 模板）——主项目非安全扫描器，仅作安全基线参考。
- **system-design-notes**：系统设计面试学习笔记（限流/一致性哈希/KV/URL 缩短/聊天/爬虫等经典题目）——纯学习资料，无代码价值。
- **Open-Source-Face-Recognition-SDK**：Faceplugin 的免费开源人脸识别 SDK（Windows/Linux，Python，本地推理）——人脸识别领域，与主项目无关。
- **ai-engineering-field-guide**：AI 工程岗位/技能/面试的数据驱动指南（6964 份 JD 分析）——职业资料，非代码。
- **NousResearch__hermes-plugin-touchdesigner**：Hermes Agent 驱动 TouchDesigner 视觉编程的 MCP 插件（twozero 嵌入）——MCP 插件打包模式可参考，领域无关。
- **minimind**：从零训练 3B LLM 的开源教学项目（预训练/微调全流程）——主项目是网关非训练，仅科普价值。
- **ClawTeam-OpenClaw**：OpenClaw 的 ClawTeam 分支（多语言 README 的 agent 平台）——与主项目 agent 化相关但主项目已有 OpenClaw 参考，分支差异有限。
- **popcorntime**：Rust/Tauri 重构的看电影/电视流媒体应用——与主项目无关。
- **avoid-ai-writing**：审计/重写内容去除 AI 写作痕迹的 skill（detect-only/edit-in-place + 声音画像）——主项目无内容生成业务，参考价值低。
- **claude-code-system-prompts**：Claude Code 系统提示词收集仓库（Piebald 发布）——提示词快照参考，非工程代码。
- **anpicasso__hermes-plugin-chrome-profiles**：通过 CDP 在多个 Chrome/Edge 配置间切换浏览器工具的 Hermes 插件（每配置独立 cookies/会话）——多配置浏览器自动化，主项目代理池场景低相关。
- **mana**：空仓库（仅 .git，无任何内容）——无价值。
- **cinar__indicator**：Go 金融技术指标库（趋势/动量/波动率/成交量 + 回测）——金融领域，与主项目无关。
- **AD-PathFinder**：NetSPI 的 AD 攻击路径映射工具（分析 SharpHound 数据，红队/渗透）——渗透领域，与主项目无关；仅安全知识参考。
- **RuView**：WiFi 人体感知系统（DensePose 隔墙测呼吸/心率，接入 Home Assistant/Apple Home）——物联网传感，与主项目无关。
- **Constrict**：GNOME 桌面视频压缩工具（视频压到目标大小）——桌面工具，视频处理可微参考。
- **interview-coder-withoupaywall-opensource**：面试辅助 Electron 工具（隐身窗口提示代码，社区免费版）——灰色用途工具，主项目无相关业务，不建议借鉴。
- **free-code-main**："无护栏版 Claude Code"（去遥测/解锁实验功能单二进制）——与主项目"工具调用安全护栏"主题相悖，仅作反例参考。
- **awesome-threat-intelligence**：威胁情报资源精选清单——参考清单，非代码。
- **public-apis**：公共 API 精选清单——参考清单，主项目上游聚合思路可微参考。
- **HKUDS__DeepTutor**：终身个性化智能导师系统（HKUDS，对话式辅导）——教育领域，主项目无相关业务。
- **ayghri__i-have-adhd**：ADHD 友好输出风格插件（多模型 extension 支持）——纯提示词风格工程，参考价值低。
- **VibeNVR**：容器化视频监控系统（IP 摄像头/录像/运动检测/React 前端，自定义视频引擎）——监控领域，视频引擎思路可微参考。
- **kudu**：Windows/macOS/Linux 系统清理器 + 安全扫描器（Electron）——系统工具，与主项目无关。
- **Archon**：开源 harness builder for AI coding（确定性/可复现编码 harness，含 auth-service/agent-service 微服务）——与主项目 agent 化弱相关，体系偏重，归入低价值。

---

## 汇总

- **高价值 10 个**：headroom（上下文压缩）、tingly-box（agent 网关）、mission-control（agent 控制平面）、bernstein（治理层）、FailproofAI（护栏/可观测）、memanto（记忆 Agent）、gbrain（记忆底座）、claude-context（语义代码搜索）、Claude-Code-Source-Study（学习地图）、ECC（本项目已用的 harness）。
- **中价值 ~38 个**：覆盖 agent 编排（open-swe/crewAI/mco/loop-engineering/kandev/vicoa）、桌面 agent（nuphus/monocode/Poracode/moon-code/Minke/DeepSeekGUI）、研究 agent（openscience/OpenResearch/hyperresearch/autoresearch）、视频生成（seedance-2.0/BigBanana/PreenCut）、Web/爬虫（wigolo/crawl4ai/web-check）、可观测性（tracecrate/Empirica）、工作流（texera）等。
- **低价值 ~32 个**：多为领域无关工具、学习资料、参考清单、空仓库与灰色工具。
- 全部 80 目录已覆盖，无遗漏。`mana` 为空仓库，`goose-main` 为 `goose` 旧版副本，`claude-context-master` 与 `claude-context` 同源，`deepseek-harness` 与 `DeepSeekGUI` 存在父子关系（GUI 基于 harness）。
