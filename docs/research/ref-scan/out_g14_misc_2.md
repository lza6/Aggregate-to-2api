# g14_misc_2 扫描报告（80 目录）

> 扫描员：g14_misc_2 · 根路径 `D:/参考项目/` · 只读分析
> 判定维度：①agent/skills/mcp/context 工程 ②图片/视频/音频/电商/办公文档/多模态 ③网关/API/队列/任务编排 ④桌面/浏览器/自动化 ⑤工程规范/交互/性能/安全
> 格式：高价值=完整5行；中低价值=紧凑1-2行

---

## 高价值项目（与主项目强相关）

### 1. tirth8205__code-review-graph
**代码审查知识图谱工具**（MCP 工具集，主项目已集成使用中）
- 解决什么问题：审查代码变更时按风险排序、给出受影响调用方/流程上下文，省 token。
- 关键能力：detect_changes / get_review_context / get_impact_radius / query_graph / get_architecture_overview 等，PyPI + VSCode 扩展 + CI action。
- 与主项目关联：主项目 CLAUDE.md 已将其列为核心知识工具链，本仓库即为该工具的落地参考实现。
- 建议：作为对照参考，无需再引入；后续图谱升级直接对齐此仓库最新版本功能。

### 2. cloudflare_temp_email
**Cloudflare 免费临时邮箱服务**（Pages/Workers + D1 + WASM 邮件解析）
- 解决什么问题：自建临时邮箱收信系统，支持多域名、多语言前端、邮件解析。
- 关键能力：Cloudflare Pages 部署、mail-parser-wasm、DB 层、e2e 测试、skills 目录。
- 与主项目关联：主项目 `email_pool.py` + `email_sources/` 内置 8 种临时邮箱源，此项目可作"自建邮箱源"（CF Workers + 域名，属 L3 边界）的完整参考实现。
- 建议：高优先级参考——若未来授权自建邮箱源，直接移植其收信/解析/WASM 链路。

### 3. google__adk-python
**Google Agent Development Kit 2.0**——code-first 的 Python 多智能体开发框架
- 解决什么问题：标准化构建/评测/部署 agent，含代码执行、MCP、eval、多 agent 协作、记忆。
- 关键能力：Python 3.10-3.14 支持、constraints 多版本、llms.txt 文档、contributing/规范完备。
- 与主项目关联：主项目 agent 化（意图识别/DAG 编排/critic）可直接借鉴 ADK 的 agent 定义/工具注册/编排分层设计；同为 Python 生态。
- 建议：主项目 agent 层重构或扩展时，以 ADK 的 `LLMAgent`/`ToolContext`/`SessionMemory` 抽象为对标蓝本。

### 4. nanobot（HKUDS）
**超轻量自托管个人 AI Agent 框架**（Python 3.11+）
- 解决什么问题：WebUI/终端/聊天应用三形态的轻量 agent，组合工具+长期记忆+MCP+模型路由+多代理委派+定时自动化。
- 关键能力：单文件可读核心、OpenAI 兼容 API、多聊天平台（Telegram/Discord/WeChat/Slack 等）。
- 与主项目关联：技术栈（Python/OpenAI 兼容 API/记忆/MCP 服务端）与主项目高度重合，其"轻量 agent 核心 + 多平台接入"架构是主项目 agent 模块的理想参考。
- 建议：重点阅读其工具注册、记忆持久化、模型路由三处实现，均可迁移思路。

### 5. letta / letta-code-main
**有状态 Agent + 记忆优先编码 Harness**（原 MemGPT）
- 解决什么问题：跨会话持久的 agent 记忆，agent 跨模型可移植（Claude/GPT/Gemini/GLM 等）。
- 关键能力：letta-code 为实际代码（npm 包，记忆优先编码 harness）；letta 仓库现为 landing page。
- 与主项目关联：主项目"记忆巩固"模块可参考其 memory block 管理、跨模型可移植设计。
- 建议：主项目记忆层若演进，参考 letta-code 的持久 agent 会话/记忆架构。

### 6. ruflo-main
**企业级 Claude Code 多智能体编排平台**（原 claude-flow，v3.5）
- 解决什么问题：16 种专业 agent 角色 + 自定义类型 swarm 编排、自学习、容错共识、企业级安全。
- 关键能力：Rust WASM 内核驱动策略引擎/embeddings/证明系统、npm 生态、fault-tolerant consensus。
- 与主项目关联：主项目已有 DAG 编排/critic 自反思，可借鉴其共识投票、agent 角色库、安全护栏设计。
- 建议：中等优先级——共识与安全部分是主项目 critic/审核环节的升级参考。

### 7. plan-cascade
**AI 级联开发框架**（Claude Code 插件 + MCP Server + Desktop + CLI）
- 解决什么问题：复杂项目智能分解为可并行执行任务，多提供商执行。
- 关键能力：agents.json 配置、builtin-skills/external-skills、mcp-configs/mcp_server、desktop。
- 与主项目关联：主项目 DAG 编排/多代理并行可直接对照其任务分解→并行执行的 cascading 模型。
- 建议：参考其任务分解与 MCP server 集成方式。

### 8. autopus-adk
**AI 编码工具通用 Harness**（Go，16 agents / 53 skills / 5 平台）
- 解决什么问题：让 Claude Code/Codex/OpenCode 等像真实工程团队一样工作，内置规划/测试/审查/安全审计。
- 关键能力：单配置多平台、跨工具 skill 目录、install.sh/ps1。
- 与主项目关联：主项目 skills 库与多工具适配可借鉴其 skill 抽象与跨平台安装。
- 建议：参考其 skills 组织与 agent 角色分工。

### 9. bmad-autonomous-development-main
**BMad 自主并行开发编排器**
- 解决什么问题：从 sprint 积压+依赖图驱动全自动多 agent 并行流水线（create→dev→review→PR），每单元任务独立 worktree + 新上下文窗口。
- 关键能力：轻量协调器（自己不读文件不写码）、依赖图构建、MAX_PARALLEL_STORIES 并行、story 生命周期。
- 与主项目关联：主项目 DAG 编排与"每任务独立子代理"模式与此高度同构，可借鉴其依赖图+worktree 隔离+并行流水线。
- 建议：重点阅读其协调器委派模式与依赖图实现。

### 10. Continuous-Claude-v3-main
**持续学习型多 Agent 开发环境**（基于 Claude Code）
- 解决什么问题：跨会话维护上下文、编排专业 agent、通过智能代码分析省 token。
- 关键能力：109 skills / 32 agents / 30 hooks、TLDR 代码分析、记忆系统。
- 与主项目关联：主项目 agent 化+skills 库可参考其 skills/agents/hooks 三层组织与记忆系统。
- 建议：参考其记忆系统与 TLDR 分析（省 token）设计。

### 11. P-ai
**自成长桌面 AI 工作系统**（Tauri2 + Vue3 + Rust 后端）
- 解决什么问题：围绕对话/任务/记忆/部门/工具/审查/远程消息的完整桌面系统，agent 委派+长期记忆+工具审查+MCP+高并发工作区。
- 关键能力：Rust async 并发流式架构、全局热键/语音唤醒、多并行会话、数据全本地。
- 与主项目关联：主项目桌面版同为 Tauri2 sidecar，其"Rust 后端 + 前端 + 本地数据 + agent 委派"是桌面端功能增强的完整参考。
- 建议：高价值——桌面端记忆/工具审查/MCP 功能可直接对标。

### 12. mateclaw-dev
**可部署 AI Agent 平台**（Java17 + Spring Boot 3.5 + Vue3）
- 解决什么问题：让 agent 思考/行动/记忆/交付的完整平台，含 server + webchat + 插件 API + 插件示例。
- 关键能力：微服务化插件体系（mateclaw-plugin-api/sample）、WebChat 前端、docker-compose。
- 与主项目关联：其插件体系与 WebChat 交互可作为主项目 chat 端与外部工具接入的参考。
- 建议：参考其插件 API 设计（Java 栈，仅借鉴接口思路）。

### 13. parlant
**面向客户 AI Agent 的交互控制 Harness**（Python）
- 解决什么问题：约束客户对话 agent 的行为/语气/政策合规，测试驱动。
- 关键能力：guideline 策略注入、行为审查、Python 3.10+、ruff/pytest 规范。
- 与主项目关联：主项目 chat 端若需政策/风格约束，可参考其 guideline 机制。
- 建议：低-中优先级参考，若主项目要加对话护栏时再深入。

### 14. OpenManus
**通用自主 agent 实现**（MetaGPT 团队 3 小时原型）
- 解决什么问题：无邀请码的通用 agent，规划-工具-记忆-浏览器操作。
- 关键能力：Python app/ 结构、protocol/ 通信、Docker、多语言 README。
- 与主项目关联：主项目 DAG/意图识别可参考其规划循环与工具调用协议。
- 建议：作为通用 agent 架构参照（轻量，易读）。

### 15. swarms
**多 Agent 群框架**（Python）
- 解决什么问题：大规模多 agent 协作/swarm 编排、结构化 agent 团队。
- 关键能力：swarms/ 核心库、SKILL.md、examples、PyPI 生态。
- 与主项目关联：主项目多代理并行编排可参考其 swarm 模式与协作协议。
- 建议：参考其 swarm 协作模式，注意其依赖较重，仅借鉴思路。

### 16. gortex
**高性能代码智能引擎**（Go 单静态二进制，CLI + MCP + WebUI）
- 解决什么问题：把代码索引为图谱供 AI agent/IDE 查询，多仓库、跨平台、无依赖。
- 关键能力：单二进制安装、Sigstore/SLSA3 供应链安全、MCP 暴露。
- 与主项目关联：主项目使用 codegraph（代码知识图谱），gortex 是其"高性能替代/补充"方案候选。
- 建议：主项目 codegraph 性能不足或需多仓库时评估 gortex。

### 17. AMAP-ML__LongHorizon-Harness
**计算机使用 agent 的循环工程 Harness**
- 解决什么问题：给 Claude Code/Codex 等一个目标后持续工作数十小时（桌面+终端），plan→act→verify→checkpoint/recover→repeat。
- 关键能力：Python≥3.10、多后端（Claude Code/Codex/OpenCode/DeepSeek）、Benchmarks（WeaveBench/OSWorld/Terminal-Bench）、前端可视化。
- 与主项目关联：主项目任务长跑/断点续跑（DAG 续跑）可借鉴其 checkpoint/recover 循环与长时任务保障。
- 建议：高价值——长时自动化与恢复机制直接对标主项目续跑需求。

### 18. Citadel
**Claude Code / Codex 的开源操作系统层**（Node 22+）
- 解决什么问题：路由请求、会话间保留仓库状态、协调并行工作、仓库保护、记录证据与交接。
- 关键能力：插件市场安装、v1.3.5 固定版本、trust boundary 文档、THREAT_MODEL。
- 与主项目关联：主项目多代理并行+会话状态可参考其状态保留与证据/交接记录。
- 建议：参考其并行协调与状态持久化设计。

### 19. claude-octopus
**多 LLM 共识/审查工作流**（Claude 原生 + 12 家外部提供商）
- 解决什么问题：用多个模型意见/对抗性审查降低盲区，consensus gate 在交付前标出分歧。
- 关键能力：Codex/Copilot/Qwen/Ollama/OpenRouter 等 12 集成、/init /review /security-review 命令。
- 与主项目关联：主项目 critic 自反思可升级为多 LLM 共识，与 argue-master 互为补充。
- 建议：参考其多提供商集成与共识门禁实现。

### 20. layerfs
**SQLite 支持的内容寻址"时间机器"文件系统**（Rust，Ephemeral-AI-Lab）
- 解决什么问题：给每个文件系统工具调用独立临时工作区，保留后成为不可变 Commit；CAS/CDC/COW 共享基底+增量，支持零拷贝分支/并行回滚/失败丢弃。
- 关键能力：`.layerfs/context`、benchmark/fs-bench-pro 性能基准、.agents/skills/tui-design。
- 与主项目关联：主项目多 agent 并行+隔离工作区（桌面 sidecar/DAG）可参考其 COW/分支/回滚存储模型。
- 建议：高价值——多 agent 工作区隔离与版本化的进阶参考（注意 0.1.0 为 preview）。

### 21. rtk-master
**降低 LLM token 消耗 60-90% 的高性能 CLI 代理**（Rust）
- 解决什么问题：作为 LLM 代理削减 token 用量与成本。
- 关键能力：CLI proxy、Homebrew 安装、安全 CI。
- 与主项目关联：主项目成本监控/预算门禁是核心，token 削减代理可直接接入网关降本。
- 建议：高价值——研究其压缩/复用机制，评估接入主项目上游调用的收益。

### 22. genoffice
**开源 AI Office 套件**（7 个 Electron 应用共享引擎）
- 解决什么问题：MS Office 的开源替代，AI 编辑为一等公民；读写 .docx/.xlsx/.pptx/.pdf/.md/.html。
- 关键能力：文字/表格/演示/PDF/MD/HTML 页 6 合 1、AI 编辑工作流。
- 与主项目关联：主项目若涉办公文档生成/多模态（PPT/文档），此为其完整参考。
- 建议：文档/PPT 生成类功能立项时参考（Electron 栈，仅借鉴能力模型）。

### 23. MinerU
**PDF/文档解析工具**（OpenDataLab，多模态）
- 解决什么问题：把 PDF（含扫描/公式/表格）转成结构化 Markdown/JSON，支撑 RAG 与多模态理解。
- 关键能力：Python 生态、docker、mineru 核心库、模型化解析（arXiv 多篇技术报告）。
- 与主项目关联：主项目若做文档类多模态输入（图转文/PDF 知识库），MinerU 是首选方案。
- 建议：按需引入（重依赖，需 GPU/模型下载），仅当主项目明确要文档解析时。

### 24. knowledge_graph
**把任意语料转为知识图谱**（Python + notebook）
- 解决什么问题：从文本清洗→实体/关系抽取→图谱 schema→可视化与查询。
- 关键能力：jupyter 流水线、ollama 本地 LLM、NetworkX 可视化。
- 与主项目关联：主项目"记忆巩固/意图 embedding"可参考其实体-关系抽取为知识图谱的做法。
- 建议：中优先级，若主项目记忆层要升级为图谱记忆时参考。

### 25. jiawenyao401__BorderlessSKU
**跨境电商多模态商品本地化 Agent**（生产级，AliExpress）
- 解决什么问题：基于同一商品事实生成可审计的三语文案/主图/详情图/商品视频/类目属性映射/发布风险判定。
- 关键能力：商品事实保真（源图唯一事实源）、qwen 系列模型、服装类目 3 市场、1.7.0。
- 与主项目关联：主项目为图像/多模态生成网关，其"多模态输出 + 事实保真 + 可审计"管线是电商场景上游客户案例。
- 建议：主项目图像生成可承接此类多模态本地化任务的参考场景。

### 26. abingyyds__Toonflow-app
**AI 视频/动漫批量生成工具**（Electron + 决策/执行/监督三层 agent 协同）
- 解决什么问题：批量生成动漫/视频内容，ScriptAgent 出剧本、素材生成、质量审阅与修订反馈。
- 关键能力：多层 agent 协同（拆解→生成→审阅→修订）、electron-builder、railway 部署。
- 与主项目关联：主项目图像/视频生成上游 + agent 编排，可直接对标其"监督层审阅反馈"闭环。
- 建议：高价值——其生成-审阅-修订闭环与主项目 critic 自反思理念一致。

### 27. violin
**开源视频翻译 Skill**（CLI + FastAPI + Claude Code skill）
- 解决什么问题：上传视频→转写→翻译→目标语言配音→重新封装，可选 SRT 字幕。
- 关键能力：FastAPI web app、pipeline/ 编排、prompts/ 模板。
- 与主项目关联：主项目 FastAPI 网关 + 对话，可新增视频翻译能力或作为上游示例。
- 建议：视频翻译类功能直接复用其 pipeline 思路。

### 28. hyperframes
**写 HTML 渲染视频**（Node ≥22，为 agent 构建）
- 解决什么问题：用 HTML/CSS 声明式生成视频帧，面向 agent 的视频合成。
- 关键能力：npm 包、DESIGN.md、多语言文档。
- 与主项目关联：主项目若做视频生成上游，可参考其 HTML→视频合成管线。
- 建议：低-中优先级参考。

### 29. calesthio__OpenMontage
**首个开源 agentic 视频制作系统**
- 解决什么问题：agent 驱动的完整视频制作流水线（backlot/ 素材库 + prompt gallery）。
- 关键能力：多 AI 编码工具支持（AGENTS/CODEX/COPILOT/CURSOR 文档）、README_zh-CN。
- 与主项目关联：主项目视频生成方向的可选参考。
- 建议：低-中优先级。

### 30. argue-master
**结构化多 Agent 辩论引擎**
- 解决什么问题：多 agent 独立分析→多轮互相质疑→投票收敛共识，降低幻觉、提升严谨性，产出经同行评分的报告。
- 关键能力：claims/votes/dossier 全流程 JSON 落盘、作为 Claude Code skill 安装、实时 viewer。
- 与主项目关联：主项目 critic 自反思可升级为多 agent 辩论共识（与 claude-octopus 互补）。
- 建议：高价值——辩论+投票机制是主项目审查环节的进阶方案。

---

## 中/低价值项目（紧凑结论）

- **cate**：无限画布 IDE，专为并行编码 agent 设计（Electron+vite）。→ 主项目桌面端交互形态参考（低-中）。
- **bountyyfi__lonkero**：Rust 专业级渗透测试扫描器（专有许可）。→ 与主项目无关，仅安全工具同类。
- **daytona**：开发环境管理器，**已停止维护**（2026-06 转私有）。→ 低价值，仅参考其 dev-container/环境自动化思路。
- **multithread-native-vs-wasm**：C 多线程 N-body 在 native vs WebAssembly 的性能对比实验。→ 纯 benchmark，无关。
- **claudecode-main**：Rust 写的开源 Claude Code 替代实现（终端 agent shell、工作区工具、持久会话）。→ 主项目 agent 化参考其 Rust 实现（中）。
- **openwiki**：agent 自动撰写并维护代码库/personal 知识 wiki，支持 13 模型提供商 + 连接器 + 可视化。→ 主项目文档/记忆参考（中）。
- **daintree**：AI 编码 agent 的"栖息地"（Electron 桌面，并行运行多个 agent 各占独立 git worktree、可观测、人留环中）。→ 主项目多 agent 并行隔离与桌面端协调参考（中）。
- **argue-master**：见上（高）。
- **witt3rd__oh-my-hermes**：Hermes Agent 多 agent 编排 skills 集（deep-research/ralplan 共识规划/ralph 验证执行/triage），零依赖。→ 主项目 skills 库与规划-执行循环参考（中-高）。
- **shareAI-lab__learn-claude-code**：Claude Code harness 工程教程（agent 循环/工具/权限/hooks/todo/subagent/skill 加载）。→ 主项目 agent 工程学习资料（中）。
- **knowledge_graph / airecon / pentagi**：见上及下方。
- **airecon**：AI 自主渗透测试 agent（Ollama + Kali Docker 沙箱 + RECON→ANALYSIS→EXPLOIT→REPORT 流水线 + Textual TUI）。→ 安全参考，主项目安全审查可借鉴流水线化（中）。
- **pentagi**：渗透测试通用智能体（PentAGI，Docker 全栈，含 observability/e2e compose）。→ 安全参考，编排复杂度值得看（中）。
- **awesome-dsh-plugin**：DeepSeek Harness 社区插件清单/市场。→ 主项目插件生态思路参考（低）。
- **Adnify**：AI 原生工程工作区（Electron，直接执行 + 受治理多 agent 规划）。→ 主项目桌面/工程工作区参考（中）。
- **cutter**：Rizin 驱动的开源逆向工程平台（C++/Qt）。→ 与主项目无关。
- **Citadel**：见上（高）。
- **tirth8205__code-review-graph**：见上（高）。
- **fff**：Rust 高速文件搜索工具（typo 容错、频率排序、内存索引），被 opencode/nushell 使用。→ 主项目搜索/性能参考（低-中）。
- **jiawenyao401__BorderlessSKU**：见上（高）。
- **librarium**：证据感知的多提供商研究工具（npm，人+agent 用，v2 catalog）。→ 主项目 deep-research 类功能参考（中）。
- **cloudflare_temp_email**：见上（高）。
- **AgriciDaniel__claude-ads**：Claude-first 付费媒体运营（12 广告平台，默认只读+审批门禁）。→ 与主项目无关；其"默认只读+审批+幂等+回滚门禁"工程模式值得借鉴（低-中）。
- **nodeskclaw**：人机共营开源平台（Cyber Workspaces：黑板/任务委派/实时协作，含 hermes 桥）。→ 主项目协同面板参考（中）。
- **eneskirca__nodeterm**：节点式终端管理器（无限画布上多终端/Claude Code 会话 Trello 板，Electron）。→ 桌面端形态参考（低-中）。
- **genoffice**：见上（高）。
- **boardui**：React agentic 界面设计系统（聊天组件+仪表盘一体，可一键 Vercel 部署）。→ 主项目 React 管理面板 UI 参考（中）。
- **oomol-lab__open-connector**：开源连接器网关（MCP/OpenAPI 3.1，Pipedream/Composio 替代，Cloudflare 兼容）。→ 主项目 MCP 服务端/外部服务接入参考（中-高）。
- **Stratum**：Go+React 企业级 AI 原生应用编排平台（DDD 分层、多租户）。→ 主项目编排层架构参考（中）。
- **flue**：TS 的 agent harness 框架（'use agent' 函数式声明模型/沙箱/skill/tool 组合）。→ 主项目 agent 层声明式写法参考（中）。
- **parlant**：见上（中）。
- **portless**：把端口号替换成稳定 .localhost 命名 URL 的本地开发工具。→ 低价值，仅开发体验。
- **blade-code**：新一代 AI 编程助手（CLI+Web+Headless，Node）。→ 主项目 agent 化竞品参考（低-中）。
- **opentofu**：Terraform 的开源分支（IaC）。→ 与主项目无关。
- **EpicInfographics**：教 agent 设计"不像 AI 生成"信息图的 skill。→ 主项目前端/图像设计参考（低-中）。
- **nezha**：专为 AI 编程打造的轻量跨平台 IDE（Tauri，多项目工作区/实时终端/会话自动发现/Git worktree/Skill 管理）。→ 主项目桌面端 IDE 化参考（中）。
- **hyperframes**：见上（低-中）。
- **violin**：见上（高-视频翻译）。
- **Claude-Code-Projects-Index-main**：Claude Code 项目/agent 工作区蓝图索引（按用途分类）。→ 主项目 agent 模式素材库（低）。
- **gortex**：见上（高）。
- **Better-Fullstack**：TS/React/RN/Rust/Go/Python 全栈 AI 开发参考（多 app monorepo + MCP + benchmarks）。→ 工程规范参考（低-中）。
- **letta-code-main / letta**：见上（高）。
- **MinerU**：见上（高-按需）。
- **AstrBot**：多平台聊天机器人框架（Python 3.12+，连接 QQ/微信/Telegram 等，插件化，含 Web 面板）。→ 主项目 chat 端点多平台接入参考（中）。
- **abingyyds__Toonflow-app**：见上（高）。
- **rtk-master**：见上（高）。
- **open-claude-tag**：Claude Tag（Slack 内常驻 AI 队友）的开源替代（Python，LLM 无关，MCP-native，channel 原生）。→ 主项目对话/协同扩展参考（中）。
- **ibywind__ai-daily-news**：每日自动抓取六大领域热点生成精美日报（GitHub Pages 部署）。→ 主项目内容自动生成参考（低）。
- **nonecap-py / nonecap-js**：NoneCap hCaptcha 求解 API 的 Python/TS 官方客户端（提交→轮询→token）。→ 与主项目 cf_solver（Turnstile）同类；可作付费求解源的接入参考，但属付费 API 红线（低-中）。
- **nanobot**：见上（高）。
- **PromptFill**：AI 绘画 prompt 填空器（结构化 prompt 生成，GPT/MJ/Nano Banana）。→ 主项目图像生成 prompt 工程参考（中）。
- **Continuous-Claude-v3-main**：见上（高）。
- **sxyazi__yazi**：Rust 异步终端文件管理器（高性能 I/O/任务调度）。→ 低价值，仅终端工具。
- **bmad-autonomous-development-main**：见上（高）。
- **OtterHub**：基于 Cloudflare KV + Telegram Bot 的免费私人云盘（Next.js）。→ 低价值，与主项目无关。
- **next-1688__1688-item-select**：1688 电商选品 Skill（SKILL.md + CLI）。→ 电商场景低相关（低）。
- **swarms**：见上（中）。
- **mateclaw-dev**：见上（中-高）。
- **shadcn-ui__lint**：agent-first 的 Tailwind 设计系统 linter（@shadcn/lint，ESLint/Oxlint）。→ 主项目前端设计系统约束参考（低-中）。
- **github-readme-stats**：动态生成 GitHub 统计卡片。→ 低价值，与主项目无关。
- **ian-xiaohei-illustrations**：指导 AI 为中文文章生成手绘配图的 Codex Skill。→ 主项目图像生成 prompt/风格 skill 参考（低）。
- **claude-octopus**：见上（高）。
- **free-vpn-anti-rkn**：俄语 VPN 订阅绕过站（静态页）。→ 无关。
- **OpenManus**：见上（高）。
- **kid-papercraft**：用热门动画 IP 为孩子定制 30 秒折纸生日视频的 Codex Skill（Gemini Omni Flash）。→ 视频生成 skill 参考（低）。
- **docus**：Vue 的 Markdown 文档框架。→ 主项目 landing(Vue3)/文档站参考（低-中）。
- **swoole__typephp**：PHP AOT 原生编译器。→ 无关。
- **garrytan__gstack**：YC CEO Garry Tan 的个人 agent 化产品开发工作流 harness（skill 模板 + 方法论 + LOC 测量）。→ 主项目工作流/效率方法论参考（中）。
- **nonecap-js**：见 nonecap-py（低-中）。
- **letta**：见上（高）。
- **layerfs**：见上（高）。
- **autopus-adk**：见上（高）。
- **AMAP-ML__LongHorizon-Harness**：见上（高）。
- **P-ai**：见上（高）。
- **miqdadbadjuber__anti-slop**：教 agent 规避 AI 味文本/设计的 skill 合集（rules/skills/cli）。→ 主项目前端/文案质量参考（低-中）。
- **calesthio__OpenMontage**：见上（低-中）。
- **ericrisco__rsc-harness**：agent harness 生成器（272 skills，读项目→按最佳实践生成 harness 计划）。→ 主项目 agent 工程脚手架思路参考（中）。

---

## 汇总：主项目可借鉴 Top 建议

| 主项目模块 | 对标项目 |
|---|---|
| agent 化（意图/DAG/critic） | argue-master（辩论共识）、claude-octopus（多LLM共识）、plan-cascade、bmad、Continuous-Claude、swarms |
| 记忆巩固 | letta-code、nanobot、knowledge_graph、openwiki |
| skills 库 | oh-my-hermes、autopus-adk、Continuous-Claude、rsc-harness、EpicInfographics、anti-slop |
| 邮箱池（自建源） | cloudflare_temp_email（CF Workers+WASM 收信） |
| 成本/预算 | rtk-master（token 削减 60-90%） |
| 桌面端（Tauri2） | P-ai、nezha、Adnify、cate、nodeterm |
| 任务长跑/续跑 | AMAP LongHorizon-Harness、layerfs（COW 工作区） |
| 代码知识图谱 | gortex（codegraph 高性能替代候选）、tirth code-review-graph（已用） |
| 视频生成 | Toonflow（生成-审阅-修订闭环）、violin（翻译）、hyperframes（HTML→视频）、OpenMontage |
| 文档/办公 | genoffice、MinerU |
| 多模态电商 | BorderlessSKU |
| MCP/连接器 | oomol open-connector、google adk |
