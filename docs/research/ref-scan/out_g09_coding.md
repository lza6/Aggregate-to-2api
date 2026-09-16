# g09_coding 组扫描报告（38 目录）— 编码/CLI 工具类

主项目关注方向对齐：①agent 深度优化（黑匣子打开/教学化/小白易用/沉淀用户 skills）；②扩展场景（图片/视频/电商/PPT）；③CLI 工程规范（交互反馈/会话管理/流式输出/配置分层/错误诊断）。
本组偏③+①，多项目与主项目「agent 化」直接同构，借鉴价值较高。

---

## AITabby__codexsplit
- 定位：Codex Desktop 本地控制中心——管理第三方模型/官方 GPT 账号池/子智能体路由/GPT-Live/语音栏/本地会话。
- 技术栈：TypeScript + Node + Desktop 应用（VSCode 系生态），src/ + src_v2/。
- 亮点：
  1. **账号池「固定账号或额度加权轮询」调度**（README 03-gpt-account-pool.png，src/codex-client.ts）——与主项目号池同构，但多了「额度加权」调度视角。
  2. **Agent 路由分配规则 + 模型能力目录**分层（README 02-agent-routing.png），把「子智能体路由」做成显式可配置层。
  3. 网关三态接入（API Key / OAuth / Desktop Bridge）统一对外，保留原生模型独立运行。
- 对主项目价值：直接借鉴
- 借鉴点：号池从「轮询/健康」升级为「额度加权轮询 + 能力目录」；子智能体路由做成显式规则层（主项目 agent 化路由可参考其划分）。
- 评分：4

## AceShell
- 定位：跨平台（Go+Wails3）网络终端管理工具（SSH/串口/SFTP/RDP），内置 AI 运维智能体。
- 技术栈：Go + Wails v3 + Vue3/TS + Naive UI + xterm.js；internal/services/。
- 亮点：
  1. **AI 助手三态权限 plan/manual/auto**（internal/services/agentservice.go:30-32 agentPermPlan/Manual/Auto）——plan 只读出方案、manual 危险操作审批、auto 自动；计划模式过滤写工具（agentBuildTools:361）。
  2. **MCP 工具总线分层治理**：外接 MCP（Streamable HTTP/SSE/stdio/内置）懒连接、可挂起（mcpsuspend）、逐工具授权（mcpgrant）、全程审计（mcpaudit）；用户强中断清空挂起（agentservice.go:23）。
  3. **操作折叠行完整可追溯 + batch_execute 批量只读巡检减少往返**（agentservice.go:317 提示词显式要求）；MCP 挂起期间用户手动操作以 system 消息 drain 回上下文（:667）。
- 对主项目价值：直接借鉴（对应关注方向①agent 深度优化/黑匣子打开）
- 借鉴点：把主项目 agent 审批/工具调用升级为「plan/manual/auto 三态权限 + 每工具授权 + 审计」；操作折叠行可展开追溯（教学化/小白易用）;相近批处理工具减少 LLM 往返。
- 评分：5

## AutoCLI
- 定位：Rust 重写的 OpenCLI——一行命令抓取 55+ 站点（335 命令）数据的 agent 原生 CLI。
- 技术栈：Rust（工作区 crates/）+ Chrome 扩展 + 云端 autocli.ai。
- 亮点：
  1. **声明式 YAML pipeline 适配器**（adapters/bilibili/hot.yaml：navigate→evaluate→map→limit 步骤，注入 `${{ args.xx }}`），新增站点零代码。
  2. **AI-native discovery**：`explore` 分析站点 API、`generate --ai` 让 LLM 自动生成适配器、`cascade` 探测鉴权策略（README:59）。
  3. 浏览器 session 复用免 token 管理 + 单二进制 4.7MB 零运行时依赖。
- 对主项目价值：扩展方向参考（可直接服务电商/数据抓取扩展场景，或上游适配器化）
- 借鉴点：主项目聚合 5 家上游可借鉴「声明式 YAML 适配器 + AI 自动生成适配器」——新增上游/新场景（电商 PDP 数据）由声明式描述代替硬编码 provider。
- 评分：4

## CLI-Anything
- 定位：让任意软件（CAD/剪辑/浏览器/AD 等）变成 agent-native CLI 的框架 + CLI-Hub 分发注册表。
- 技术栈：Python + click + pytest；cli-hub/ + 60+ 软件 harness 目录。
- 亮点：
  1. **统一 harness 生命周期管理**（cli-hub/cli_hub/installer.py：针对不同 CLI 自动选 bundled/pip/uv/npm 安装策略 + preview 预览）。
  2. registry.json / public_registry.json + matrix 社区分发，skills/ 为每个软件预生成 agent 技能。
  3. 2461 测试、输出同时面向 JSON 与人类。
- 对主项目价值：扩展方向参考
- 借鉴点：「软件→CLI→skill」三件套的统一生成与分发模型，可借用其「harness + 安装策略自动选择」做主项目外挂工具的统一接入。
- 评分：3

## CLI-WeChat-Bridge-main
- 定位：桥接微信消息与本地 Codex/Claude Code/powershell 会话，远程输入+结果回流+审批同步。
- 技术栈：Node.js + Bun + TypeScript；bin/ + src/。
- 亮点：
  1. **本地会话为中心，微信仅作远程入口**——会话一致性/线程状态/审批流仍以本地为唯一权威。
  2. 审批请求经微信侧回流确认，运行状态持续同步。
- 对主项目价值：扩展方向参考
- 借鉴点：主项目 agent 的「远程/移动接入通道」可参考此「本地权威+远程镜像」模型与审批回流设计。
- 评分：2

## ClipboardHealth__groundcrew
- 定位：把任务 backlog 派发到本地交互式 AI 编码 agent，一个任务一个 git worktree，默认沙箱。
- 技术栈：Node/TS + tmux/cmux + Docker Sandbox/Safehouse；src/lib/ 模块化。
- 亮点：
  1. **one worktree per task + 默认沙箱**（Docker/Safehouse），`none` 是显式逃生舱——并行安全关键设计。
  2. **可插拔任务源**（Linear 默认/Jira/本地文件，task-sources/）+ 多 agent preset（claude/codex/cursor/pi）。
  3. `crew doctor` 前置依赖检查；run/dry-run/--watch 编排器语义。
- 对主项目价值：扩展方向参考
- 借鉴点：主项目 DAG 编排可借鉴「任务→隔离工作区→独立分支/可恢复」的幂等派发模型与健康检查引导（小白易用）。
- 评分：4

## Codex-CLI-Compact-main
- 定位：GrapeRoot——为 AI 编码助手建语义代码图谱，预加载相关文件进 prompt，降 30-45% token。
- 技术栈：Python + 语义图 + 本地/云端双图；bin/dg(dgc)（Windows ps1/cmd 一并提供）。
- 亮点：
  1. **双图（语义图+缓存感知）选文件**：先扫项目建符号/导入图→问题→找相关文件→打包上下文，token 节省可量化（$0.46→$0.27/次）。
  2. 跨会话图记忆：记住哪些文件被读/改/查，每轮越来越省（compounding）。
- 对主项目价值：直接借鉴
- 借鉴点：主项目已有 intent embedding/codegraph，可借鉴「图选文件 + token 节省量化报告 + 跨会话记忆复用」，把上下文工程做成可观测指标。
- 评分：4

## Fincept-Corporation__FinceptTerminal
- 定位：空目录（FinceptTerminal 的上游公司名/Fork 重复项），无源码内容。
- 技术栈：无。
- 亮点：无。
- 对主项目价值：无价值（重复项）
- 借鉴点：无。
- 评分：0

## FinceptTerminal
- 定位：机构级金融智能终端（C++20/Qt6 桌面 + 内嵌 Python 3.11 分析，单二进制）。
- 技术栈：C++20 + Qt6 + 内嵌 Python；fincept-qt/。
- 亮点：
  1. 单二进制桌面终端捆绑数据连接/AI 自动化/交易，无 Electron。
  2. Node Editor 可视化 + 数据连接器体系。
- 对主项目价值：局部借鉴
- 借鉴点：主项目 Tauri sidecar 已是「单桌面壳」，可参考其「内嵌分析运行时」的打包哲学；领域（金融）不直接相关。
- 评分：2

## FunClip
- 定位：达摩院开源的本地视频剪辑工具——ASR 转写→选中文本/说话人→自动裁剪。
- 技术栈：Python + FunASR(Paraformer) + CAM++ 说话人 + Gradio；funclip/。
- 亮点：
  1. **时间戳/热词定制/说话人分离三位一体驱动剪辑**——多段自由剪辑+SRT 字幕输出。
  2. LLM 智能剪辑路径（新方向）。
- 对主项目价值：扩展方向参考（对应关注方向②视频场景）
- 借鉴点：主项目扩展「视频」能力可借鉴「ASR→时间戳→段落剪辑」产品链路与 Gradio 快速落地 UI。
- 评分：3

## OfficeCLI
- 定位：面向 AI agent 的 Office 套件 CLI——Word/Excel/PPT 一键可控，单二进制无需安装 Office。
- 技术栈：Go（src/officecli）+ SDK（node/python）+ plugins/；skills/ 每场景一套。
- 亮点：
  1. **内置 HTML 渲染引擎给 AI"眼睛"，render → look → fix 闭环**（README:9,259；view html / view screenshot / watch 三模式，无头浏览器出 PNG 供多模态 agent 读）——标题溢出、形状重叠这类 DOM 看不出的问题可被看见修复。
  2. **结构化 selector 寻址语法**（$Sheet:A1、/slide[N]/shape[@name=Foo] 路径）——精准局部改文档。
  3. 每产品场景（pitch-deck/financial-model/academic-paper/data-dashboard 等）预置 skill。
- 对主项目价值：直接借鉴（对应关注方向②PPT/电商扩展场景 + 生成物可视回环）
- 借鉴点：①主项目生成物（电商主图/PPT/视频）加「渲染→截图→LLM 自检→修复」闭环，把黑盒生成变可自查；②selector 路径语法用于局部编辑；③按场景拆 skill。
- 评分：5

## Tencent__teamai-cli
- 定位：腾讯开源——让团队在 Claude Code/Codex/Cursor/OpenCode 等 agent 之间统一管理 skills/rules/MCP/知识。
- 技术栈：TypeScript + tsup/vitest；src/ 六大引擎区。
- 亮点：
  1. **git repo 作为共享知识底座**：`teamai init` 拉取，多 git 平台 provider 适配（src/providers/：GitHub/GitLab/GitCode/CNB/TGit 统一 GitProvider 接口）+ 双向 push/pull。
  2. **技能健康度评分 + 推荐/淘汰**（src/skill-health.ts calculateSkillHealth：按使用次数/最近使用衰减打分）+ skill-recommend.ts。
  3. **wiki 知识图引擎 + 召回评分**（src/wiki-engine/, recall.ts IDF 基线+autoUpvote），增强 code-knowledge-recall。
- 对主项目价值：直接借鉴（对应关注方向①沉淀用户 skills）
- 借鉴点：skills 的「共享仓库派生/多源适配/健康度评分淘汰/召回投票」整套工程化——主项目沉淀用户 skills 的直接模板；codebase 知识层参考其 wiki 图引擎。
- 评分：5

## ai-codex-master
- 定位：一键生成紧凑代码库索引（5 个小文件替代每次 50K+ token 的探索）。
- 技术栈：TypeScript（npx ai-codex 自动探测框架）。
- 亮点：
  1. 按框架自动探测，输出 routes.md/pages.md/functions.md/schema.md 等结构模板化索引。
- 对主项目价值：局部借鉴
- 借鉴点：为接入主项目的 agent 生成「能力索引/接入指南」（谁有权限、多少号池、路由记录在哪），降低首次接入学习成本。
- 评分：3

## aider
- 定位：终端 AI 结对编程标杆，连接任意 LLM 对现有代码库做有 git 版本管理的修改。
- 技术栈：Python + tree-sitter + grep_ast + diskcache；aider/repomap.py, coders/。
- 亮点：
  1. **RepoMap：tree-sitter AST 提取（定义/引用 tag）建图，PageRank 个性化排序**（repomap.py get_ranked_tags:365——正在聊的文件/被提及文件加权 personalization），把「哪些文件进上下文」做成算法而非启发式；SQLite 缓存版本化。
  2. 多 coder 架构按任务划分（architect/ask/editblock/patch/editor_* 等十余种 coder）与 prompts 分离。
  3. 自动 git 提交/回滚治理（简洁 commit, undo 语义）。
- 对主项目价值：直接借鉴
- 借鉴点：主项目 agent 的「工具/文件选择」可引入 AST+PageRank 个性化排序（替代纯 embedding 或关键词）；上下文缓存/多角色 coder 拆分为模板。
- 评分：5

## autoclip
- 定位：AI 视频智能切片系统（YouTube/B站 下载→AI 分析→切片→合集）。
- 技术栈：Python + FastAPI + Celery + Redis + React/TS + Ant Design（前后端分离）。
- 亮点：
  1. Celery 异步任务队列 + WebSocket 实时进度反馈。
  2. 通义千问大模型视频内容理解 + 智能合集。
- 对主项目价值：扩展方向参考（视频场景）
- 借鉴点：主项目视频扩展可参考其「任务队列+WebSocket 进度」组合（主项目已有 SSE 队列，架构同款）；本体较个人项目，未深挖价值。
- 评分：2

## cli-main
- 定位：MiniMax 官方 CLI（mmx）——为 agent/终端生成文本/图像/视频/语音/音乐全模态。
- 技术栈：TypeScript + Node；src/client($stream) + polling/ + output/ 分层。
- 亮点：
  1. **统一异步任务轮询**（src/polling/poll.ts：deadline 超时 + spinner + 递增超时提示 + 状态查询引导）——视频/生图等慢任务的 CLI 标准范式。
  2. **输出层分层**（output/：json/text/formatter/progress/status-bar/quota-table），同一命令多种机器可读输出。
  3. 双区域（Global/CN）远端无感切换。
- 对主项目价值：直接借鉴
- 借鉴点：主项目生图/视频异步队列的「CLI/对外接口化」：轮询语义（超时/幂等/状态查询）与 quota-table 用量展示；输出格式分层（agent vs 人）。
- 评分：4

## clickclickclick
- 定位：用任意 LLM（本地/远程）驱动自主安卓与电脑操作框架。
- 技术栈：Python + Gradio + Ollama/Gemini/GPT；clickclickclick/{planner,finder,executor}。
- 亮点：
  1. **Planner/Finder 双角色分工**：（planner 规划下一步动作 vs finder 定位 UI 元素），且两者可配不同模型分别调优（utils.py get_planner/get_finder 工厂）。
  2. 截图+视觉反馈循环，image-quality 参数权衡成本。
- 对主项目价值：扩展方向参考
- 借鉴点：agent 视觉操作/UI 自动化场景的「规划/定位双模型拆分 + 截图反馈」架构。
- 评分：3

## clickgraph
- 定位：Rust 高性能 ClickHouse 图查询引擎，Cypher/Bolt（Neo4j）兼容。
- 技术栈：Rust + chdb（嵌入式）/ClickHouse；clickgraph-* 多语言绑定（Go/Python/FFI）。
- 亮点：
  1. 无状态 Cypher→ClickHouse SQL 翻译，嵌入式读写模式（GraphRAG 本地建图查询无需服务器）。
  2. **cg CLI agentic**：`cg nl`（NL→Cypher)、`cg schema discover`（LLM 辅助从活仓库生成 schema YAML）+ 可发布 agent skills（/cypher /graph-schema /schema-discover）。
- 对主项目价值：局部借鉴
- 借鉴点：图形数据层与 LLM 辅助 schema 生成思路（主项目 codegraph 类能力可参考其 CLI 形态）；领域差异大，分值有限。
- 评分：2

## cline
- 定位：开源编码 agent（IDE 扩展 + CLI + 桌面三端）。
- 技术栈：TypeScript + Bun monorepo；apps/{cli,vscode,desktop} + sdk/packages/core。
- 亮点：
  1. **core SDK 化可嵌入**（sdk/packages/core/src ClineCore.ts：session/tasks/settings/hub/cron 分层），多端共用逻辑单点。
  2. CLI headless 模式面向 CI/CD 与脚本。
- 对主项目价值：局部借鉴
- 借鉴点：核心逻辑抽 SDK 多端复用（主项目 API/管理面板/桌面可参考）；headless 脚本化模式。
- 评分：3

## codex-chatgpt-web
- 定位：把本地 Codex 任务通过 Responses+SSE 桥接到浏览器登录的 ChatGPT Web 会话。
- 技术栈：TypeScript + Bun + Playwright（嵌入式浏览器）；src/{bridge,adapters,launcher-browser-host,tunnel,usage}。
- 亮点：
  1. **协议桥接保原生 harness**（src/bridge.ts + native-passthrough.ts）：只转发任务上下文/图片，Codex 保留原生任务/上下文/界面；适配器化（src/adapters/）。
  2. stall-timeout 超时护栏 + tunnel + 桌面 launcher（PWA 免安装）工程完整。
- 对主项目价值：局部借鉴
- 借鉴点：主项目若要做「免登录/无头上游接入」可参考协议桥+超时护栏+launcher 分发；ChatGPT Web 上游非主项目目标。
- 评分：3

## codex-host
- 定位：在 Codex Desktop 中运行 Pi/Claude Code/OpenCode/Grok 等 harness，跨 agent 协作。
- 技术栈：Rust（crates/launcher, updater）+ TS 工作区（packages/harness-adapter, harness-broker, harness-discovery）monorepo, openspec。
- 亮点：
  1. **harness 插件化承载**：adapter/broker/discovery/mapping-store 分层，新 agent 插拔即用；api 同一桌面窗口多 thread 协作。
  2. 远程连接 harness（远程驱动）。
- 对主项目价值：扩展方向参考
- 借鉴点：桌面多 agent 统一承载与远程接入的适配层设计（主项目 Tauri sidecar 可扩展）。
- 评分：3

## codex-keysmith
- 定位：先预览、再写入、可撤销的 Codex 全局指令部署工具。
- 技术栈：Python（codex-instruct.py + fixture_packs + tests）+ Desktop Beta。
- 亮点：
  1. **dry-run 默认**：部署/卸载/中断恢复都先预览，无 `--yes` 绝不写盘（codex-instruct.py:12,20）。
  2. **隔离式回滚**：hooks.json 先备份为 .disabled+时间戳，`--restore-hooks` 一键恢复；卸载前快照 manifest-restore。
  3. 双语文案统一、SHA256SUMS 校验流（防 curl|bash 供应链）。
- 对主项目价值：直接借鉴（配置/指令/规则部署的安全工程模板）
- 借鉴点：主项目「预算门禁/规则/技能包」下发类操作套用「预览→确认→隔离备份→可回滚」模式；发布资产校验。
- 评分：4

## codex-main
- 定位：OpenAI Codex CLI（官方开源，Rust 实现）。
- 技术栈：Rust（codex-rs/core）+ Bazel monorepo。
- 亮点：
  1. **工具系统工程化**（core/src/tools/）：registry/router/orchestrator/parallel/runtimes/sandboxing（含 windows_sandbox 读取授权清单）+ network_approval 网络审批。
  2. **turn_diff_tracker 变更追踪 + tasks/undo**（core/src/tasks/undo.rs）——agent 修改可精确差异+回滚。
  3. skills.rs 原生技能加载 + compact（上下文压缩）分层。
- 对主项目价值：直接借鉴
- 借鉴点：主项目 agent 工具层参照其「注册/路由/并行/沙箱/网络审批」；DAG 任务加「差异追踪+undo」回滚语义；技能加载范式。
- 评分：5

## codexloom
- 定位：Codex 长跑 agent 的工作环境——给 agent 持久身份/职责，组织成受治理的团队，对外经 Interface Agent 交付。
- 技术栈：Go（cmd/loom-*, internal/）+ gateway/（Feishu/Slack/Parall 协议 mjs）。
- 亮点：
  1. **持久身份 + Profile + 单一主 Thread** 的职责固化模型（docs/owner-guide.zh-CN.md：Profile 是可检验假设，长期责任才更新）——agent 从「一次性会话」升级为「可续跑的领域成员」。
  2. **Interface Agent 对外交付**：外部协作者经 Feishu/Slack/Parall 网关与治理边界（身份/会话/授权/信息四边界）协作，内部 Domain Agent 不受干扰。
  3. WebUI/Desktop/Mobile 三端同 Agent 续跑（internal/webui, launchagent, rollout）。
- 对主项目价值：直接借鉴（对应关注方向①agent 深度优化 + 对外交付）
- 借鉴点：主项目 agent「持久身份+职责 Profile」固化模型与「接口 Agent + 多 IM 网关」对外通道（微信/钉钉接入）；治理边界显式声明。
- 评分：5

## coolqoo__1click-ecom-detailpage
- 定位：电商主图+详情页（PDP）一键生成 skill——只给「卖什么+受众」自动出完整可上架图集。
- 技术栈：Python + SKILL.md（OpenClaw/Hermes/Codex/Claude Code 全兼容）+ scripts/。
- 亮点：
  1. **端到端一键**：5 主图 + 7-9 详情图全自动交付，含文案/版式规划。
  2. **跨图视觉一致性对齐**（统一风格+主体，消除拼贴感）——电商图集核心痛点。
  3. 转化驱动文案 + 结构化版式（Amazon 美式文案内置）。
- 对主项目价值：直接借鉴（对应关注方向②电商场景）
- 借鉴点：主项目电商扩展可直接移植其「图像集一致性保持」与「一句话→全套图」的 skill 编排链；验证于多主流 agent 框架兼容写法。
- 评分：4

## donvito__codex-astra-luna-orchestrator
- 定位：Codex 多模型编排配置——Astra 做根/编排+评审，Luna 做执行子代理。
- 技术栈：Codex config as code（.codex/config.toml + agents/*.toml + skills/）。
- 亮点：
  1. **角色-模型-推理档显式映射表**（orchestrator/execution/reviewer 各配模型与 reasoning 档）——一份表看懂整盘编排策略。
  2. 按套餐（Plus/Pro）双配置 + token 用量脚本。
- 对主项目价值：局部借鉴
- 借鉴点：主项目 MAB-EWMA 路由可把「角色-模型-推理档」做成显式配置面；并发子代理上限显式化。
- 评分：2

## googleworkspace__cli
- 定位：gws——一个 CLI 覆盖 Google Workspace 全部 API（Drive/Gmail/Calendar...），人为与 agent 双用。
- 技术栈：Rust（crates/google-workspace(-cli)）+ npm 分发。
- 亮点：
  1. **动态 schema 驱动命令面**：不维护静态命令列表，运行时读 Google Discovery Service 自动建出整个 CLI（main.rs:17-19, discovery.rs）——Google 加接口/方法即自动支持。
  2. **40+ agent skills 随命令自动生成**（generate_skills.rs）+ 结构化 JSON 输出 + 明确 exit codes。
  3. **终端输出安全清洗**（output.rs sanitize_for_terminal：剥控制字符/双向 Unicode 欺骗/零宽字符，尊重 NO_COLOR 与非 TTY）。
- 对主项目价值：直接借鉴
- 借鉴点：①上游 API「schema 自动同步生成适配」——主项目 5 家图像上游可用 OpenAPI/Discovery 动态生成统一 provider；②生成物进终端前的转义/注入清洗（主项目前端渲染同理）；③exit code 约定。
- 评分：5

## grok-cli-main
- 定位：Grok 编码 agent CLI——OpenTUI + 默认子代理 + Telegram 远程控制。
- 技术栈：TypeScript + Bun + OpenTUI。
- 亮点：
  1. **Telegram pair 一次远程控制**（src/telegram/pairing.ts + headless-bridge + turn-coordinator）：配对后手机驱动本地 agent，音频/文件/图片通道完整。
  2. 子代理默认开 + 规划(plan.ts) + 调度(schedule.ts) 会话 UI。
  3. `grok update/uninstall --dry-run/--keep-config` 自管理。
- 对主项目价值：局部借鉴
- 借鉴点：远程配对（微信/Telegram 驱动主项目 agent）实现细节；子代理展示与计划 UI。
- 评分：3

## guardian-cli
- 定位：企业级 AI 渗透测试自动化平台（多 provider + 多角色 agent + RAG 知识库 + 证据捕获）。
- 技术栈：Python 3.11 + black + pytest；ai/, core/ 分层。
- 亮点：
  1. **三角色辩论判定 triage**（core/agents/debate_triage.py：RED/BLUE 针锋相对 + JUDGE 裁决并调严重级）——**只对 analyst 标为 MEDIUM 置信度的发现触发**，自信判定走廉价路径跳过辩论，token 成本有界；实测 F1 ≥ 单 agent +5pp。
  2. **Judge 模型路由**：`think_deeply(judge_model=...)` 大模型想、小模型判，swap-and-restore，~10x 成本下降。
  3. **离线学习工具排序器**（core/learners/tool_ranker.py：predict_with_fallback 低置信度 abstain 回退 LLM 选择器）+ RAG（SQLite+FTS5 查 CVE，防幻觉引用）记忆（core/memory.py 全程 token/决策账本）。
- 对主项目价值：直接借鉴（对应关注方向①critic 自反思升级）
- 借鉴点：把主项目 critic 自反思升级为「红蓝辩论 + 小模型判定 + 仅模糊项触发」的争议裁决协议；工具选择排序器（低置信度回退）+ 成本账本；RAG 防幻觉引用。
- 评分：5

## mobilecli
- 定位：统一 iOS/Android 设备、模拟器、应用管理 CLI。
- 技术栈：Go + adb + 苹果私有协议 + RPC；devices/, rpc/, daemon/。
- 亮点：
  1. **后台常驻 daemon 跨调用保活**（daemon/：设备发现只付一次代价，30min 空闲自动退出，自动重启旧版本 daemon）——CLI 调用无状态、daemon 有状态的分层设计经典范式。
  2. **CLI/daemon/HTTP server 三层共享一组设备**：JSON-RPC over unix socket + OpenRPC 规格，桌面/脚本/网页同一后端。
  3. webview 检查/日志流/位置伪造等深度设备能力。
- 对主项目价值：局部借鉴
- 借鉴点：主项目 Tauri sidecar 可参考「守护进程保活 + JSON-RPC 单线协议 + 多前端共后端」架构；Windows 路径实现（process_windows.go）。
- 评分：3

## mvanhorn__cli-printing-press
- 定位：自动"打印"对 agent 极友好的 CLI——读官方文档/嗅探无文档 API，产出一套 token 高效 CLI + skill + MCP。
- 技术栈：Go + Claude Code skills + MCP。
- 亮点：
  1. **agent 友好 CLI 范式**：本地 SQLite 镜像 + compound 命令（一次调用给全答案，试验证多源拼接）+ agent-native flags——减少 agent 往返与 token（肌肉记忆原则）。
  2. 每条 CLI 同时产出 skill + MCP server 三件套。
- 对主项目价值：局部借鉴
- 借鉴点：agent 工具设计的「compound 命令减少往返」与「CLI+skill+MCP 三件套」交付形态（主项目 MCP 服务端五个工具可包装为同一范式）。
- 评分：3

## nicobailon__pi-interactive-shell
- 定位：Pi 编码 agent 的交互式 CLI 扩展——agent 在可观测 TUI 覆盖层中自主运行交互程序，用户可随时接管。
- 技术栈：TypeScript + PTY（zigpty 免 node-gyp）；index.ts + pty-session.ts + session-manager.ts。
- 亮点：
  1. **稳定 sessionId + 四档异步模式**（Interactive/Hands-free/Dispatch/Monitor，README 模式表）：从人机共驾到后台值守全覆盖，agent 按需选档。
  2. **可观测覆盖层 + 随时接管**：用户实时看 agent 操作，输入任意键即接管（user-takeover 状态机，session-manager.ts:13）。
  3. PTY 会话管理器（WriteQueue 背压、sessionId 生成/释放）工程完整。
- 对主项目价值：直接借鉴（对应关注方向①黑匣子打开/教学化）
- 借鉴点：交互式子进程的「可观测覆盖层 + 用户接管 + 四档阻塞语义」——让主项目 agent 跑 ssh/db shell/git 时黑匣子打开、小白可看可控。
- 评分：4

## opencode-ai__opencode
- 定位：Go 终端 AI 编码助手（已归档，迁往 Crush）。
- 技术栈：Go + Bubble Tea TUI + SQLite + LSP；internal/{tui,session,permission,db}。
- 亮点：
  1. Permission service 请求/授权/持久化分层（permission.go：GrantPersistant/Grant/Deny）。
  2. SQLite 会话持久 + LSP 集成 + 文件变更追踪。
- 对主项目价值：局部借鉴
- 借鉴点：权限服务状态机与 TUI 会话；已归档，参考价值较有限。
- 评分：2

## opencode-magic-context-master
- 定位：缓存感知无限上下文 + 跨会话记忆 + 后台历史压缩的 OpenCode 插件。
- 技术栈：TypeScript（packages/plugin + dashboard/ 桌面应用）。
- 亮点：
  1. **缓存感知压缩**：后台 historian 用独立模型压缩旧对话，全程避免破坏缓存前缀、延迟到无害时机执行——cost 与质量兼得。
  2. **dreamer 夜跑整合**：把记忆去重/提升为规范事实并维护代码库文档；**user memories 提炼行为画像**（沟通风格/专长/评审重点）跨会话注入 `<user-profile>`。
  3. sidekick 按需增强 prompt + TUI 侧栏实时展示 token/上下文/记忆状态（教学化/可视化）。
- 对主项目价值：直接借鉴（对应关注方向①记忆巩固 + 教学化）
- 借鉴点：主项目记忆 L1-L3 巩固层升级为「缓存感知压缩 + 夜间整合 + 用户画像抽取 + 可视化侧栏」；实验开关模式（experimental.*）。
- 评分：4

## pilot-shell-main
- 定位：Claude Code 的专业开发环境——spec 驱动开发 + 质量门禁 + 上下文工程 + 技能沉淀。
- 技术栈：Python（pilot/）+ Claude Code hooks/技能；pilot/{hooks,rules,skills,agents}。
- 亮点：
  1. **spec 驱动闭环当质量门槛**：/spec 规划→实现→验证，spec_plan_validator / spec_verify_validator / spec_stop_guard hooks 把「计划有误/未验证就停」设成硬门禁而非建议；/prd 脑暴转明确需求。
  2. hooks/ 强制 lint/format/typecheck/TDD 每次编辑即 gate；pre_compact/post_compact 上下文管理。
  3. **/create-skill 捕获工作流可复用** + /setup-rules 按项目生成规则；语义搜索 + 代码知识图谱。
- 对主项目价值：直接借鉴（对应关注方向①教学化/小白易用 + 沉淀 skills）
- 借鉴点：spec 驱动「PRD→计划→实现→验证」funnel 与质量 hooks 门禁化（主项目 DAG + critic 可套此 execute 链）；/create-skill 式技能沉淀入口 —— 正是主项目「沉淀用户 skills」的产品化形态。
- 评分：4

## rorkai__App-Store-Connect-CLI
- 定位：asc——轻量可脚本化 Apple 上架流程 CLI（TestFlight/元数据/签名）。
- 技术栈：Go + GitHub Actions；commands/, concepts/, configuration/ 文档化。
- 亮点：
  1. **skills 安装锁定 + 可回滚**：`asc install-skills` 检出 review commit 拷贝 25 skills 到全局目录，校验每个文件、失败整包回滚、外部不改锁条目。
  2. 结构化 table/json 多格式输出 + 安装脚本自身有单测（install_script_test.go）。
  3. 隐私/遥测透明化文档。
- 对主项目价值：局部借鉴
- 借鉴点：主项目 skills 包「安装锁定校验回滚」工程；CLI 输出格式与安装器测试。
- 评分：3

## teamai-cli
- 定位：Tencent__teamai-cli 的重复目录（同名镜像）。
- 技术栈：同 Tencent__teamai-cli。
- 亮点：同 Tencent__teamai-cli。
- 对主项目价值：无独立价值（重复项）
- 借鉴点：见 Tencent__teamai-cli。
- 评分：1

## vibepod-cli
- 定位：vp——统一 CLI 在 Docker/Podman 隔离容器中运行各编码 agent（Claude/Codex/Gemini/Copilot...），零配置。
- 技术栈：Python（src/vibepod/）+ Docker/Podman + ACP。
- 亮点：
  1. **零配置隔离运行**（vp run <agent>）+ 内容寻址 overlay 层（.vibepod/overlay/ Dockerfile 片段→每项目每 agent 一个缓存镜像）。
  2. **本地分析面板 + Agent 对比基准**（HTTP 流量/用量/响应延迟侧写），隐私本地化。
  3. 支持 ACP（Agent Client Protocol）适配器，容器化 agent 可直接出现在 Zed 等编辑器 AI 面板。
- 对主项目价值：局部借鉴
- 借鉴点：agent 隔离运行 + 覆盖层定制 + 本地对比观测面板（主项目桌面/CI 中隔离跑 agent 的评估基建）。
- 评分：3

---

## 本组汇总：Top3 最值得主项目借鉴项

1. **AceShell — AI 助手「三态权限 + MCP 逐工具授权/挂起/审计 + 操作折叠可追溯 + batch_execute 批处理」**（internal/services/agentservice.go）
   直接命中关注方向①「黑匣子打开/教学化/小白易用」：主项目 agent 审批升级为 plan/manual/auto 三态、工具级授权与审计、每次操作折叠行可展开复盘、「强中断清空挂起+手动操作 drain 回上下文」的会话一致性。这是把「agent 行为变可见可变」最完整的实践。

2. **guardian-cli — 三角色辩论裁决 + Judge 小模型判定 + 模糊项才触发的成本有界 critic**（core/agents/debate_triage.py + core/learners/tool_ranker.py）
   主项目已有 critic 自反思（V13），可升级为「红/蓝辩论 + 独立小模型裁决」提升判定质量（F1+5pp）、把裁决成本降 ~10x，并学习「低置信度 abstain 回退 LLM」与 RAG 防幻觉引用——agent 质量与成本兼得的直接模板。

3. **OfficeCLI — 生成物「render → look → fix」可视回环**（README:259 + view html/screenshot/watch）
   直接命中关注方向②（电商/PPT 扩展）：内置渲染引擎把生成文档渲染成 HTML/PNG 给多模态 LLM 自检，解决「DOM 看不出标题溢出/形状重叠」的黑盒生成痛点；配套结构化 selector 路径语法与按场景拆 skill。主项目电商主图/PPT/视频生成可整套移植此「生成即自检」闭环。

荣誉推荐（并列竞争 Top3）：
- **Tencent__teamai-cli**：skills/rules/MCP「git 共享底座 + 多源适配 + 健康度评分淘汰 + 召回投票」——沉淀用户 skills 的产品化路径。
- **codexloom**：agent 持久身份/Profile/接口 Agent + Feishu/Slack 网关注入——agent「可持续角色化」与对外交付架构。
- **aider / codex-main**：AST+PageRank 上下文选择；工具注册/并行/沙箱/undo 差异追踪。