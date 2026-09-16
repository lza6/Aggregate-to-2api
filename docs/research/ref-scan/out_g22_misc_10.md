# g22_misc_10 扫描报告（80 目录）

> 扫描方式：`ls` + README 前 30-50 行识别真实功能；疑似有价值项目深入确认。
> 价值口径：①agent/skills/mcp/context 工程 ②图片/视频/音频生成、电商、PPT/办公文档、多模态 ③网关/API/队列/任务编排 ④桌面/浏览器/自动化 ⑤工程规范/交互/性能/安全。无关→低价值但一句话说明是什么。

---

## 高价值 / 疑似高价值（完整格式）

### 33. diegosouzapw__OmniRoute — ⭐ AI 网关直接对标
- **是什么**：免费 AI 网关「OmniRoute」——356 providers（150+ 免费层，~1.47B 免费 token/月），一个 OpenAI 兼容端点，19 种路由策略 + 自动回退，RTK+Caveman 双层压缩省 15-95% token，免费层目录库。
- **对主项目价值**：与「听风AI」核心场景（聚合多上游、统一 /v1 接口、路由引擎）**高度对标**。主项目是 MAB-EWMA 单策略路由；OmniRoute 的 19 策略库、免费层配额/池去重记账、token 压缩（RTK/Caveman）思路可直接迁移到主项目路由引擎与预算门禁。
- **技术栈**：TypeScript（@omniroute/ 工作区 + Bun 可选 Docker）。
- **亮点可抄**：免费层目录→配额预算映射、多策略路由打分、压缩中间层。
- **结论**：✅ 重点精读 `config/` 路由策略与 free-tiers 记账模块。

### 37. yaojingang__TokHub — ⭐ API 网关 + 监控
- **是什么**：面向 AI API 服务的开源监控、推荐运营 + OpenAI 兼容网关（Go）：公开状态页、供应商排行、用户工作区、官方账号本地连接、分层探测、用量计量、告警审计、自托管。
- **对主项目价值**：主项目已含"账号池/邮箱池自动化 + /v1 网关 + 管理面板"，TokHub 补齐的是**上游健康分层探测、用量计量与告警审计**、状态页；三层连接（官方 API/官方账号本地/本机实验室）的"密文擦除+托管通道禁用"思路与主项目号池治理可互参。
- **技术栈**：Go + 浏览器扩展 + Docker。
- **亮点可抄**：provider 探测矩阵、用量计量/配额告警、连接凭据生命周期。
- **结论**：✅ 中高价值，重点看 `internal/` 探测与 `db/` 计量模型。

### 45. Puppetmaster — ⭐ 多步任务调度 + 持久状态
- **是什么**：把多步工程工作流跑在已有 agent 工具（Cursor/Claude Code/Codex/API）之上的调度器：独立 worker、任务路由到可用模型、**SQLite 持久化 typed results**，可断点续跑；含成本路由 + durable retries（SWE-bench 实测省 29% 成本）。
- **对主项目价值**：主项目 agent 化已有"高并发异步队列/DAG 续跑"，Puppetmaster 提供**跨 agent 工具（非仅本地代码）的 worker 编排**与 SQLite 持久 job 续跑范式，与主项目 `queue_store`/审批持久化互补。
- **技术栈**：Python/PyPI。
- **亮点可抄**：typed result 存储、cost-routing 决策、resume 语义。
- **结论**：✅ 中高价值，任务编排层精读 `puppetmaster/` + `bench/`。

### 7. LongHorizon-Harness — ⭐ 长时循环工程
- **是什么**：给 Claude Code/Codex/OpenCode/DeepSeek Harness 的**循环工程系统**：一次给目标，跨桌面+终端连续工作数十小时；plan→act→verify→checkpoint/recover→repeat，用新 context 执行每个有界步骤并校验真实结果；带 benchmark（WeaveBench/OSWorld 2.0）。
- **对主项目价值**：主项目有 DAG 编排 + 续跑，但没有**跨工具长时自动循环 + 失败证据回喂下一轮**的闭环；此项目的 checkpoint/recover 与"上下文刷新后继续"机制对主项目 agent 长任务鲁棒性直接可参考。
- **技术栈**：Python ≥3.10 + 前端。
- **亮点可抄**：verify→checkpoint 决策、失败证据结构化回喂、context 刷新续跑。
- **结论**：✅ 中高价值，`src/` 循环内核精读。

### 19. ownmem — ⭐ Git-native agent 记忆
- **是什么**：Git 原生的 AI 编码代理记忆系统（Claude Code/Codex/Cursor/Gemini CLI 通用）：`.ownmem/` 内可读 Markdown 记忆随代码走（clone/review/rollback），**确定性本地召回**（同 query+config+snapshot 必同排序，默认零模型/网络调用），证据治理、安全自改进。
- **对主项目价值**：主项目记忆靠 `.wolf/` + MEMORY.md（OpenWolf 协议），召回靠人工/嵌入。ownmem 的**确定性召回 + 记忆即代码（可 review/回滚）+ 多 agent 共享单一事实源**正是主项目记忆巩固模块可升级的方向。
- **技术栈**：Node ≥20.6 / npm。
- **亮点可抄**：召回排序的确定性实现、记忆文件格式、跨宿主共享。
- **结论**：✅ 中高价值，`lib/` 召回与 `schemas/` 精读。

### 26. honcho-main — ⭐ 记忆库（stateful agents）
- **是什么**：开源记忆库 + managed service：给任意模型/框架的 agent 构建与维护**持续学习状态**（user/agent/group/idea 等实体随时间演化），支持 MCP、多 SDK。
- **对主项目价值**：与 ownmem 互补——honcho 解决"实体随时间变化的记忆"（持续学习），主项目 agent 会话/用户记忆可借其实体模型设计；MCP + SDK 多语言暴露也匹配主项目 MCP 服务端。
- **技术栈**：Python/FastAPI 式后端 + 多 SDK + alembic 迁移。
- **亮点可抄**：实体演化建模、记忆存取 API、migrations 组织。
- **结论****：** 中价值偏上；记忆实体层可参考，但引入成本需评估。

### 20. pi-shadow-mind — ⭐ 影子思维并行 critic
- **是什么**：给 Pi 的"影子思维"——主 agent 干活时并行跑多个持久专业代理（架构审查/项目接地/文档维护/完成审查），各自独立决定何时审查/行动，可只读汇报或并行工作，**构建与审查同一遍**。
- **对主项目价值**：主项目已有 critic 自反思（builder/critic/evaluator 三角色），pi-shadow-mind 的**"持久认知角色 + 独立触发时机 + 可写并行工作线"**模型是 critic 机制升级参考：把一次性审查变成常驻旁路代理。
- **技术栈**：TypeScript/Node。
- **亮点可抄**：角色职责定义、只读/可写双模式、完成前独立验证触发。
- **结论**：✅ 中高价值，`src/` 角色与调度机制精读。

### 29. Cotal-AI__Cotal — ⭐ agent 分布式拓扑标准
- **是什么**：AI agent 的开放 pub/sub 标准（"the open pub/sub standard for AI agents"）：任意 agent 拓扑——DAG/图/群 swarm/监督树/流水线，跨 Claude Code/OpenCode/Hermes/Codex，分布式编程 for agents。
- **对主项目价值**：主项目 agent 编排目前是内部 DAG 实现；Cotal 给出**协议化/标准化的 agent 间 pub/sub 通信**与拓扑声明方式，若主项目要开放 agent 互操作或扩展多拓扑（swarm/hybrid）可借鉴。
- **技术栈**：monorepo（TS 为主 + 多语言包）。
- **亮点可抄**：拓扑声明 DSL、消息协议、跨运行时桥。
- **结论**：✅ 中高价值，协议定义层精读。

### 59. open-web-bridge — ⭐ agent 驱动真实浏览器
- **是什么**：让任意 AI agent 驱动**你正在用的真实浏览器**（Chrome MV3 扩展 + daemon + relay）：带上登录态、指纹、当前标签页，agent 可在你的真实会话中操作网页；含 skills 封装。
- **对主项目价值**：主项目自动化目前是号池/邮箱池/cf_solver 层面；open-web-bridge 让 agent 直接操作**已登录真实浏览器**，对主项目"号池操作真人网页动作（如上游注册/签到）"是直接可用的浏览器自动化基础设施。
- **技术栈**：Node/npm + Chrome MV3。
- **亮点可抄**：扩展↔daemon 桥接、登录态复用、skill 封装。
- **结论**：✅ 高价值（若主项目号池要做真人会话自动化），`owb-*` 三件套精读。

### 66. glimpse — ⭐ agent 真实浏览器（CDP）
- **是什么**：给 AI 编码 agent 一个真实 Chrome（经 CDP 驱动）：把 agent 渲染结果当 live HTML、驱动并检查运行中的应用、用户圈选高亮回话，双向可视化画布，全本地。
- **对主项目价值**：主项目管理面板是 React 管理台，前端改动验证需要浏览器真实路径；glimpse 的 CDP 驱动 + live 渲染回馈是**前端 E2E/视觉验证的 agent 化增强**参考（与 Playwright 互补）。
- **技术栈**：Node 22+ + Chrome。
- **亮点可抄**：CDP 会话封装、live HTML 渲染流、圈选回话协议。
- **结论**：✅ 中高价值，`lib/` 驱动层精读。

### 18. donsetch — ⭐ web for AI agents（真实浏览器 + MCP）
- **是什么**：Rust 写的 MCP server "DonSeTch — The web, for AI agents"：让 agent 用**真实浏览器（Chrome TLS，非 Chrome-like）**做搜索/解算跳转/PDF/OCR，766 tests；主打"Solve & Bounce"、免 key 搜索。
- **对主项目价值**：与 open-web-bridge/glimpse 同类但走 MCP 协议 + Rust 高性能；主项目已有 MCP 服务端，其"真实浏览器会话 + 反检测 + 搜索/OCR 工具化"对 agent 联网检索与浏览器自动化是互补方案。
- **技术栈**：Rust + npm 包。
- **亮点可抄**：MCP 工具划分（search/solve/pdf）、真实 Chrome 指纹接管。
- **结论**：✅ 中高价值，`src/` 工具集精读。

### 68. Ix — ⭐ 代码库持久图谱
- **是什么**：把仓库解析为**持久系统图谱**（symbols/calls/imports/关系），agent 可查询结构而非 grep；CLI + skills + 输出样例。
- **对主项目价值**：主项目已装 codegraph/code-review-graph/graft 三类图谱工具；Ix 是又一个同类实现——可作为**图谱 schema 与查询接口设计的对照**（比较其符号粒度/增量更新），评估是否值得并入主项目图谱链。
- **技术栈**：TypeScript/Node（ix-cli）。
- **亮点可抄**：图 schema、CLI 查询语法、增量索引。
- **结论**：✅ 中价值（与现有图谱工具高度重叠，作对照即可）。

### 62. antflydb__antfly — ⭐ 搜索+推理数据库
- **是什么**：Zig 零依赖搜索引擎数据库：一个引擎同时承载 BM25/稠密/稀疏/late-interaction 向量索引 + 图遍历；内置模型做 chunk/embed/rerank/OCR；自动生成嵌入/实体/图边；RAG agent 内建；单文件/单节点热备/多 Raft/无服务器对象存储。
- **对主项目价值**：主项目数据层是 SQLite + agent 记忆；antfly 的"一体化混合检索 + 内置 ML 推理"对主项目**知识库/记忆检索升级**是架构级参考（尤其嵌入自动生成 + RAG agent），但 Zig 零依赖引擎接入成本高，宜取理念。
- **技术栈**：Zig。
- **亮点可抄**：混合索引统一表、自动实体/图边生成、RAG 内建。
- **结论**：✅ 中价值（架构理念参考，不建议直接引入 Zig 引擎）。

### 9. HKUDS__nanobot — ⭐ 轻量个人 agent 框架
- **是什么**：极轻量、自托管、开源个人 AI agent 框架（Python）：WebUI/终端/Telegram/Discord/Slack/微信/Email 等多渠道；工具、长期记忆、MCP 集成、**模型路由、多 agent 委派、调度自动化、OpenAI 兼容 API**，核心小而可读。
- **对主项目价值**：与主项目能力面**几乎重叠**（多渠道 + 模型路由 + MCP + OpenAI 兼容 API + agent 化）——是主项目"轻量 + 多渠道"侧的最佳参照物，尤其多 agent 委派与调度自动化是主项目 DAG 编排的简化对照。
- **技术栈**：Python。
- **亮点可抄**：多渠道接入层、模型路由简化实现、调度自动化。
- **结论**：✅ 中高价值，`nanobot/` 核心精读。

### 3. polynoia — ⭐ local-first agent 工作台
- **是什么**：local-first 工作台："AI 队友记得工作"——编码 agent 有身份、工作场所、**持久且作用域化的决策与结果记忆**；多 AI 协作者共享工作台，物化笔记/决策/产物原地保留。
- **对主项目价值**：主项目 agent 化 + 记忆巩固；polynoia 的"**作用域记忆 + 共享工作台物化**"对主项目多 agent 协作上下文设计有参考价值。
- **技术栈**：全栈应用（桌面 + Web，含 build-desktop.ps1）。
- **亮点可抄**：作用域记忆模型、工作台物化（决策/产物持久）。
- **结论**：✅ 中价值，记忆作用域模型可参考。

### 24. everything-claude-code-main — ⭐ Claude Code 全景合集
- **是什么**：140K+ stars 的 Claude Code 生态大合集：agents/commands/skills/hooks/rules/subagents 模板 + 12 语言生态 + 方法论。
- **对主项目价值**：主项目已在用 Claude Code + 大量 ECC 技能；此仓库是**现成 agent/skill 模板与最佳实践的活字典**，可作为主项目 agent 化（critic/subagent/skills）的素材库按需抽取。
- **技术栈**：Shell/TS/Python/Go/Java 等。
- **亮点可抄**：subagent 模板、hooks 规则、工作流编排样例。
- **结论**：✅ 中高价值，`agent.yaml` + 模板目录按需查阅。

---

## 中价值（1-2 行）

1. **Raccoon**：Python 攻击性安全侦察/信息收集工具（DNS/WHOIS/端口扫描/子域枚举/CMS 指纹）。主项目非安全产品，作安全基线参考即可，低-中价值。
2. **dotfiles**：macOS 开发机 dotfiles 管理（zsh/vim/iterm + 把 skills 软链进 Cursor/Claude）。纯个人配置，低价值。
4. **hhhuang__CAG**：Cache-Augmented Generation 论文实现——把全部知识预载入 KV cache 替代实时检索（RAG 免检索方案）。主项目是 AI 网关不直接跑推理，但 CAG 思路对 agent 长上下文/记忆加载有参考，低-中价值。
5. **unlazy**：AI agent"完成纪律"skill——先写验收台账、执行可运行门禁、复验返回工作、只报有证据的结论。主项目"真实闭环/证据优先"理念同源，可作 skill 素材，中高价值。
6. **yoink-main**：Claude Code 插件，把第三方依赖"去依赖化"重实现为内部替换（供应链安全 + 少依赖）。主项目可参考其"按需重实现 + 用原库测试校验"方法论，中价值。
8. **weir**：CI 门禁——读 agent 的 OpenTelemetry traces，检测敏感数据是否流到不该去的 sink（taint 追踪 + witness path）。主项目已有日志脱敏/mask_key，此工具提供**agent 数据泄露的自动化 CI 校验**思路，中高价值。
10. **claude-code-best-practice-main**：Claude Code 最佳实践库（subagents/commands/skills/workflows 概念表 + 实现样例）。知识型，与 ECC 重叠，中价值。
11. **arsenal-ng**：Go 版 pentest 命令启动器（247 工具/2926 命令搜索）。安全工具，低-中价值。
12. **repoprompt__repoprompt-ce**：macOS 原生"上下文工程"App：组装文件/CodeMap/git diff 成可审查上下文交给 agent + 内置 MCP server 编排。与主项目 context 工程思路一致，中高价值但强绑 macOS。
13. **DSH-taskboard**：DeepSeek Harness 原生任务看板插件（SQLite 为任务权威，agent 工具 + 人类验收闭环）。主项目已有审批持久化，此为其 Harness 特化版，低-中价值。
14. **GitHub仓库下载工具（Git-clone-Max）**：PyQt6 桌面工具批量并行克隆/增量更新/入库追踪 GitHub/GitLab/Gitee 仓库。工具类，低价值。
15. **superpowers-main**：Superpowers 软件工程工作流 skill 套件（brainstorming→spec→计划→subagent-driven-development→TDD）。主项目已装 superpowers-zh（同源 20 skills），作上游版本对照即可，高价值（已复用）。
16. **ZingerLittleBee__Heeler**：herdr agent 终端运行时的 iOS 原生 companion（SSH 实时终端 + Composer）。强绑特定宿主，低价值。
17. **nopecha-python**：NopeCHA 付费验证码服务的 Python SDK（requests/aiohttp/httpx/urllib 四种绑定）。主项目有自建 cf_solver 求解器，仅作"验证码解决即服务"API 设计对照，低-中价值。
21. **claude-code-tips-main**：45 个 Claude Code 使用技巧（状态栏/命令/语音/子代理/容器化等）。知识型，低-中价值。
22. **mistral-vibe-main**：Mistral 开源 CLI 编码助手（Python，ACP 协议、工具调用）。agent 工程参照，中价值。
23. **HKUDS__Vibe-Trading**：交易 agent 平台（FastAPI + React 19 + 桌面）。业务与主项目无关，但 FastAPI+React19 架构与主项目一致，可参考其工程组织，低-中价值。
25. **OpenBMB__PilotDeck**：OpenBMB 的任务导向 AI Agent 生产力平台（WorkSpace、MCP native、Agent）。agent 平台参照，中高价值（MCP native 设计可看）。
27. **marketing-dashboard**：本地优先营销运营控制台（Next.js 16 + SQLite，CRM/外联/内容/审批/自动化，可连 OpenClaw）。营销领域无关，其"本地优先 + agent 活动监控"工程可参考，中价值。
28. **tiptour-macos**：macOS 菜单栏 computer-use companion（理解屏幕/听语音/按住热键说话即控制电脑，freeform 高亮操作）。桌面自动化参照，中价值。
30. **builderz-solana-dapp-scaffold**：Solana dApp 脚手架（Next.js 16 + Tailwind v4 + shadcn/ui 玻璃拟态设计系统）。区块链无关，设计系统/组件库可参考，低-中价值。
31. **openclaude**：开源编码 agent CLI（OpenAI 兼容/Gemini/Codex/Ollama 多后端 + MCP + slash 命令）。多 provider 适配与主项目网关 Provider 层思路相通，中高价值。
32. **cua**：computer-use 2.0 开源驱动 + 跨 OS 舰队 + benchmark。computer-use 基础设施，中价值。
34. **LibreChat**：知名开源多模型聊天平台（多 provider、多模态、Agent Builder、RAG）。主项目聊天端点/管理面板可对照其会话与多模态能力，中高价值但体量大。
35. **evonic**：agentic AI 框架（模型/工具/知识库/渠道/skills 声明式定义 + 分布式多 agent 编排）。agent 框架参照，中高价值。
36. **Jellyfish**：AI 短剧工作室（FastAPI + React + Vite 生成脚本/镜头）。②多模态内容生成相关，与主项目图像生态互补，中价值。
38. **crabfleet**：OpenClaw agent 舰队仪表板（Codex 实例按人分组、board 卡片工作流、WebVNC/屏幕共享）。agent 运维/舰队监控参照，中价值。
39. **andrewvieyra__hermes-plugin-netbox**：Hermes Agent 的 NetBox 变更管理插件（**plan-diff-apply-rollback 写保护**：agent 只能按计划写，逐字段 diff + journal + 反向回放）。主项目有审批持久化，其"计划化写保护"模式值得借鉴，中高价值。
40. **PraisonAI**：低代码多 agent 框架（Python + MCP registry）。agent 框架参照，中价值。
41. **vero**：⚠️ 空目录（仅 `.git`，无内容）——疑似未克隆完成，无结论。
42. **croffasia__itsaplan**：Linear/Jira/Trello/Plane 的开源替代（AI agent 内建为队友，REST/webhooks/MCP 全暴露）。项目管理领域无关，但"agent 即队友 + MCP 化"工程可参考，中价值。
43. **worktrunk**：git worktree 管理 CLI（专为并行运行 AI agent 设计）。主项目多 agent 并行开发可参考其 worktree 编排，中高价值。
44. **soulforge-main**：给 AI 编码 agent 的**实时代码库依赖图谱**（live dependency graph + PageRank 重要性 + git co-change 历史，实时更新）。与主项目 codegraph/graft 同类，作对照补充，中高价值。
46. **AQBot**：本地优先桌面 AI 工作台（多服务商对话 + ACP agent + 知识库 + MCP + API 网关，数据本机掌控）。桌面 AI 应用参照，中价值。
47. **cc-polymath**：Claude Code 插件，410+ 渐进式 skills（context-efficient 按项目推荐发现）。skills 库素材，中高价值。
48. **ongrid**：运维 AI agent（Slack/Telegram 触发，metrics/logs/traces 根因关联、blast-radius、远程执行、RAG 知识库）。运维 agent 参照，中价值。
49. **hermes-hudui-main**：Hermes agent 的 Web HUD 监控面板（token 成本、agent 档案、意识监测）。主项目管理面板可参考其成本/档案可视化，中价值。
50. **anycrawl**：多引擎爬虫（site crawl + SERP 多引擎 + 多线程 + AI config）。主项目账号/邮箱自动化可用爬虫工具，中价值。
51. **ghostty-config**：Ghostty 终端配置生成器（Svelte + Cloudflare Workers）。无关，低价值。
52. **xint**：终端 X（Twitter）数据搜索/监控/分析 CLI。低-中价值（社交数据采集有合规边界）。
53. **sqltoerdiagram**：纯浏览器 SQL→ER 图生成器（单页、双向编辑、链接分享）。工具类，低-中价值（前端纯本地实现可参考）。
54. **qwen-code**：Qwen 开源 AI 编码 agent（终端/编辑器/桌面/浏览器/聊天一体）。agent 工程参照，中价值。
55. **t3code**：agent harness 控制面板（移动/web/桌面 App 控制 Claude Code/Codex/Cursor/Grok/OpenCode 等）。agent 控制/远程参照，中价值。
56. **agno**：构建/运行/管理 agent 平台（Python 生态大而全）。agent 框架参照，中高价值。
57. **multica-main**：开源 managed agents 平台（把编码 agent 变队友：分配任务/跟踪进度/沉淀 skills）。agent 平台参照，中价值。
58. **Cairn**：AI 渗透测试框架（腾讯 ChainReactors，"通用状态空间搜索"范式）。安全参照，中价值。
60. **learn-harness-engineering**：harness 工程学习资料（文档/项目/skills 库）。知识型，与主项目 harness 演进相关，中价值。
61. **auto-subs**：本地优先 AI 字幕工具（Whisper/Moonshine/Parakeet 转写、说话人分离、100+ 语言、集成 Resolve/Premiere）。②音频/字幕生成相关，与主项目多模态生态互补，中价值。
63. **K-Vault**：免费图片/文件托管（Cloudflare Pages + Docker 双模，多存储后端）。②图片托管相关，主项目图像生成产物存储可参考，中价值。
64. **Claude-BugHunter**：Claude skill 套件：bug hunting/红队（83 skills、15 命令、681 披露报告模式、Burp MCP 集成）。安全审计 skill 库，中高价值。
65. **Claude-Code-Game-Studios-main**：把单个 Claude Code 会话变成游戏开发工作室（49 agents、72 skills、12 hooks 协调团队）。agent 团队编排样例，中价值。
67. **onyx-dot-app__onyx**：Onyx（原 Danswer）企业级知识搜索/RAG 平台（连接 Confluence/Slack/Drive 等 + agent + 前端）。企业 RAG 参照，中价值。
69. **meta-harness**：元 harness 框架——自动搜索"任务特定模型 harness"（决定模型工作时存取/展示什么）。harness 工程研究参考，中高价值（理念性）。
70. **uisight**：MCP server：实时移动+桌面双会话测量 web UI（对比度/不可见文本/带 selector 的精确诊断）。前端质量/视觉回归参照，与主项目管理面板前端验证相关，中高价值。
71. **scroll-world**：agent skill——生成滚动驱动的"飞穿世界"落地页（scroll-scrubbed fly-through，无剪辑连续运镜）。主项目有 Vue3 落地页，此 skill 可作落地页创意参照，中价值。
72. **METATRON**：本地 AI 渗透测试助手（Ollama + nmap/whois/whatweb/nikto + MariaDB 历史 + agentic loop + 报告导出）。安全参照，中价值。
73. **trivy**：综合安全扫描器（容器/镜像/文件系统/依赖漏洞 + IaC 配置扫描，Aqua 出品）。主项目 CI 安全基线可直接引入做依赖/镜像扫描，中高价值。
74. **OpenSpec**：spec-driven 开发工具（AI 友好，开源 spec 变更管理 + CLI）。主项目"计划书/下一步改进指南"可 spec 化，中高价值。
75. **apurvsinghgautam__robin**：AI 暗网 OSINT 工具（LLM 细化查询/过滤暗网搜索结果）。OSINT，合规风险高，仅参考，低-中价值。
76. **awesome-llm-apps-main**：LLM 应用教程/示例集合（RAG/agent/voice/mcp 教程）。知识型，中价值。
77. **caveman-2**：让 AI 编码 agent 少写 token（"brain big, mouth small"压缩表达）。token 节省思路，中价值。
78. **ultimate_bug_scanner**：AI agent 的 bug 扫描器（1000+ bug patterns，`detectors.yml` 规则驱动，Linux/macOS/Windows）。主项目有 buglog/审查流程，其规则库设计可参考，中高价值。
79. **CCTV_YOLO**：YOLOv5 实时目标检测 demo（低分辨率推理 + 高分辨率绘制 + Gradio + 摄像头流）。无关，低价值。
80. **MoneyPrinterTurbo**：一站式 AI 短视频生成（主题→脚本→素材→字幕→配音→合成高清视频）。②视频生成生态相关（与主项目图像生成网关互补），中价值。

---

## 汇总建议（Top 精读）
- **直接对标主项目**：OmniRoute（网关/路由/预算）、TokHub（网关/计量/告警）、nanobot（多渠道 agent 框架）、Puppetmaster（任务调度/持久续跑）。
- **agent 化增强**：ownmem/honcho（记忆）、pi-shadow-mind（并行 critic）、LongHorizon-Harness（长时循环）、Cotal（分布式拓扑）、weir（数据泄露 CI）。
- **浏览器/自动化**：open-web-bridge、glimpse、donsetch（真实浏览器驱动三选一深入）。
- **前端/工程**：uisight（UI 测量）、ultimate_bug_scanner（bug 规则）、OpenSpec（spec 驱动）、trivy（CI 安全扫描）。
- **图谱对照**：Ix / soulforge（与主项目 codegraph/graft 对比）。
