# g21_misc_9 扫描结果（80 目录）

> 扫描方式：快速 ls + README 前段识别；疑似有价值者已深入确认。
> 价值判断标准：①agent/skills/mcp/context 工程 ②图片/视频/音频生成、电商、PPT/办公文档、多模态 ③网关/API/队列/任务编排 ④桌面/浏览器/自动化 ⑤工程规范/交互/性能/安全。
> 标注：`★高` = 与主项目核心方向高度相关，建议参考；`○中` = 局部可借鉴；`—低` = 无关，一句话定位。

## 高价值（★）

1. **modelcontextprotocol__servers（★高）** — MCP 官方参考实现集合（filesystem / git / fetch / memory / everything / time 等 + 各语言 SDK 用法）。主项目已有 MCP 服务端能力，可对照官方参考实现校准协议细节（工具 schema、错误处理、流式输出），是 MCP 兼容性的权威基准。建议：作为 MCP 协议正确性对照与测试参考。

2. **deer-flow（★高）** — 字节开源 Super Agent Harness（Python3.12/Node22）：编排子代理 + 记忆 + 沙箱 + 可扩展 skills，Deep Research 工作流。与主项目「意图识别、DAG 编排、critic 自反思、记忆巩固」agent 栈高度同构。建议：参考其子代理编排、记忆模块、skills 扩展机制设计，可与主项目 DAG 编排互证。

3. **obra__superpowers（★高）** — 业界最成熟的 coding-agent 方法论 skills 集合（brainstorming/planning/TDD/executing-plans/subagent-driven 等），主项目已安装 superpowers-zh。建议：对照官方版本校准本项目已落地 skills 的完整性，学习其 skills 组合与初始指令架构。

4. **soumatheusgomes__vibe-coding-toolkit（★高）** — 生产级 Claude Code/Codex 工作流工具箱（subagents + superpowers + 规范模板），强调"真实生产验证的方法而非理论"。含文档/模板体系。建议：借鉴其 agent 工作流编排、CLAUDE.md/AGENTS.md 模板与 lint 清零实践。

5. **mksglu__context-mode（★高）** — 上下文压缩/管理工具（另一面"context problem"），面向 coding agent 的 context 优化，已被多家大厂团队使用。与主项目 token 预算、上下文工程相关。建议：研究其上下文压缩策略，可借鉴到主项目 agent 长会话记忆管理。

6. **so-Pi（NVlabs__SoL-Pi）（★高）** — NVIDIA 开源：agent harness 效率机制（减少重复模型轮次、context 重放、过大观测、无谓长日志读取）。主项目 agent 化后存在同类效率痛点。建议：研究其四种可插拔效率机制，评估移植到主项目 agent 循环。

7. **autoharness（tigerless-labs__autoharness）（★高）** — Claude Code 自学习 skills 层：从真实会话蒸馏 skill、同类合并、使用中更新、废弃剪枝，只动自己生成的 skills。主项目有 skills 技能库 + 记忆巩固。建议：学习其 skills 自维护循环（learn/merge/update/prune + ledger），可作为主项目 skill 生命周期管理参考。

8. **letta-code（★高）** — 有状态 agent harness：记忆块（memory blocks）、skill 学习、MemFS（git 跟踪 context）、sleep 期自省。主项目有「记忆巩固」方向。建议：研究其记忆块机制与 MemFS 快照设计，对比主项目记忆实现找差距。

9. **lacp（★高）** — 本地策略/证据/恢复控制层：包装 CLI agent 做确定性路由、审批门、执行记录、内存控制、回滚路径。与主项目「预算门禁、Fence、权限边界」高度契合。建议：借鉴其审批门与证据留痕、回滚机制到主项目 agent 管控。

10. **matterloop（★高）** — Python 组件化 agent 工程闭环：计划/执行/验证/人工反馈/预算/审计，不绑定模型供应商与存储后端。与主项目「计划书 + 预算门禁 + 审计」直接对应。建议：对比其协议注入式架构（组合根建客户端+基础设施注入），评估主项目 agent 层解耦。

11. **govctl（★高）** — AI 编码治理 harness：把 prompt/补丁转成 RFC、ADR、工作项与受控交付（Rust）。主项目有「计划书」「审批持久化」体系。建议：借鉴其 RFC/ADR/工作项流转与治理管线设计。

12. **iFixAi（★高）** — 独立审计 AI agent 的框架：多智能体 disagreement + 可达性门控，捕获 agent 错误与盲点（Python，趋势榜第一）。主项目已有 critic 自反思，但缺独立审计。建议：研究其「多个窄 agent + 故意分歧 + reachability gate」审计流水线，移植到主项目 critic/审查层。

13. **evilsocket__audit（★高）** — 8 阶段漏洞发现 agent（Cloudflare Glasswing 项目复刻）：并行窄 agent + 分歧 + 可达性门。与主项目安全审查方向契合。建议：作为主项目安全/渗透审计 agent 流水线参考（与 iFixAi 互补）。

14. **alibaba__open-code-review（★高）** — 阿里开源代码审查 agent（Go）：架构演进/风险分级/审查上下文。主项目有 code-review-graph + 审查标准。建议：对照其审查流水线（检测变更→影响面→审查上下文），优化主项目审查工具的 token 效率。

15. **redhat-et__ripwire（★高）** — "AI context 界的 ripgrep"：给 agent 一份排名的确定性调用图（改什么、破坏什么、跑哪些测试），大幅省 token。主项目有 codegraph。建议：学习其把调用图+影响分析做成低成本确定性工具的思路，优化主项目 codegraph 输出形态。

16. **anthropics__defending-code-reference-harness（★高）** — Anthropic 官方：自主漏洞发现与修复参考实现（recon→find→triage→report→patch 循环）。主项目安全方向权威参照。建议：作为漏洞修复 agent 流水线黄金标准对照。

17. **alibaba__OpenSandbox（★高）** — 阿里开源 agent 沙箱（多语言、浏览器、可伸缩），主项目 agent 若需沙箱执行可参照。

18. **fastclaw（★高）** — Go 轻量 AI agent runtime：单二进制、任意 LLM、多 agent、沙箱、云就绪，带管理面板（agents/models/skills/users/API keys）。与主项目「多上游网关 + 管理面板」形态接近。建议：研究其 agent 运行时的沙箱与面板设计。

## 中价值（○）

19. **AI-Search-Hub-main（○中）** — 开源 Skill：聚合大厂 AI 平台搜索/抽取能力，借力搜索公众号/抖音/微博等数据。主项目可借鉴其"多平台搜索聚合 + 数据清洗整理接入 agent"的 skill 设计。

20. **GSd-2-main（gsd-2-main）（○中）** — 独立 CLI coding agent（基于 Pi SDK）：跨任务清上下文、精准注入文件、管 git 分支、成本 token 追踪、卡死循环检测、崩溃恢复、里程碑自动推进。MCP 安全 env 收集。主项目可借鉴其「成本追踪 + 卡死检测 + 恢复」agent 运维能力。

21. **bBuilderz-labs__mission-control（builderz-labs__mission-control）（○中）** — 自托管 agent 控制面：SQLite 后台，派发任务/检视 run/审失败/追踪花费/协调多 runtime。与主项目管理面板任务/成本页同构。建议：对照其任务派发与成本追踪 UI 模型。

22. **experientiallabs__experiential（○中）** — OpenAI 兼容 agent 网关与路由器：托管/BYOK/本地模型统一 API，控制身份/模型/预算。与主项目「OpenAI 风格网关 + 预算门禁」几乎同题。建议：深度对比其预算控制与模型路由策略，补主项目缺口。

23. **waooAI__waoowaoo（○中）** — AI 图像/视频创意工作台（右侧 assistant + 画布组织作品）。主项目是图像生成网关，可借鉴其创作工作台交互与参考图上传组织。

24. **foru17__neko-master（○中）** — 网络流量实时监控/审计面板（多网关支持，Node22）。主项目有多上游代理/网关，可借鉴其流量审计 UI 与多网关监控设计。

25. **alibaba__open-code-review 之外的审查生态——Yuxi（语析）（○中）** — 多租户 Harness + 企业知识库（Docker 一键），企业知识可被 agent 检索/推理/交付。主项目有记忆/知识管理需求可参考其多租户知识库设计。

26. **OpenViking-main（○中）** — 火山引擎开源：面向 AI agent 的 Context 数据库（集中管理 agent 上下文/记忆）。主项目「记忆巩固」可对照其 context 存取模型。

27. **holaOS-main（○中）** — agent 环境（Electron/TS），面向长时任务连续性与自我进化。主项目桌面版 Tauri + agent 长任务可借鉴其会话连续性设计。

28. **letta-code 同源思路——Letta（已列★）之外：holaOS / Yuxi 均为 agent 记忆/环境方向，主项目按需取舍。

29. **codeg-main（○中）** — 企业级多 agent 编码工作区（Tauri2 + Next16）：统一 Claude Code/Codex 等、并发 git worktree、MCP/Skills 管理、聊天频道（Telegram/Lark/iLink）远程任务。主项目桌面版已有，可借鉴其多 agent 聚合 + MCP/Skills 管理 + 聊天频道集成。

30. **vanehub-ai（○中）** — Tauri2 + React19 桌面工作台，统一管理 12 种 coding agent CLI：统一会话/权限审批/可观测性/用量统计。与主项目桌面版「统一管理」方向一致，可对照其权限审批与用量统计设计。

31. **claw-code-main（○中）** — 2 小时破 50K star 的 Claude Code 替代实现（Rust，开源，含 CLAW.md/PARITY.md 兼容目标）。主项目桌面 sidecar 可参考其 MCP/agent 协议兼容实现思路。

32. **DeepDeck（○中）** — DeepSeek Harness 桌面客户端 + WebMCP（agent 探索真实网站→保存为可复用工具）。WebMCP 概念对主项目 agent 浏览器自动化有参考价值。

33. **obscura（○中）** — 开源 Rust 无头浏览器（原生渲染无需 Chromium，轻量隐蔽）。主项目 agent/爬取场景可评估其轻量无头方案。

34. **dsh-turn-rewind（○中）** — DeepSeek Harness 的会话回滚/文件恢复引擎（changeLedger 快照 + path 级漂移预览）。主项目桌面版/agent 可借鉴其工作区变更快照与恢复机制。

35. **zvec-grep（○中）** — 本地优先的语义搜索层（基于阿里 zvec），面向人与 agent 的代码/文件检索。主项目 codegraph/grep 场景可对照其本地索引方案。

36. **clawdeck（○中）** — Claude Code 本地仪表盘（零依赖，loopback-only）：会话/事件时间线/成本/上下文遥测/git worktree/审查。主项目管理面板可借鉴其会话与成本遥测 UI。

37. **humanize（○中）** — LLM 无关 skills 集合：让 AI 写作像人（50+ 同行评审依据）。主项目落地页/文案/聊天回复润色可选用。

38. **sepia（○中）** — Agent Skill 规范（agentskills.io 标准）：去 AI 味写作，叙事结构层修复。主项目若有内容生成质量诉求可参考其 skill 打包规范。

39. **TORCH（○中）** — Claude Code 渗透/赏金知识库 + 自动化 harness（Obsidian vault + 500+ 技术页 + 状态优先模型防重复工作）。安全方向深度参考（与 audit/iFixAi 互补）。

40. **free-api（○中）** — 免费验证码 API v3：统一解 Cloudflare Turnstile 与 hCaptcha（浏览器注入+拟人点击）。主项目已有 cf_solver（Turnstile），此项目提供 hCaptcha 扩展思路与参考实现。

41. **upscayl（○中）** — 开源 AI 图像超分辨率桌面工具（Real-ESRGAN 系，Vulkan GPU）。主项目为图像生成网关，可作为图像后处理/增强能力参考。

42. **PriceGhost（○中）** — 自托管价格跟踪：多策略并行抽取（JSON-LD/站点专属/CSS/AI）+ 投票式选择 UI。电商/爬取抽取方向可借鉴其多路投票与 UI。

43. **RepooRewind / RepoRewind（○中）** — 3D Git 历史可视化 + AI 叙事。主项目文档/演进可视化可借鉴，价值一般。

44. **GitNexus-main（○中）** — 本地索引仓库 + 通过 MCP 连接 AI agent + 图探索 + AI 聊天，一键装 agent skills + hooks + AGENTS.md。主项目 MCP 服务端/agent 上下文可借鉴其一键 onboarding 流程。

45. **supervision（○中）** — Roboflow 开源：计算机视觉模型输出后处理/标注/可视化 Python 库。主项目无 CV 生成诉求，仅作图像处理工具库参考。

46. **bytebot-ai__bytebot（○中）** — 开源 AI 桌面 agent（有自己的电脑执行任务，浏览器自动化）。主项目桌面 sidecar/浏览器自动化方向可参考。

47. **promptomatix（○中）** — LLM prompt 优化框架（Python，有 arXiv）。主项目 prompt 工程可参考其优化方法论，价值一般。

## 低价值（—）

48. **supervision** 已列入 ○。以下按清单逐条：**machine-learning-visualized（—）** — ML 算法可视化 Jupyter Book 站点，纯教学，无工程价值。

49. **proqi（—）** — 终端原生 prompt 编辑器（Rust），多 coding agent 提示词管理。交互工具，非工程参考。

50. **JeffBox（—）** — 450KB 单文件 Windows 桌面工具箱（Todo/Markdown/Launcher，WPF）。与主项目无关。

51. **kilocode（—）** — VS Code/JetBrains/CLI 开源 coding agent（500+ 模型零加价）。竞品级 IDE agent，非网关参考。

52. **PhiCookBook（—）** — 微软 Phi 模型动手教程集合（SLM 应用示例）。教程资料，非工程代码。

53. **MiroFish-main（—）** — 群体智能预测引擎（多 agent 模拟社会演化预测未来）。方向新颖但非主项目工程栈。

54. **sgl-project__sglang（—）** — 空克隆（仅 .git，无文件，remote 指向 sglang）。LLM 推理服务框架 sglang，主项目不需要（无本地推理）。

55. **textgen（—）** — oobabooga 本地 LLM 桌面端（GGUF 便携包）。本地推理工具，主项目无本地模型诉求。

56. **awesome-ralph-master（—）** — Ralph 自动化编码方法资源列表（while 循环跑 agent 直到规格完成）。理念性清单。

57. **yolo-training-template（—）** — YOLO 训练模板（Kaggle 数据集）。CV 训练，与主项目无关。

58. **fmt（—）** — C++ 格式化库 {fmt}（工业级格式库）。语言基础库，非参考。

59. **carbon-lang（—）** — Google Carbon 实验语言（C++ 继任者）。编程语言项目，无关。

60. **nautilus_trader（—）** — 高频量化交易框架（Rust+Python，事件驱动引擎）。金融交易，与主项目无关（队列/并发设计可略读）。

61. **wordpecker-app（—）** — 语言学习应用（Duolingo 式）。无关。

62. **asgeirtj__system_prompts_leaks（—）** — 各家厂商 system prompt 泄露合集（Anthropic/Cursor/DeepSeek 等）。仅供 prompt 研究参考，无工程价值。

63. **Ephemeral-AI-Lab__layerfs（—）** — 空克隆（仅 .git，无文件）。

64. **pranshuparmar__witr（—）** — 进程/端口/容器溯源 CLI（"为什么在跑"）。运维工具，主项目用不到。

65. **cashclaw（—）** — 自主接单赚钱 agent（Moltlaunch 链上任务市场）。概念项目，非主项目栈。

66. **malulile-sudo__ma-operations-copywriting（—）** — 运营文案生产/品控 skill（马想得到 App 方法论）。文案 skill，与主项目生成网关无直接关联（聊天内容生成可略用）。

67. **TORCH** 已列 ○。**superset-main（—）** — 注意与 Apache Superset 不同：是"编排 swarms 的 Claude Code/Codex 并行 agent"的代码编辑器，worktree 隔离并行。与 codeg/vanehub 同赛道，已由 codeg 覆盖，主项目桌面版可略读。

68. **openpi（—）** — Pi agent 的终端/本地 Web 工作台 + 独立子代理 + 后台任务管理。与主项目 agent 编排相关度低于 deer-flow/matterloop，略读即可。

69. **qualcomm__GenieX（—）** — Qualcomm 设备本地跑 LLM/VLM 工具（AI Hub）。硬件绑定本地推理，主项目不需要。

70. **cap（—）** — 开源屏幕录制/分享桌面工具（Tauri）。主项目桌面版无录屏诉求。

71. **rtk（—）** — Rust 高性能 CLI 代理，压缩 bash 输出最多省 90% token（agent 读取优化）。token 优化思路可借鉴（grep/命令输出压缩），价值中低。

72. **airi（—）** — 重造 Neuro-sama 的 AI waifu 虚拟角色项目（灵魂容器）。娱乐向，无关。

73. **dsh-turn-rewind** 已列 ○。

74. **on-page-seo（AgriciDaniel__on-page-seo）（○中，补列）** — 页内 SEO 分析器（React19+Node+SQLite，Firecrawl+DataForSEO，74 指标）。前端栈与主项目同构，可作为 React19+SQLite 全栈样板参考。

## 汇总

- **高价值 18 个**：MCP 官方 servers、deer-flow、superpowers、vibe-coding-toolkit、context-mode、SoL-Pi、autoharness、letta-code、lacp、matterloop、govctl、iFixAi、evilsocket/audit、open-code-review、ripwire、defending-code-reference-harness、OpenSandbox、fastclaw
- **中价值 24 个**：AI-Search-Hub、GSD-2、mission-control、experiential、waoowaoo、neko-master、Yuxi、OpenViking、holaOS、codeg、vanehub、claw-code、DeepDeck、obscura、turn-rewind、zvec-grep、clawdeck、humanize、sepia、TORCH、free-api、upscayl、PriceGhost、GitNexus 等
- **低价值/无关 38 个**（含 2 个空克隆 sglang、layerfs）
- **优先精读建议**：与主项目「agent 编排 + 预算门禁 + MCP + 记忆」四条主线的直接对标项目为 **deer-flow / matterloop / lacp / iFixAi / experiential / modelcontextprotocol servers / SoL-Pi**；与「审查与安全」对标为 **open-code-review / ripwire / iFixAi / evilsocket-audit / defending-code-reference**。
