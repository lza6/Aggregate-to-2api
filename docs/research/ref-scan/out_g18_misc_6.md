# g18_misc_6 扫描报告（80 个目录）

> 扫描时间：本会话。方法：批量 ls + README 前 20-30 行识别真实功能，疑似高价值者深入确认。
> 价值维度：①agent/skills/mcp/context ②生成（图/视频/音频/办公/电商）③网关/API/队列/任务编排 ④桌面/浏览器/自动化 ⑤工程规范/交互/性能/安全。

---

## ⭐ 疑似高价值（完整 5 行格式）

### sirchmunk-main — 原始数据→自进化智能体（实时）
- **是什么**：Python3.10/FastAPI + Next.js14 + DuckDB OLAP 的数据分析智能体工作台，从原始数据实时构建"自进化智能体"，内置 MCP Server + 多格式文本抽取（Kreuzberg + ripgrep-all）。
- **解决什么问题**：把非结构化/半结构化数据实时变成可问答、可记忆、可进化的分析工作流，替代手动 ETL 与记忆碎片。
- **对主项目价值**：**高**。主项目已用 FastAPI+SQLite；其 MCP server 封装、DuckDB 分析链路、实时自进化记忆设计可借鉴到「听风AI」的分析/审计/记忆巩固模块；数据→智能体工作流与 agent 化方向强相关。
- **技术栈**：Python3.10+/FastAPI/Next.js14/Tailwind/DuckDB/ripgrep-all/Kreuzberg/MCP Python SDK。
- **备注**：README 完整、中文友好，本地可跑。

### open-design — 开源版 Claude Design（设计/生图平台）
- **是什么**：Apache2.0 的 Claude Design 替代品，桌面端 + web 端 + daemon 架构，集成设计系统/插件/编码 agent/媒体提供商，支持 GPT/Claude/DeepSeek agent 与 GPT Image/Seedream/Nano Banana 生图。
- **解决什么问题**：把"AI 设计与生图"做成自托管产品（原型、deck、设计系统、媒体生成一体化），对比 Claude Design 免锁定。
- **对主项目价值**：**高**。①上游媒体提供商聚合模式（生图多厂商）与主项目「听风AI」图像网关直接对标；②其 daemon+desktop+web 三层架构可参考「听风AI」桌面 Tauri2 sidecar 设计；③DeepSeek Harness(dsh) 原生集成方式可借鉴。
- **技术栈**：monorepo（apps: closure/daemon/desktop/packaged/web），TS + agent 集成。
- **备注**：成熟产品级代码，发布节奏密集。

### Pi (earendil-works/pi) — 可自扩展编码 agent harness
- **是什么**：Node/TS 的 Pi agent harness + 自扩展编码 agent（packages: agent/ai/chord/client/coding-agent/protocol/server/session-backends/tui/telemetry），提供协议化 agent 运行时。
- **解决什么问题**：给 agent 一个可插拔、可自扩展的 harness 底座（协议、session 后端、TUI、遥测），避免各工具各自为政。
- **对主项目价值**：**高**。①session-backends + telemetry + protocol 分层与「听风AI」SSE 事件流/遥测(tail-based 采样)可互鉴；②自扩展 agent 思路与 skills 库 + MCP 服务端方向一致。
- **技术栈**：TypeScript monorepo，biome，多 CLI（pi-test.sh/bat/ps1）。
- **备注**：harness 级基础设施，参考其协议与遥测设计价值大。

### Octop (TencentCloud) — 自托管多用户多智能体 AI 助手
- **是什么**：Python3.12 自托管 AI 助手，单进程起 Web 控制台 + CLI + IM 接入（飞书/钉钉/QQ/Discord/企微）+ HTTP/SSE；多用户专家团队、MBTI 人格、JWT 隔离、工具审批、shell 护栏、PII 脱敏、MCP/ACP 网关、远程桌面、浏览器 AI+。
- **解决什么问题**：把 AI 助手做成可自托管、多用户、可插拔后端的"数字生命体"，安全内置。
- **对主项目价值**：**高**。①IM 接入（飞书/钉钉/企微/QQ/Discord）+ HTTP/SSE 与主项目聊天/生图网关入口高度可复用；②MCP 网关、JWT 多用户隔离、PII 脱敏、工具审批等安全工程正是主项目薄弱点；③专家库 = agent 化。
- **技术栈**：Python3.12/FastAPI(推断)/ruff，harness-memory 可移植记忆，多存储后端（本地/容器/Postgres/COS/S3）。
- **备注**：腾讯云出品，工程完整度高，README 中文详尽。

### cs-board — 白板声画工坊（AI 视频制作工作台）
- **是什么**：本地运行的 AI 视频制作工作台——上传参考音频 + 中文文案 → 音色克隆、内容拆解、插画、手绘笔迹、字幕、音画合成，导出 MP4；局域网团队共用队列。
- **解决什么问题**：把"AI 白板动画视频"全流程自动化，素材/密钥/任务历史本地保留。
- **对主项目价值**：**中高**。①主项目主打图像/对话生成，此项目是视频/音频生成补充形态，可作上游扩展参考；②OpenAI 协议兼容 + ComfyUI 的 MiniMax H3 视频 API 接入是直接可借鉴的 provider 集成范本。
- **技术栈**：webapp + 队列（团队共用制作队列），SKILL.md + agent 编排。
- **备注**：付费视频上游（MiniMax）符合主项目「付费 API 红线」的 Mock 验证场景。

### HKUDS__ViMax — Agentic 视频生成框架
- **是什么**：香港大学 Data Science 出品的 agentic 视频生成（idea2video / script2video），Python3.12 + uv，多 agent 运行时、pipeline、prompts 结构化。
- **解决什么问题**：把"想法/剧本"编排成视频生成 agent 工作流（多 agent 协同生成视频）。
- **对主项目价值**：**中高**。①agent 化 pipeline 编排（多 agent 协同）与主项目 DAG 编排/critic 自反思可互鉴；②视频生成 agent 化可作为上游能力扩展方向（主项目目前无视频）。
- **技术栈**：Python3.12/uv/MIT，agents + pipelines + interfaces 分层。
- **备注**：学术机构出品，结构清晰；arXiv 论文支撑。

### MemeCalculate__moyin-creator — 魔因漫创（AI 影视生产级工具）
- **是什么**：面向 AI 影视创作者的生产级工具（AGPL-3.0），五大板块环环相扣：剧本→角色→场景→导演→S级（Seedance 2.0/SkyReels-V4 多模态），支持短剧/动漫番剧/预告片批量化生产。
- **解决什么问题**：把"剧本到成片"全流程流水线化——剧本解析引擎（拆场景/分镜/对白）、角色一致性系统（6 层身份锚点 + 角色圣经 + 参考图绑定）、场景生成（多视角联合图）、专业分镜系统、多镜头合并叙事视频（@Image/@Video/@Audio 多模态引用、智能三层 prompt 融合、首帧图网格拼接、Seedance 参数约束自动校验）。
- **对主项目价值**：**中高**。①视频生成上游（Seedance 2.0）+ 多模态 prompt 拼装（参数约束自动校验、首帧拼接）正是主项目图像 provider 扩展视频方向可借鉴的；②剧本/角色/场景分层流水线与主项目 DAG 编排理念同构；③依赖 Memefast API 中转聚合（真实付费上游，符合 Mock 验证场景）。
- **技术栈**：AGPL-3.0，build 打包，demo-data/docs/changelog 齐全，中文 README 详尽。
- **备注**：付费视频上游 + 多模态约束校验，建议先 Mock 验证再评估接入。

### Open-Pomelli — Google Pomelli 开源替代（品牌/电商创意生成）
- **是什么**：贴任意网站 URL → 提取可编辑 Brand DNA → 生成品牌营销概念、8 平台尺寸创意图、AI 产品摄影（6 类×5 风格=30 预设）、短视频（seedance-lite i2v）；单用户自托管、无鉴权、SQLite，全部 AI 调用走单一 provider MuAPI。
- **解决什么问题**：把"品牌资产/电商创意/产品图/短视频"从 URL 一键批量化生成，含浏览器内画布编辑器（9 宫格排版、改背景、重生成）。
- **对主项目价值**：**中**。①多模态 provider 路由（text/vision/image/image-edit/video 全走一个网关）+ 参数校验与主项目图像网关路由理念一致；②品牌/电商生成是主项目生图能力的新应用面；③强绑 MuAPI，仅参考其工作流与 prompt 拼装，不直接复用。
- **技术栈**：Next.js16/React19/TS/Tailwind4 + Prisma(SQLite) + Playwright 爬站 + MuAPI。
- **备注**：品牌营销/电商生成方向参考；真实付费上游注意 Mock 验证。

### OpenViking (volcengine) — AI Agent 上下文数据库
- **是什么**：字节火山引擎出品的"AI Agent 的上下文数据库"，Rust 实现 + Web Studio，提供上下文存储/检索/管理，中文友好。
- **解决什么问题**：为 agent 提供持久化、可检索的上下文数据库，解决跨会话上下文丢失。
- **对主项目价值**：**高**。主项目已用 OpenWolf/记忆巩固，此项目是专用上下文存储方案，可评估替换/增强当前记忆层；Rust + AGPL 注意授权。
- **技术栈**：Rust/Cargo/AGPL-3.0，Caddy，Web Studio。
- **备注**：volcengine 官方项目，文档与中文支持齐全。

### openclaw__clawhub — OpenClaw 公开技能注册表
- **是什么**：OpenClaw 生态的公开技能注册表（registry）：发布/版本化/搜索文本型 agent skills（SKILL.md + 支撑文件），支持快速浏览 + CLI 友好 API、审核钩子、向量搜索；同时是 OpenClaw 代码插件/bundle 插件/整包 Claw 的包目录。
- **解决什么问题**：让 agent skills 可发现、可版本、可分发（registry 化），解决"技能散落各处找不到"问题。
- **对主项目价值**：**中高**。主项目已有 skills 技能库 + 记忆/agent 化，其 registry 化发布/搜索/向量检索 + 审核钩子设计可直接对标主项目 skills 的分发与治理（含 marketplace/插件元数据规范）。
- **技术栈**：Bun/Node（bun.lock），MIT，CI 齐全，DESIGN.md/VISION.md 有架构文档。
- **备注**：与主项目 skills 库建设强相关，参考其注册表数据模型与 CLI API。

### redcell — AI agent 端到端渗透测试 + 报告
- **是什么**：Python3.12/FastAPI + React+Vite + Postgres + Redis + LiteLLM 的 AI 渗透测试平台，agent 全流程跑完渗透并自动写报告。
- **解决什么问题**：把渗透测试（扫描→利用→报告）交给 agent 自动完成，模型无关（LiteLLM）。
- **对主项目价值**：**中高**。①FastAPI+React 技术栈与主项目一致，其任务队列(Redis)/报告生成模式可借鉴到「听风AI」任务/审计系统；②安全合规方向与主项目 Security 页/安全工程呼应。
- **技术栈**：FastAPI/React/Vite/Postgres/Redis/LiteLLM，模型无关。
- **备注**：安全工具类，仅作工程借鉴，不直接接入。

### ccteam — 多编码 agent 编排成一支团队
- **是什么**：Rust 实现的 agent 编排层——把 Claude Code/Codex/Grok/Kimi/Deepseek Harness 统一成一支团队，任意会话可跨厂商跨机器 spawn/dispatch/collect，从 Telegram/Lark/浏览器远程指挥。
- **解决什么问题**：多 agent 跨厂商统一调度与协作，解决"4-10 个 agent 混乱"问题。
- **对主项目价值**：**中高**。①跨厂商 agent 编排思路与主项目 DAG 编排/DAG 续跑可互鉴；②Telegram/Lark 远程指挥 = 多入口控制面，可参考。
- **技术栈**：Rust（crates 多包），macOS/Linux/WSL，MIT。
- **备注**：与 Gas Town/beads 属同赛道，三选一参考即可。

### claude-mem-main — Claude 代码助手长期记忆插件
- **是什么**：给 Claude Code/OpenClaw 等加长期记忆层（plugin + openclaw + cursor-hooks + ragtime/LLM 记忆文件），跨会话记住偏好/学到的知识，可云端同步。
- **解决什么问题**：解决 agent 跨会话失忆，记忆可安装、可移植、可同步。
- **对主项目价值**：**高**。主项目记忆层（OpenWolf/memory）可对照其插件化记忆 + 云端同步 + 会话回顾设计，尤其 memory 检索与注入策略。
- **技术栈**：Node/TS + LLM（RAG 记忆），多入口（claude/opencode/claw）。
- **备注**：与 memvid/beads 属记忆赛道，记忆方案横向可对照。

### memvid__memvid — 单文件 agent 记忆层（免数据库）
- **是什么**：Rust 实现的单文件记忆层，agent 即时检索 + 长期记忆，持久化/版本化/可移植，无需数据库。
- **解决什么问题**：给 agent 一个轻量、可移植、无需 DB 的记忆层（单文件即时检索）。
- **对主项目价值**：**中高**。主项目用 SQLite 存任务/审计，若想给 agent 加轻量记忆通道，其单文件设计是极简备选；MV2_SPEC.md 规范清晰可参考。
- **技术栈**：Rust/Cargo，docker/docs/benches 齐全。
- **备注**：与 claude-mem/beads 同一赛道，取向相反（极简 vs 图结构）。

### beads / beads-main — 分布式图结构 issue 跟踪器（agent 记忆）
- **是什么**：Go 实现，基于 Dolt 的分布式依赖感知图 issue tracker，给 coding agent 做持久化结构化记忆，替代杂乱 markdown 计划，支持跨机器/跨 agent 同步（bd dolt push/pull）。
- **解决什么问题**：让 agent 长程任务不丢上下文，用依赖图管理任务状态，天然支持团队协作。
- **对主项目价值**：**中高**。主项目已有 DAG 编排 + workflow_status.md，其「图结构任务记忆 + 分布式同步」是任务状态管理的有力参考；提供 MCP（beads-mcp）可评估。
- **技术栈**：Go/Dolt/npm/PyPI 多发行。
- **备注**：README 明确"distributed graph issue tracker for AI agents"，与主项目任务/审计层强相关。

### gastown-main — 多 agent 编排工作区管理器
- **是什么**：多 agent 编排系统（Claude Code/Copilot/Codex 等），git-backed hooks 持久化工作状态，内置邮箱/身份/交接，目标 20-30 agent 协作，工作状态存 Beads ledger。
- **解决什么问题**：解决 agent 重启丢上下文 + 多 agent 手动协调问题。
- **对主项目价值**：**中高**。与 ccteam/beads 同赛道，其 git-backed 状态持久化思路对主项目任务续跑/恢复有参考价值（主项目已有 DAG 续跑）。
- **技术栈**：Go（cmd/ + Beads ledger），Docker/e2e 齐全。
- **备注**：三选一参考（ccteam/gastown/beads），不必重复调研。

### OpenHarness-main — 轻量 agent harness 基础设施
- **是什么**：Python ≥3.10 的开源 agent harness，提供 tool-use/skills/memory/多 agent 协调，43+ 工具，114 测试通过，MIT。
- **解决什么问题**：给 agent 开发一个轻量可复用底座（工具/技能/记忆/多 agent）。
- **对主项目价值**：**中高**。主项目 agent 化（意图识别/DAG/critic/记忆）可对照其工具抽象、skills、memory 与多 agent 协调的最小实现。
- **技术栈**：Python ≥3.10/MIT，src + frontend + tests。
- **备注**：结构精简，适合作为主项目 agent 底座的学习蓝本。

### dsh-univer-office — DeepSeek Harness 的 Office 插件
- **是什么**：给 DeepSeek Harness(DSH) 一个真实 Office 环境：Univer 插件把电子表格/文档/幻灯片/画布/关系表带进同一运行时，agent 自然语言创建/编辑 Excel/Word/PPT，变更版本化 + 隔离 worktree 支持多 agent 协作。
- **解决什么问题**：让 agent 能真正操作办公文档，且每步变更可预览/批准/丢弃。
- **对主项目价值**：**中高**。主项目定位图像/对话，办公文档是内容生成新方向；其「agent 操作文档 + 版本化变更 + 隔离 worktree 多 agent 协作」范式可扩展。
- **技术栈**：Node ≥22.19，Univer monorepo（pnpm）。
- **备注**：仅作方向参考；主项目接入需评估依赖体积。

### lossless-claw-main — OpenClaw 无损上下文管理
- **是什么**：基于 LCM 论文的 OpenClaw 插件，用 DAG 摘要系统替换滑窗压缩，保留每条消息同时把活跃上下文压在 token 限制内。
- **解决什么问题**：无损上下文压缩（长会话不丢信息又省 token）。
- **对主项目价值**：**中高**。主项目大 context 治理（CLAUDE.md/记忆）可借鉴其 DAG 摘要压缩思路；token 成本控制方向一致。
- **技术栈**：TS/Node（openclaw.plugin.json）。
- **备注**：无损上下文 = 记忆 + 成本双收益，值得细读。

### headroom — AI agent 上下文压缩层
- **是什么**：Rust 实现的上下文压缩层（headroomlabs-ai），agent prompt 压缩保留关键行，PyPI+npm 双发行，Apache2.0。
- **解决什么问题**：把超长 agent 上下文压缩到真正发送的量，字节级保留关键内容。
- **对主项目价值**：**中高**。与 lossless-claw/context-mode 同赛道（上下文压缩），主项目 token 优化/记忆可对照。
- **技术栈**：Rust，Docker，CI。
- **备注**：压缩赛道代表，横向对比后再定是否引入。

### context-mode-main — 上下文管理的另一半
- **是什么**：Claude Code/OpenClaw 上下文管理模式（ELv2 许可），Hacker News 热门，微软/谷歌/元等团队使用，针对"上下文窗口另一半"问题（输出侧/指令侧管理）。
- **解决什么问题**：系统化管理 agent 上下文（模式化切换上下文，降低 token 浪费）。
- **对主项目价值**：**中高**。主项目性能调优/PROMPT_CACHING 可对照其上下文管理范式。
- **技术栈**：Node/bun，CLI bundle。
- **备注**：ELv2 许可注意；参考设计而非直接搬。

### claude-token-optimizer / claude-token-efficient / token-optimizer — token 优化三件套
- **是什么**：同类"省 token"技能/插件族——claude-token-optimizer（把旧文档挤出上下文，省 90%）、claude-token-efficient（单文件指令让回复精简）、token-optimizer（多宿主 Claude/OpenClaw/Codex/Copilot 插件）。
- **解决什么问题**：降低 agent 输出/指令 token 成本，改善长会话质量。
- **对主项目价值**：**中高**（合并评估）。主项目成本页/预算门禁/token 治理可直接吸收其规则集与基准（CONTROLLED-A-B-BENCHMARK）。
- **技术栈**：多为 Claude Code skills/plugins（markdown 规则 + benchmark）。
- **备注**：三个项目取向互补（压缩旧文/精简输出/跨宿主规则），取各自 benchmark 与规则即可；caveman 见独立条目。

### caveman-main — "少 token 达成同样效果"的压缩措辞技能
- **是什么**：名为 caveman（"why use many token when few do trick"）的 agent skill，用极简措辞压缩 prompt/回复的 token 消耗，附 caveman-compress 变体、benchmarks 与分档强度（intensity levels）。
- **解决什么问题**：通过"措辞压缩"在不清除上下文的情况下降低 token 用量并提升长会话质量。
- **对主项目价值**：**中**。与 token 优化三件套互补（它是"说话方式"侧），主项目 token 治理/预算门禁可把其规则并入同一基准体系。
- **技术栈**：Claude Code skill（caveman.skill）+ commands + benchmarks。
- **备注**：取向独特（压词非压文），作为 token 优化族的补充参考即可。


### Waza-main — 工程习惯技能集（Claude 可运行）
- **是什么**：tw93 出品的"工程习惯技能集"，把工程师已知的好习惯（review/lint/commit 等）转成 Claude 可运行的 skills，含 rules/scripts/skills/marketplace。
- **解决什么问题**：让 agent 内建工程规范习惯，可复用、可分发。
- **对主项目价值**：**中高**。主项目 rules/ 体系可吸收其"习惯→skill"封装方式与 marketplace 分发。
- **技术栈**：markdown skills + scripts，marketplace.json。
- **备注**：与主项目 skills 库建设直接相关。

### abingyyds__webnovel-writer — 长篇网文创作插件
- **是什么**：跑在 Claude Code 上的长篇网文创作插件（6.2.0），初始化设定→规划卷纲→写章→审查→沉淀记忆→查询状态→只读可视化面板，专治"写到几百章还记得住设定/伏笔/大纲"。
- **解决什么问题**：长篇内容生成的一致性（跨章记忆与大纲约束）。
- **对主项目价值**：**中**。主项目无网文方向，但其「一致性/记忆沉淀 + 只读面板」与主项目 agent 记忆巩固/前端反馈态可借鉴。
- **技术栈**：Python3.10+，Claude Code marketplace 插件。
- **备注**：内容创作类，价值偏范式借鉴。

### Egonex-AI__Understand-Anything — 代码库→交互知识图谱
- **是什么**：把任意代码库/知识库/文档变成可探索、可搜索、可问答的交互知识图谱，兼容 Claude Code/Codex/Cursor/Copilot/Gemini CLI。
- **解决什么问题**：代码库/文档理解与问答（知识图谱化检索）。
- **对主项目价值**：**中高**。主项目已用 codegraph/code-review-graph/graft 图谱，此项目是"知识图谱问答"落地方案，可对照其图谱构建+问答链路。
- **技术栈**：TS/Node + 多 agent CLI 兼容层。
- **备注**：与主项目图谱工具链同赛道，互补参考。

### cortexkit__aft — 给编码 agent 一个 IDE 和 OS
- **是什么**：Rust 实现"编码 agent 的感觉运动皮层"——文件系统/进程/IDE 级工具集（agent-file-tools crate + CLI），跨 opencode/pi 等宿主。
- **解决什么问题**：让 agent 拥有安全、高效的文件与系统操作能力（真 IDE/OS 体验）。
- **对主项目价值**：**中**。主项目桌面 sidecar 与工具调用安全护栏可借鉴其文件/进程工具封装与权限设计。
- **技术栈**：Rust + npm CLI 双发行，ARCHITECTURE.md 详尽。
- **备注**：工具面参考，非直接依赖。

### hermes-otel / briancaffey__hermes-otel — Hermes Agent 的 OpenTelemetry 插件
- **是什么**：OpenTelemetry 插件，自动把 LLM tool calls / 模型调用 / API 请求导出为 OTel spans 到任意 OTLP 后端（Phoenix/Langfuse/LangSmith/SigNoz/Jaeger/Tempo/LGTM/Uptrace/OpenObserve），含 docker-compose 全套后端。
- **解决什么问题**：agent LLM 调用可观测性（trace+metrics+logs）。
- **对主项目价值**：**中高**。主项目已用 OTel tail-based 采样（错误 100%+正常 10%），此项目是 agent 侧 LLM 调用埋点的现成参考（尤其 OTLP 多后端样例配置）。
- **技术栈**：Python，pyproject，多后端 docker-compose。
- **备注**：两个同名目录一个主仓库一个 fork，取其一即可。

### free-for-dev — 开发者免费服务清单
- **是什么**：知名 awesome 清单，收集有免费 tier 的 SaaS/PaaS/IaaS 等服务（1600+ 人维护）。
- **解决什么问题**：找免费/低成本上游与服务（邮箱/存储/API）。
- **对主项目价值**：**中**。主项目邮箱池（email_sources 多临时邮箱源）、代理池、上游选择可从中物色免费资源。
- **技术栈**：markdown 清单。
- **备注**：直接资料库，按需查阅。

### claude-plugins-official-main — Claude Code 官方插件目录
- **是什么**：Anthropic 官方的 Claude Code 插件目录（internal + external 插件），可 /plugin install 安装。
- **解决什么问题**：发现/分发官方与社区高质量 Claude Code 插件。
- **对主项目价值**：**中**。主项目 skills/插件体系可参考官方插件结构与 marketplace 规范（.claude-plugin/marketplace.json）。
- **技术栈**：插件清单 + marketplace。
- **备注**：结构规范参考。

### context-hub-main — 版本化文档上下文中心
- **是什么**：给编码 agent 提供精选、版本化、随任务变聪明的文档（markdown 维护，chub CLI 搜索/拉取按语言版本）。
- **解决什么问题**：让 agent 读到正确版本、正确语言的库文档（防 API 幻觉 + 会话学习）。
- **对主项目价值**：**中**。主项目 context7 用法可对照其版本化文档投喂模式。
- **技术栈**：Node ≥18 CLI，npm @aisuite/chub。
- **备注**：文档上下文工程参考。

### effective-html — HTML 工件生成技能集
- **是什么**：Plannotator 的 agent skills，生成自包含 HTML 工件（线框/原型/图表/示意图），"fat artifacts + fat context"。
- **解决什么问题**：让 agent 产出高质量自包含 HTML 原型/图表。
- **对主项目价值**：**中**。主项目前端（React 面板 + Vue 落地页）若需 agent 辅助原型/图表生成可参考其技能封装。
- **技术栈**：markdown skills + 示例。
- **备注**：前端技能参考。

### cathrynlavery__diagram-design — 39 种编辑级 diagram 技能
- **是什么**：39 种编辑级图表类型（Sankey/fishbone/Wardley/kanban/用户旅程/UML/数据库 schema 等）的 agent skill，自包含 HTML+SVG，语义化模式分离行为与布局。
- **解决什么问题**：让 agent 画出"设计师不讨厌"的编辑级图表（非 Mermaid slop）。
- **对主项目价值**：**中**。主项目文档/架构图（workflow_status、docs）可由 agent 用此技能产出高质量图表。
- **技术栈**：markdown skills + prompts，兼容多个 agent 宿主。
- **备注**：文档图表质量提升直接可用。

### notfair-plugin — SEO/GEO/营销 agent skills
- **是什么**：开源 SEO/GEO/营销 skills 集（审计站点/查流量掉/分析 GA4 与 Search Console/查广告浪费/建投放计划），每个都是可读 SKILL.md + 参考 + 脚本 + evals。
- **解决什么问题**：把营销工作流变成 agent 可执行技能。
- **对主项目价值**：**低中**。主项目无营销方向，但其 SKILL.md 组织 + evals 结构与主项目 skills 库建设可借鉴。
- **技术栈**：markdown skills + scripts + evals。
- **备注**：技能工程范式参考。

### spec-ptc — 投机式程序化工具调用
- **是什么**：sPTC 技术，LLM 流式生成 REPL 调用时投机预取/排队 tool 与 sub-LLM 调用（Futures），与生成重叠执行减少阻塞。
- **解决什么问题**：agent 工具调用延迟（生成与执行串行 → 重叠）。
- **对主项目价值**：**中高**。主项目高并发异步队列 + agent 工具调用（MCP/skills）可借鉴其投机预取降低尾延迟的思路（benchmark/ 有对比）。
- **技术栈**：Python，plugins/src/tests。
- **备注**：偏研究/高级优化，L3 引入前需评估。

### skales — 私有桌面 AI（闭源冻结快照）
- **是什么**：闭源（BSL 1.1，个人免费）的本地私有 AI，仓库只是 v7 冻结快照 + 发布物，做真事不止聊天，多平台桌面。
- **解决什么问题**：本地私有、能执行实际工作的 AI 助手。
- **对主项目价值**：**低**。闭源 + 冻结快照，仅作产品形态参考（本地桌面 AI 的 UI/交互）。
- **技术栈**：仓库为冻结快照，非源码主线。
- **备注**：低价值，仅形态参考。

### claude-code-rust-master — Claude Code 的 Rust 重构版
- **是什么**：Claude Code 的完整 Rust 重构（claude-code-rs），性能/类型/内存安全 + 跨平台，含大量中文重构报告（BRIDGE_REFACTOR_REPORT、COMMAND_SYSTEM_REFACTOR 等）。
- **解决什么问题**：用 Rust 重写 AI 编程助手以获得性能与类型安全。
- **对主项目价值**：**低中**。主项目无 Rust 主线，但其重构方法论与架构分析报告（中文）对理解 Claude Code 内部机制有价值。
- **技术栈**：Rust/Cargo，中文文档丰富。
- **备注**：知识参考而非代码复用。

### crab-code-main / crab — Rust 编码 agent 与 serverless Git for 大文件
- **是什么**：crab-code 是 Rust 从零写的开源 Claude Code 替代（任意 LLM）；crab 是 Serverless Git for large files（大文件版本管理）。
- **解决什么问题**：前者——开源可配任意 LLM 的编码 agent；后者——大文件 Git 管理。
- **对主项目价值**：**低中**（两个目录不同项目）。crab-code 的 agent 工作流可参考；crab 大文件管理与主项目桌面/安装包发布（Git LFS 替代）略相关。
- **技术栈**：Rust。
- **备注**：注意 crab 与 crab-code 是不同仓库（同名目录易混淆）。

### codebuff-main — 开源 AI 编码助手（多 agent 协作）
- **是什么**：Codebuff/Freebuff，用自然语言改代码的开源编码助手，多 agent 协作理解项目并做精准修改，evals 声称 61% vs Claude Code 53%。
- **解决什么问题**：让编码 agent 多 agent 分工做精准代码修改。
- **对主项目价值**：**低中**。主项目 agent 化可参考其多 agent 协调与 evals 设计。
- **技术栈**：TS/Node，evals 齐全。
- **备注**：agent 编排范式参考。

### OpenSwarm-main — 基于 Claude Code CLI 的自主 agent 编排器
- **是什么**：编排多个 Claude Code 实例为自主 agent：接 Linear issue、Worker/Reviewer 结对产代码、报告 Discord、LanceDB 向量长期记忆、TUI。
- **解决什么问题**：自动化 agent 开发流水线（issue→代码→上报）。
- **对主项目价值**：**低中**。其 Worker/Reviewer 结对 + LanceDB 记忆模式与主项目 critic 自反思/记忆巩固同构，可对照。
- **技术栈**：npm/TS，vitest。
- **备注**：简单实用，适合抄结对模式。

### AI-company — AI 团队操作系统（Claude Code/Codex 插件）
- **是什么**：AI Team OS——Claude Code 插件（也接 Codex），任务墙/记忆/报告/Dashboard/MCP 工具，两个 harness 协同同一项目互相留言，观测层 + 邮箱唤醒。
- **解决什么问题**：把 AI 编码工具从"停下就停"变成 24h 自主团队 OS。
- **对主项目价值**：**低中**。主项目多代理编排/记忆巩固可对照其任务墙 + 观测层 + 会话唤醒设计。
- **技术栈**：Python3.11+ + Claude Code/Codex 插件 + SQLite。
- **备注**：与主项目 Python 栈接近，参考价值中。

### thepopebot-main — 24/7 自主 agent 团队机器人
- **是什么**：构建 24/7 自主 agent（单人/团队）：自动写代码、开 PR、多步任务全链路，每个动作都是可审查/撤销的 commit。
- **解决什么问题**：无人值守的 agent 团队，动作全可审计（每动作=commit）。
- **对主项目价值**：**低中**。其"每动作 commit 可撤销"的审计思路与主项目任务/审计层可互鉴。
- **技术栈**：Node + drizzle + docker，api/docs。
- **备注**：审计可撤销范式参考。

### Cas (codingagentsystem/cas) — 多 agent 编码工厂（持久记忆）
- **是什么**：Rust 多 agent 编码工厂，带持久记忆（crates 多包 + cas-cli），MIT。
- **解决什么问题**：把多 agent 编码做成带持久记忆的工厂流水线。
- **对主项目价值**：**低中**。与 ccteam/OpenSwarm 同赛道（多 agent 编排），主项目可三选一参考。
- **技术栈**：Rust/Cargo，CI/Release 齐全。
- **备注**：编排赛道重复，不必重复深挖。

### xyops — 下一代 Cronicle 作业调度平台
- **是什么**：Cronicle 的完全开源自托管继任者：作业调度、可视化工作流、服务器监控、告警、事件响应，SSO/OIDC 全免费开源。
- **解决什么问题**：把"作业调度 + 服务器监控 + 告警"一体化自托管。
- **对主项目价值**：**中**。主项目的任务队列/后台任务调度/健康监控可借鉴其可视化工作流 + 告警 + 事件响应设计。
- **技术栈**：Node（bin/docs/Dockerfile），Cronicle 迁移兼容。
- **备注**：作业编排强参考，不直接依赖。

### txtai — 一站式 AI 框架
- **是什么**：neuml 的一站式 AI 框架（embedding/RAG/向量检索/工作流/agent 等，pyproject，历史久）。
- **解决什么问题**：把 embedding、检索、RAG、workflow 放一个框架内。
- **对主项目价值**：**中**。主项目意图识别/记忆检索（intent embedding）可对照其向量检索与 workflow 实现。
- **技术栈**：Python，mkdocs 文档完备。
- **备注**：embedding/RAG 能力参考。

### nashsu__llm_wiki — 自动构建的私人知识库
- **是什么**：LLM 读你的文档自动构建结构化 wiki 并持续更新（个人知识库自动维护），含浏览器扩展 + MCP server。
- **解决什么问题**：文档→自动 wiki 的知识库自动化。
- **对主项目价值**：**中**。主项目记忆巩固/文档沉淀（OpenWolf memory、docs）可借鉴其自动 wiki + MCP 化。
- **技术栈**：TS + MCP server + 浏览器扩展。
- **备注**：知识库自动化参考。

### nashsu__llm_wiki（上文）已列——跳过。

### quackd — 给 Microduck 一个大脑（LLM 机器人 daemon）
- **是什么**：Python3.11 的机器人脑 daemon：任意 LLM 驱动 Microduck/Reachy Mini/轮式底座等小机器人，一个 .duck 文件定义行为，MCP-ready。
- **解决什么问题**：让 LLM 驱动实体机器人（统一行为定义 + MCP 接入）。
- **对主项目价值**：**低**。主项目无机器人方向；其 MCP 接入 + 行为文件范式与主项目 MCP 服务端略相关。
- **技术栈**：Python3.11+，MCP，Apache2.0。
- **备注**：低价值，趣味方向。

### sokuji — 实时双语会议语音互译
- **是什么**：实时双向语音翻译（双语会议），云或完全离线，Electron 桌面 + 浏览器扩展，AGPL-3.0。
- **解决什么问题**：双语会议实时互译，离线可跑。
- **对主项目价值**：**低中**。主项目无语音方向，但其 Electron + 离线 TTS/STT 桌面架构与主项目 Tauri 桌面 sidecar 可互鉴。
- **技术栈**：Electron + Chrome 扩展 + eval，AGPL。
- **备注**：桌面端架构参考，功能无关。

### roze→roam-code — 代码库上下文 + 静态检查工具
- **是什么**：287 命令 / 246 MCP 工具 / 28 语言，本地跑无账户无 API key，代码库上下文 + 静态检查给编码 agent。
- **解决什么问题**：给 agent 提供本地代码库上下文（不传源码/遥测）。
- **对主项目价值**：**中高**。主项目已用 codegraph/graft 图谱，此项目是"本地静态检查 + MCP 工具化"的现成方案，可对照其 MCP 工具设计与隐私（无上传）设计。
- **技术栈**：Python3.10+，PyPI，本地运行。
- **备注**：MCP 工具面强参考。

### deep-eye — AI 渗透测试工具（单文件）
- **是什么**：Python3.8+ AI 驱动的渗透测试工具（1.4.0，代号 Hanzou），多 ai_providers + config + core。
- **解决什么问题**：AI 辅助渗透测试。
- **对主项目价值**：**低**。安全工具类，仅工程参考（不接入）。
- **技术栈**：Python，多 provider 抽象。
- **备注**：低价值，安全方向已有 clearwing/redcell 更好。

### Pentaract — Telegram 云存储（极小磁盘占用）
- **是什么**：基于 Telegram 做云存储的系统（单机几 MB，Postgres 存储元数据），BT 钱包打赏。
- **解决什么问题**：免服务器存储（Telegram 兜底），极小占用。
- **对主项目价值**：**低**。主项目有 tgDrive 同类可对比；存储方案与主项目无交集。
- **技术栈**：Java/Maven/Docker/Postgres。
- **备注**：低价值。

### tgDrive — Telegram 无限容量云存储
- **是什么**：Java 基于 Telegram Bot 的云存储应用，多线程 + 优化传输策略，无限容量/速度。
- **解决什么问题**：把 Telegram 当无限云盘（免费/大容量）。
- **对主项目价值**：**低**。与主项目无关（存储类），但主项目如有 TG 通道/文件托管需求可参考。
- **技术栈**：Java/Maven/Docker。
- **备注**：低价值。

### Foundry — 开源 AI 数字公司平台
- **是什么**：开源 AI 数字公司平台，让 AI 团队像真人团队一样协作（多 agent 公司化组织），中文文档齐全。
- **解决什么问题**：AI 团队/数字公司化协作编排。
- **对主项目价值**：**低中**。主项目多 agent 编排可参考其"数字公司"组织模型。
- **技术栈**：admin/apps/client/ci-cd 多包。
- **备注**：编排范式参考，功能跨度大。

### headroom（上文已列）——已列。

### 剩余非相关项目（一句话结论）：
- **Deep-Learning-Experiments**：深度学习讲义+实验 notebook（MLP/CNN/RNN/Transformer/Mamba/GAN 等），教学资料，与主项目无关，低价值。
- **CL4R1T4S**：各大 AI 系统提示词/工具提取集（模型透明度/观测），知识资料，低价值（主项目 agent 提示词设计可瞄一眼）。
- **tracy**：知名实时纳秒级 C/C++ 性能剖析器（游戏/应用），低价值（性能工程可参考其设计，非本项目栈）。
- **MasterDnsVPN**：Go 实现的 DNS 隧道/VPN（TCP over DNS，科研向），低价值（网络协议研究，与主项目代理池无关）。
- **OpenNutriTracker**：开源热量/营养记录 App（Flutter，Android/iOS），低价值。
- **get-shit-done / get-shit-done-main**：Claude Code 等多工具的元提示/上下文工程/规格驱动开发系统（同名双目录，一个含更多文档），中价值——与主项目 CLAUDE.md/上下文工程方法论同构，可对照其"上下文腐烂"对策。
- **Elysia-Api-for-Koishi**：Koishi 的 Elysia API 适配（聊天机器人框架），低价值（与主项目网关无关，Koishi 生态）。
- **pathwaycom__arc-task-gen**：ARC-AGI-1 评测任务生成器（分布匹配），研究向，低价值。
- **jailbreak-prompts**：LLM 破甲提示词合集（非合规内容），低价值 + 高风险内容，仅记录存在。
- **The-Swarm-Corporation__AutoHedge**：自主 agent 对冲基金（Solana 交易），低价值（金融交易，与主项目无关，风险高）。
- **cowart**：Codex 的无限画布 tldraw 插件（可视化思考/标注/生图，MCP widget），低中价值（主项目前端 Canvas/生图交互可参考其 MCP widget 集成，Codex 专属）。
- **hermes-hud-main**：Hermes agent 的意识监视器（终端仪表盘），低价值（Hermes 专属，HUD 交互形态参考）。
- **Cloudflare-Faker**：Cloudflare 反爬/指纹伪造（Java + Chrome 插件），低价值（与主项目代理池/风控边缘相关，但属灰色工具）。
- **htmx**：知名前端库（HTML 直接 AJAX/CSS 过渡/WebSocket/SSE），低中价值（SSE 扩展与主项目 SSE 事件流前端消费可参考，React 面板不直接适用）。
- **PeerTube**：去中心化联邦视频托管平台（Angular/Node），低价值（视频托管与主项目无关，但大文件/转码流水线可瞄）。
- **mobilecode**：OpenCode 开源编码 agent 的多语言翻译 fork（阿拉伯语为主），低价值（OpenCode 生态，翻译变体）。
- **developer-roadmap**：知名开发者学习路线图（roadmaps.sh），低价值（资料）。
- **quackd（上文已列）**——已列。
- **kunchenguid__gnhf**：极简编码 agent（"good night, have fun"，npm gnhf），低价值（迷你 agent，与主项目无交集）。
- **cfal__garcon**：自托管编码 agent 可视化工作区（浏览器并排跑 Claude Code/Codex/Cursor/OpenCode/Pi 等并协调），中价值——与主项目桌面/Tauri 及多 agent 控制台可对照，但偏"agent 工作台"定位。
- **jlcodes99__cockpit-tools**：通用 AI IDE 账号管理工具（16 种 IDE 账号一键切换/配额监控/多实例并行），低价值（账号管理灰色工具，与主项目号池理念有共鸣但形态不同）。
- **AutoSciRub**：自动归纳学术研究 rubric 的研究框架（评价先于改进），低中价值——主项目 critic 自反思可借鉴其 rubric 归纳思想（arXiv 论文）。
- **caveman（上文已列）**——已列。

---

## 汇总：价值聚类

| 聚类 | 项目 | 主项目借鉴点 |
|------|------|------|
| agent 记忆/上下文 | claude-mem、memvid、beads、OpenViking、lossless-claw、headroom、context-mode、claude-token-optimizer/efficient/token-optimizer/caveman、context-hub、nashsu__llm_wiki | 记忆层设计、上下文压缩、token 治理 |
| agent 编排/多 agent | ccteam、gastown、beads、OpenSwarm、cas、AI-company、thepopebot、Foundry、OpenHarness、codebuff、pi | DAG/任务状态、worker-reviewer、任务墙、审计可撤销 |
| 图像/视频/音频/办公生成 | open-design、cs-board、ViMax、dsh-univer-office、Open-Pomelli、moyin-creator、webnovel-writer | 上游 provider 路由、视频 agent 化、文档操作、品牌生成 |
| 网关/API/队列/观测 | redcell、hermes-otel、xyops、Octop、roam-code、spec-ptc、txtai | 任务队列、OTel 埋点、作业调度、SSE、工具调用延迟优化 |
| 安全 | clearwing、deep-eye、redcell | 安全工程借鉴（不接入） |
| 工具/技能/效率 | Waza、effective-html、diagram-design、notfair-plugin、caveman | skills 封装、图表生成、规则集 |
| 低/无关 | Deep-Learning、CL4R1T4S、tracy、MasterDnsVPN、OpenNutriTracker、tgDrive、Pentaract、Cloudflare-Faker、jailbreak-prompts、AutoHedge、hermes-hud、htmx、PeerTube、mobilecode、developer-roadmap、gnhf、cockpit-tools、skales、crab、crab-code、codebuff、quackd、sokuji、claude-code-rust | 记录在案，一句话说明 |

**Top 5 建议优先深读**：open-design（生图网关对标）、Octop（IM/MCP/安全工程）、sirchmunk（数据→agent 工作流）、OpenViking（上下文数据库）、claude-mem（记忆层对照）。

**易混淆注意**：get-shit-done 与 get-shit-done-main（同一项目双目录）、beads 与 beads-main（同一项目双目录）、crab-code 与 crab（不同项目）、hermes-hud 与 hermes-otel（不同项目）、claude-token-optimizer / claude-token-efficient / token-optimizer（三个不同 token 项目）。
