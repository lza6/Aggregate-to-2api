# g20_misc_8（80 个目录）扫描结果

> 主项目对标口径：听风AI = AI 图像/对话生成网关（FastAPI/SQLite/SSE）+ 号池/邮箱池/代理池 + MAB-EWMA 路由/熔断/预算门禁 + agent 化（意图识别/DAG 编排/critic 自反思/记忆巩固/MCP/skills）+ React19 管理面板 + Tauri2 桌面 + Vue3 落地页。
> 价值维度：①agent/skills/mcp/context 工程 ②图片/视频/音频生成·电商·多模态 ③网关/API/队列/任务编排 ④桌面/浏览器/自动化 ⑤工程规范/交互/性能/安全。
> 结论分级：★高价值（深度对标）· ◐中价值（可借鉴）· ○低/无关（一句话定性）

---

## 1. graphiti — ★ 时间知识图谱框架（agent 记忆层）

- 是什么：Zep 开源的时间知识图谱框架，为 AI agent 构建"bi-temporal 事实图"（实体/关系/事实带有效性窗口），混合检索（语义+关键词+图谱遍历）。
- 解决什么：agent 长时记忆会过时/冲突——需要"何时为真、何时失效"的时序记忆，而非静态向量库。
- 技术要点：Python，Neo4j/FalkorDB 后端，Pydantic 定义本体（实体/边类型），arXiv:2501.13956；记忆巩固（consolidation）机制把零散对话压缩成图谱。
- 对主项目价值：主项目已有"记忆巩固"agent 化，graphiti 是记忆层的事实标准，可为记忆巩固的存储/查询模型提供参考（时序有效性 + 混合检索），也可作为可选外部记忆后端。
- 建议：研究其"临时 vs 长期记忆分层 + 巩固"设计，移植到主项目记忆模块的概念模型；不直接引入（需图数据库）。

## 2. trailhq__Graft — ◐ 代码库 context 层（主项目已集成）

- 是什么：为 Claude Code/Cursor/Codex/Gemini 等编码 agent 提供大代码库上下文索引（TypeScript，npm @nanonets/graft）。
- 解决什么：agent 在大仓库里检索/理解上下文慢且费 token；Graft 预构建可复用 context 层。
- 对主项目价值：**主项目本身已用 graft 索引本仓库**（graft/ 目录 + CLAUDE.md 约定），本目录即该工具源码，可作为主项目 graft 用法的官方文档/扩展参考。

## 3. Kangentic__kangentic — ◐ 多 agent CLI 的 Kanban 看板

- 是什么：桌面端 Kanban 看板，从一块板 spawn/suspend/resume 14 个 agent CLI（Claude Code/Codex/Gemini 等）会话，管理各自 backlog。
- 解决什么：多 agent 并行开发会话混乱、无法统一跟踪状态/输出/进度。
- 对主项目价值：与主项目 agent 化 + 管理面板相关；其"多 agent 会话统一看板"交互可参考进主项目前端任务/会话视图（P3 增强）。

## 4. Zackriya-Solutions__meetily — ○ 隐私优先 AI 会议助手

- 是什么：本地/私有部署的会议纪要+助手（Rust backend + llama-helper，桌面应用）。
- 解决什么：会议录音转写、摘要、行动项，强调数据不上云。
- 对主项目价值：无关（语音/会议域），但 Rust 后端结构可作工程参考。

## 5. gaffer — ◐ 计划-调度-验收的 agent 编排器（Python）

- 是什么：纯 Python（0 运行时依赖）的 agent 编排工具："plan → waves(依赖图) → 每任务一个 git worktree → gate(退出码验收) → 完成/驳回/回滚"。
- 解决什么：让 agent 的"任务完成"有可执行验收（gate 命令），依赖不可走时阻塞，杜绝口头"完成了"。
- 对主项目价值：主项目有 DAG 编排 + 验收 gate，gaffer 的"gate 命令 + worktree 隔离 + unfinish 回滚"是简洁可移植的模式，适合主项目 agent 任务节点验收增强。

## 6. no-ai-slop — ◐ 写作去"AI味" skill（Agent Skills 标准）

- 是什么：单个 SKILL.md（agentskills.io 标准），36 个 AI 腔模式检查，写作用/不用。
- 解决什么：避免文案的 AI 味（空话、排比、无信息量）。
- 对主项目价值：skill 打包/分发格式（Agent Skills 标准，可装进 Claude Code/Codex/Cursor）与主项目 skills 技能库组织方式一致，模式清单可复用于主项目文案类 agent。

## 7. awesome-generative-ai-apps — ◐ 50 个完整 AI SaaS 产品模板

- 是什么：50 个可直接上线的 AI 应用模板（auth+billing+AI 全接线），按画像/美妆/电商/视频/写作/平台分类。
- 解决什么：给"想快速起一个 AI 产品"的人提供可品牌化底子。
- 对主项目价值：与主项目"图像生成"域相关，其图像生成/电商类应用的端到端接线（支付、鉴权、前端）可作为主项目对外产品化的参考。

## 8. ilovepixelart__pi-code — ○ pi 编码 agent 的 Claude Code 兼容层

- 是什么：让 pi.dev agent 读取项目 .claude/ 配置（rules/commands/skills/hooks/MCP），并补齐 todo 覆盖层、checkpoints、记忆、web 搜索、子代理。
- 解决什么：pi 生态复用 Claude Code 项目配置。
- 对主项目价值：低相关（工具生态），其"读取并信任项目配置前需审批"的安全模型可参考。

## 9. OpenLore — ★ 确定性本地记忆 + 变更守卫（无 LLM 热路径）

- 是什么：本地优先、确定性的 agent 记忆与 guardrails；静态分析驱动，无需 API key，支持 21 语言+12 IaC；MCP-ready。
- 解决什么：给 agent"一次调用告诉它任务触及哪些代码 + 一道闸门告诉它哪些不能改"，答案可复现、不受 LLM 漂移影响。
- 对主项目价值：主项目 agent 化的"critic 自反思/记忆巩固"可借鉴其确定性记忆 + 禁止修改区 guardrails（类似主项目已做的 Fence/预算门禁思路），5500+ 测试的工程水准值得学习。
- 建议：提取其"静态分析决定读什么/不能碰什么"的机制到主项目 agent 上下文管理。

## 10. obsidian-mind — ◐ Obsidian 驱动的 Claude Code 记忆库

- 是什么：把 Obsidian vault 当 Claude Code 的长期记忆（笔记/链接/索引/性能管理自动维护），跨会话累积。
- 解决什么：会话记忆连续性 + 可视化知识管理。
- 对主项目价值：与主项目 OpenWolf/.wolf 记忆体系同类，其"笔记即记忆 + 自动索引"模式可参考；主项目已有更强闭环，价值一般。

## 11. amplifthq__opentag — ◐ Slack 持久 AI 队友（ACP 控制平面+Runner）

- 是什么：自托管 Control Plane + Runner，把编码 agent 通过 ACP（Agent Client Protocol）接到 Slack，排队执行、回帖报告状态/证据。
- 解决什么：让 AI 队友在配对的机器离线时仍可接活，工作可排队异步执行。
- 对主项目价值：主项目 agent 化可参考其"消息队列 + ACP 标准接入 + 证据回传"架构，若未来做 IM 集成（微信群/飞书）是现成模板。

## 12. open-mercato — ◐ AI 工程基础框架（架构感知 harness）

- 是什么：开源"AI-Engineering Foundation Framework"：架构感知 harness（agent 知道代码放哪、如何分层）、spec-first 开发、CRM/ERP 就绪模块、code review/ticketing 协作 skills。
- 解决什么：30-50 人团队里 AI 生成代码的落位与一致性。
- 对主项目价值：工程规范类；其"spec-first + 架构落位约束"与主项目计划书/多 agent 纪律可互相印证；模板本身（CRM/ERP）与主项目无关。

## 13. cc-switch — ★ Tauri 桌面端多 LLM 提供商切换器

- 是什么：Tauri2 桌面应用，一站式管理 Claude Code/Desktop/Codex/Gemini/Grok/OpenCode/OpenClaw/Hermes 的 API 提供商/模型配置并快速切换。
- 解决什么：多个 AI 工具各自配 provider 烦琐，切换供应商/模型要改一堆配置。
- 对主项目价值：**与主项目 Tauri2 桌面 sidecar + 网关 provider 聚合直接相关**：其一键多 provider 配置管理 UI 可作为主项目桌面端"上游提供商管理/切换"的交互与数据模型参考。
- 建议：对照其 Tauri 配置持久化 + provider 切换 UX，评估主项目桌面端复用。

## 14. autoresearch-master — ◐ 基于 GitHub Issue 的全自动开发

- 是什么：karpathy/autoresearch 思想的通用实现：喂一个 Issue，agent 自动拆解、实现、开 PR，任意 Git+GitHub 语言项目可用，含桌面 app。
- 解决什么：把开发交给 agent 全天候跑，人只喝茶睡觉。
- 对主项目价值：与主项目 agent 化/DAG 编排同域；其 Issue 驱动任务循环 + 验收闭环与主项目任务系统可互参考。

## 15. lingji-cut — ◐ 本地优先 AI 视频创作工作台

- 是什么：桌面端 AI 视频创作全流水线：选题采集→写稿→AI 审稿→TTS 语音→字幕→信息卡/封面生成→时间线剪辑→Remotion 导出→多平台发布。
- 解决什么：把内容创作各环节串成一条本地优先流水线。
- 对主项目价值：②域相关（视频生成/多模态）；其 TTS/字幕/封面生成环节与主项目图像生成能力可组合；Remotion 导出流水线是优秀工程样例。

## 16. netwatch — ○ Rust 终端网络监控 TUI

- 是什么：Rust TUI 网络监控：命名每个连接背后的进程、解密握有密钥的 TLS、诊断问题并给出修复建议。
- 解决什么：终端里的进程级网络可视化与排障。
- 对主项目价值：无关（系统工具），Rust TUI 写法可参考。

## 17. copilotkit — ◐ agent-native 应用框架（生成式 UI + HITL）

- 是什么：在 React/Angular/Vue/RN/Slack/Teams 上构建 agent-native 应用的框架：生成式 UI、共享状态、human-in-the-loop 工作流；自带 AG-UI 协议把任意 agent 接入多 IM。
- 解决什么：让 agent 不只是聊天，而是可嵌入 UI、可人机协同的应用组件。
- 对主项目价值：主项目前端 15 页管理面板 + 聊天 Playground 可借鉴其生成式 UI/流式状态管理；若未来接 IM 可参考其协议封装。

## 18. semantica-agi__semantica — ★ 图原生上下文/知识图谱基础设施

- 是什么：开发者优先的上下文与知识基础设施：摄入企业数据→构建 Context Graph + Knowledge Graph→图分析+因果推理，内置决策 provenance（全链路可溯源/可解释）。
- 解决什么：替代昂贵企业平台的"可问责 AI 系统"底座，让 AI 结论可解释、可追踪。
- 对主项目价值：与主项目"记忆巩固/意图识别"同属 context 工程；其"决策 provenance + 因果推理 + ontology 管理"是主项目 agent 化（critic 自反思、审计）可借鉴的溯源模型。

## 19. FreeToken — ○ 边缘 MoE 本地推理引擎

- 是什么：把消费级 GPU/CPU/内存当统一弹性平台的 MoE serving 引擎，本地跑 290B+ 开源 MoE（带宽自适应 CPU-GPU 协同、LRU 专家缓存），Anthropic/OpenAI 兼容 API。
- 解决什么：个人硬件上跑超大 MoE 模型。
- 对主项目价值：低相关（本地推理，非网关/图像），但若主项目未来支持"本地模型上游"可作参考。

## 20. semantix — ★ 跨会话记忆 + 语义缓存 + 自适应调度 + 预取

- 是什么：跨会话记忆系统：语义缓存（provider 缓存命中率可达 99.8%）、自适应调度（学习工具调用模式并行化）、投机预取（模型等待时预取只读上下文）、跨会话学习。
- 解决什么：让 agent 每次会话不再重复烧 token/重复读上下文，大幅省钱提速。
- 对主项目价值：**与主项目 MAB 路由/熔断/预算门禁高度相关**：语义缓存是预算门禁之外的另一省钱维度；其"调度器学习工具使用模式 + 预取"可增强主项目异步队列/agent 编排。
- 建议：重点研究其 prefix 卫生中间件（第三方端点缓存失效问题）与调度器，评估并入主项目网关层。

## 21. Fabric — ◐ AI 提示工程模式框架（Go）

- 是什么：danielmiessler 经典项目：海量"模式"（patterns：用固定提示模板处理文本，如总结/提取/改写），Go CLI + 本地 API，可组合成流水线。
- 解决什么：把重复的 AI 文本处理任务固化成可复用、可组合的模式。
- 对主项目价值：提示模板工程化（patterns 目录结构 + CLI 调用）与主项目 skills 体系可互相借鉴。

## 22. GitNexus — ◐ 企业代码库知识图谱 + MCP 工具

- 是什么：把代码库索引成知识图谱（依赖/调用链/集群/执行流），通过 CLI + MCP 工具暴露给 agent；另有 Web UI 可对话。
- 解决什么：让 Cursor/Claude Code/Codex 对大仓库有架构级视野，不盲改。
- 对主项目价值：与主项目 codegraph/graft 同类（主项目已内建 codegraph），其 MCP 暴露方式可参考；Web 对话 UI 是额外亮点。

## 23. ART — ◐ Agent 强化训练器（GRPO）

- 是什么：OpenPipe 出品，用 GRPO 对多步 agent 做真实任务强化训练（PyPI openpipe-art）。
- 解决什么：让 agent 在真实环境里通过试错学会多步任务。
- 对主项目价值：agent 化进阶方向（训练而非仅提示）；主项目当前无需训练，可作为长期能力储备。

## 24. vibe-kanban — ◐ 本地 Kanban 工作流 for 编码 agent

- 是什么：把 Claude Code/Gemini CLI/Codex 等接到本地 Kanban 板，任务卡片驱动 agent 协作（Rust 内核）。
- 解决什么：把 agent 开发组织成看板流水线。
- 对主项目价值：与 3（kangentic）同类，agent 任务看板交互可参考进主项目前端任务视图。

## 25. atlas — ★ 编码 agent 的"源代码控制"（checkpoint 溯源）

- 是什么：Rust 桌面应用：每次 agent 运行产生 checkpoint，把 commit 链回产生它的会话（prompts/工具调用/推理）；多 agent（Claude/Codex/ACP）同库并行，共享记忆跨 agent 生效；本地优先，可团队同步。
- 解决什么："哪个 agent 做了什么、为什么"——agent 行为的版本控制与可审计性。
- 对主项目价值：主项目多 agent + 审计日志可借鉴其 checkpoint 溯源模型（会话↔变更↔记忆联动），与主项目 SSE 事件流/审计表互补。

## 26. mnemosyne — ★ SQLite 零云记忆层（与主项目技术栈完全契合）

- 是什么：pip install 即用的通用记忆层，一个 SQLite 库搞定，纯 Python 单依赖；MCP-ready，支持 Claude Code/Cursor/Codex/OpenClaw/Hermes 等。
- 解决什么：任何 agent 框架都能获得持久记忆，无需外部服务。
- 对主项目价值：**主项目即 SQLite(aiosqlite) + 记忆巩固**，mnemosyne 的数据模型/提取-巩固-召回流程与主项目记忆模块可深度对标；其"单 SQLite 零云"哲学与主项目完全一致。
- 建议：对照其 schema 与 MCP 暴露方式，检查主项目 .wolf 记忆/记忆巩固实现的差距。

## 27. AutoSeg-SAM2 — ○ 视频自动分割（SAM2）

- 是什么：基于 SAM2/SAM1 的视频自动全分割工具（目标跟踪 + 新目标检测）。
- 解决什么：视频逐帧分割与目标追踪。
- 对主项目价值：无关（CV 视频分割，非生成网关）。

## 28. crewAI — ◐ 多 agent 编排框架标杆

- 是什么：最流行的开源多 AI agent 编排框架（crew = 角色+任务+流程），与 LangChain 生态深度集成。
- 解决什么：定义 agent 团队、角色分工、任务依赖与执行流程。
- 对主项目价值：主项目已有自研 DAG 编排，crewAI 的角色/任务/流程抽象可作为概念对照；主项目更轻，不必引入。

## 29. robin — ○ 暗网 OSINT 调查工具

- 是什么：AI 驱动的暗网 OSINT：LLM 优化查询、过滤暗网搜索引擎结果、生成调查摘要。
- 解决什么：暗网情报调查。
- 对主项目价值：无关（安全侦查域，且涉暗网，仅作了解）。

## 30. arc-kit-main — ◐ 企业架构治理工具包（多 agent CLI 版）

- 是什么：为企业架构师做的治理工具：架构原则、干系人驱动、风险管理（HM Treasury Orange Book）、供应商采购、设计评审工作流；分 arckit-claude/codex/copilot/gemini 四套 agent 集。
- 解决什么：把架构治理从散文档变成系统化 AI 辅助流程。
- 对主项目价值：⑤工程规范类；其"AI agent 固化组织流程（模板/审查/风险)"的组织方式可参考主项目 agent skills 化。

## 31. awesome-system-prompts — ○ 系统提示词收藏集

- 是什么：收集各大 LLM/AI 产品/工具的系统提示词，展示内部机制与输出风格。
- 解决什么：提示工程研究参考。
- 对主项目价值：低（参考资料），可作主项目各 agent 系统提示词灵感来源。

## 32. OmniRoute — ★★★ 免费 AI 网关（主项目头号对标）

- 是什么：MIT 自托管 AI 网关：356 个 provider、150+ 免费额度（约 1.47B 免费 token/月）、19 种路由策略、12 引擎 token 压缩（RTK+Caveman，平均省 89%）、自动 fallback；内置 MCP server（110 工具）、A2A agent 协议、持久记忆、guardrails、SQLite 审计、TLS 指纹隐身、Electron 桌面 + PWA。
- 解决什么：把所有 AI 工具/免费额度收敛到一个 OpenAI 兼容端点，自动路由/降级/压缩，永不因限流卡死。
- 对主项目价值：**与主项目网关定位高度重叠且更激进**：路由策略（19 种 vs 主项目 MAB-EWMA）、免费 provider 聚合（对标主项目 5 家上游/号池）、token 压缩、限流/审计、多协议支持均值得逐一对照差距。
- 建议：做一次系统性 diff（路由引擎/预算管理/fallback/provider catalog），吸收其"免费额度池化 + 自动 fallback + 压缩"思路，避免重复造轮子。

## 33. hermes-venice-web — ○ Venice 隐私 web 搜索插件

- 是什么：Hermes agent 的 Venice AI web_search/web_extract provider 插件（零数据留存、匿名 Google 兜底）。
- 解决什么：给 agent 加隐私优先的联网搜索后端。
- 对主项目价值：低相关（主项目不做 web 搜索），其 provider 插件模式可参考。

## 34. llm-wiki — ◐ LLM 编译知识库（多 runtime 插件）

- 是什么：把"粗糙想法"研究塑造成"交付项目"的知识库系统：并行研究、采集目录、会话记忆、源摄入、编译、审计、查询、产物生成；Claude Code/Codex/OpenCode 插件，Obsidian 兼容。
- 解决什么：给 agent 一个结构化的知识生产管线（想法→研究→项目）。
- 对主项目价值：与主项目 skills/记忆/知识管理相关；其"知识编译为可交付项目"的工作流可作为主项目 agent 知识生产参考。

## 35. handraw-style — ◐ 手绘风格提示词库（图像生成域资产）

- 是什么：001–216 种手绘风格提示词库（中文+英文），选编号→得到带风格名的提示词→交支持生图的 AI 使用。
- 解决什么：不会描述画风也能稳定复现风格、跨模型不漂移。
- 对主项目价值：**主项目是图像生成网关**，此类风格化提示词资产可直接用于主项目的提示词模板/风格库功能（前端可提供"风格选择"入口），是低成本高契合的内容资产。

## 36. openyak — ◐ Codex/Claude Code 本地桌面 GUI

- 是什么：本地桌面 GUI for Codex 和 Claude Code：保留会话、检视文件、共享浏览器里协同 agent（v2 alpha）。
- 解决什么：把终端里的 agent 搬进图形界面，看到工作过程而非只有答案。
- 对主项目价值：④域；主项目已有 Tauri2 桌面 sidecar，其"会话可视化 + 文件协同"交互可参考。

## 37. reef — ★ 自改进 agent 的持续学习基础设施

- 是什么：首个开源"持续自改进 agent"基础设施：连接推理、反馈、学习、版本化交付；既可用 Slime/SGLang 训权重，也可改进 harness（prompts/rules/skills）；提供多条 recipes（coral/gepa/meta_harness/openclawrl 等）。
- 解决什么：agent 不只跑任务，还能从反馈中自我迭代（权重级或 harness 级）。
- 对主项目价值：主项目已有"critic 自反思 + 记忆巩固 + 自升级"，reef 的"harness 级学习（改 prompts/rules/skills 并版本化）"闭环是主项目自反思的升级方向，可直接借鉴其 recipes 设计。

## 38. claude-vibe-squad — ◐ 纯 Markdown 多模型专家编排

- 是什么：1 个协调者 + 5 个模型族 + 71 个纯 Markdown 专家（可读可改），原生 CLI + 隔离 worktree 编排。
- 解决什么：用可读可编辑的 Markdown 定义跨模型 agent 团队。
- 对主项目价值：其"专家即 Markdown（可审计可版本化）+ worktree 隔离"模式与主项目 skills 技能库/多 agent 纪律契合，组织方式可参考。

## 39. agtx — ◐ 终端原生 agentic 开发环境（黑板多 agent）

- 是什么：Rust 终端黑板：一块共享板 + agent 舰队，任务并行委托给多编码 agent，不同模型协作（Codex 规划/Claude 实现/Grok 评审），自动会话切换与上下文感知。
- 解决什么：多模型多 agent 并行协作的终端工作台。
- 对主项目价值：与主项目 DAG 编排/多 agent 同域；其"黑板 + 多模型分工 + 会话切换"可作为主项目 agent 编排交互参考。

## 40. openui — ◐ LLM 生成 UI 组件工具

- 是什么：W&B 的"用描述生成并实时渲染 UI"工具，可把 HTML 转 React/Svelte/Web Components。
- 解决什么：加速前端组件原型（类 v0 开源版）。
- 对主项目价值：⑤/前端域；主项目管理面板开发可参考其"描述→渲染→转换"流水线，属可选工具。

## 41. sandbox-runtime — ★ OS 级沙箱运行时（agent/MCP 安全执行）

- 是什么：Anthropic 官方 research preview：用 OS 原生沙箱原语（macOS sandbox-exec / Linux bubblewrap）+ 代理网络过滤，给 agent/本地 MCP server/bash 任意进程做文件系统+网络限制，无需容器。
- 解决什么：让 agent 默认更安全——限制能读能写能连的边界。
- 对主项目价值：主项目有 cf_solver 外部进程 + Fence/预算门禁安全层，此沙箱可作为主项目"外部求解器/agent 进程隔离"的增强（防越权读写/联网），是安全域高契合组件。

## 42. gnekt__My-Brain-Is-Full-Crew — ◐ Obsidian vault 多 agent 管家

- 是什么：8+ agents + 14 个技能管理 Obsidian 库：整理、归档、连接、搜索、转写、邮件分类，多语言，支持 Claude Code/Gemini/OpenCode/Codex。
- 解决什么：个人知识库的自动化打理。
- 对主项目价值：与主项目记忆/知识管理同域；agent 分工模式可参考，整体偏个人知识管理、价值一般。

## 43. luvus — ◐ Rust "AI 编码 agent 任务控制台"

- 是什么：Rust 编写的编码 agent 任务控制台（mission control），跨平台。
- 解决什么：集中管理/调度多个编码 agent。
- 对主项目价值：④/agent 编排域；与 agtx/vibe-kanban 同类，控制台交互可参考。

## 44. ripwire — ★ 调用图 context（"AI 上下文的 ripgrep"）

- 是什么：Red Hat 出品，指向仓库生成**确定性排名调用图**——告诉 agent 该动什么、会破坏什么、该跑哪些测试，而不是 grep 到处乱读；C++23，0 运行时依赖。
- 解决什么：让 agent 动手前有"代码地图"，少读少 token 少破坏。
- 对主项目价值：与主项目 codegraph/graft 同属"上下文/影响半径"工程；其"受影响测试推荐"能力是主项目 codegraph impact 的增强方向。

## 45. SafeLine — ★ WAF（雷池社区版）——网关安全增强

- 是什么：字节跳动开源的免费 Web 应用防火墙（WAF）：流量检测拦截（SQLi/XSS/CC 等），Docker 一键部署，管理后台 + 可编程 SDK/管理 API。
- 解决什么：给暴露公网的 Web 服务加应用层防护。
- 对主项目价值：主项目 `/v1/generate*` 公益开放且 `/v1/*` 对外，安全基线要求"限流/防注入/CSRF"；SafeLine 可作为主项目网关前置防护的可选组件或安全能力对标（比自研防火墙省力）。

## 46. mirafold — ◐ 编码 agent 的浏览器界面 + 生成式 UI

- 是什么：给 Claude Agent/Codex/OpenCode/Gemini CLI 加浏览器界面，叠加生成式 UI（仓库概览、测试-修复循环、交互式 shell、固定图表），每 agent 一个专用 adapter。
- 解决什么：把终端 agent 变成可视化工作台。
- 对主项目价值：④域；与 openyak/atlas 同类，其 adapter 分离 + 生成式 UI 交互可参考。

## 47. imgcompress — ◐ 本地图片压缩/转换/抠图服务

- 是什么：Docker 自托管图片工具：70+ 格式转换、批量压缩、本地 AI 去背景、12 语言 UI，零云（文件不出服务器）。
- 解决什么：本地批量图片处理。
- 对主项目价值：②图像域；主项目是图像**生成**，此工具可作生成结果的**后处理**增强（压缩/格式转换/抠图）候选，属低成本扩展。

## 48. OpenHands — ◐ 自托管编码 agent 控制中心（Agent Canvas）

- 是什么：OpenHands 的 agent 控制中心：本地/远程/云多后端运行 OpenHands/Claude Code/Codex/Gemini 或任意 ACP agent。
- 解决什么：统一面板控制多个 agent 环境。
- 对主项目价值：④/agent 编排域；ACP 多后端抽象可参考。

## 49. OpenBot — ★ 可信 AI 同事（每个 agent 独立浏览器+文件+审批）

- 是什么：CopilotKit 出品：每个 AI 同事拥有独立浏览器（自带登录态）、独立文件、只授予的工具；所有动作执行前决策、执行后记录，可审批。
- 解决什么：给 agent 真实访问权的同时保持可审计、可撤销的安全边界。
- 对主项目价值：主项目 agent 化强调"安全护栏/工具调用安全护栏"（已实现），OpenBot 的"隔离身份 + 动作前审批 + 全程记录"是完整的参考实现，可用于主项目 agent 的浏览器/外网操作增强。

## 50. magnitudedev__magnitude — ○ 本地模型运行器（桌面）

- 是什么：桌面应用，为你的机器挑选并运行最合适的本地模型（LLM）。
- 解决什么：一键跑本地模型。
- 对主项目价值：低相关（本地推理，主项目为网关），与 FreeToken 同类。

## 51. GhostTrack — ○ 手机定位/号码追踪 OSINT 脚本

- 是什么：Python 脚本，按手机号/号码做位置/信息追踪（OSINT 采集）。
- 解决什么：信息收集。
- 对主项目价值：无关（且涉及隐私敏感操作，主项目不涉此域；仅作了解）。

## 52. jordan-gibbs__hyperresearch — ★ DeepResearch harness（16 步管线）

- 是什么：把 Claude Code 变成深度研究 agent：tier-adaptive 16 步管线，产出对抗式审计报告，全源溯源；每个读过的源进持久可检索 vault，会话越用越聪明。
- 解决什么：高质量多步研究 + 可溯源报告 + 研究记忆沉淀。
- 对主项目价值：主项目 agent 化含意图识别/DAG 编排，hyperresearch 的"研究管线分级 + 源 vault + 审计报告"可作为主项目研究类 agent 任务的模板。

## 53. InsForge-main — ◐ agentic development 后端

- 是什么：为 agentic 开发构建的后端（OAuth 集成 GitHub/Google、API、SDK、团队 agent 基础设施）。
- 解决什么：给 agent 产品提供鉴权/账号/API 底座。
- 对主项目价值：③后端域；主项目鉴权（IF_API_KEYS）较简单，InsForge 的 OAuth + 团队模型可参考，但引入成本高，价值中等。

## 54. three-man-team-main — ◐ 三 agent 流程（Architect/Builder/Reviewer）

- 是什么：三个 agent 分工：Architect 规划+部署、Builder 严格照 brief 实现、Reviewer 把关不放行不对的东西，带明确交接与防漂移规则。
- 解决什么：纠正 AI 编码"不守纪律"（多读、加未要求的 feature、中途漂移）。
- 对主项目价值：主项目多 agent 已含类似分工（规划/实施/critic 审查），其"明确 brief + 交接协议"可对照强化主项目 agent 纪律规则。

## 55. ruvnet__ruflo — ◐ Claude Flow 编排（npm 库）

- 是什么：Claude Code 的 flow 编排库（npm ruflo），组织多步 agent 工作流/目标规划，配套 goal planner UI 与 live agents。
- 解决什么：用代码/配置编排 agent 多步任务。
- 对主项目价值：与主项目 DAG 编排同域；目标规划交互（goal.ruv.io）可参考。

## 56. awesome-claude-code-main — ○ Claude Code 资源大全（awesome list）

- 是什么：Claude Code 生态资源索引（工具/技能/教程表格 CSV 等，含多风格 README）。
- 解决什么：找 Claude Code 相关资源的目录。
- 对主项目价值：低（资源索引），可按需检索主项目可借鉴的工具/技能。

## 57. EverOS-main — ★ 长时记忆方法 + 基准 + 用例集合

- 是什么：EverMind 出品的统一仓库：EverCore/HyperMem 记忆方法、EverMemBench/EvoAgentBench 基准、自进化 agent 用例；为"构建/评估/集成长期记忆"提供一揽子方案。
- 解决什么：agent 长期记忆该怎么做、怎么测、怎么集成——方法论+基准。
- 对主项目价值：主项目有记忆巩固但缺基准；EverMemBench 可用来评估主项目记忆模块效果，HyperMem 等方法可参考实现。

## 58. awesome-autoresearch — ○ autoresearch 案例清单

- 是什么：各行业 autoresearch（自动研究/开发）真实用例的 awesome list。
- 解决什么：了解 autoresearch 的行业应用模式。
- 对主项目价值：低（清单），可辅助主项目 agent 自动化的场景规划。

## 59. claude-seo — ◐ Claude Code SEO 审计插件（多 sub-skill/agent）

- 是什么：开源 SEO 分析插件：25 个 sub-skills + 18 个专家 agent 并行跑技术 SEO/内容质量(E-E-A-T)/Schema/GEO/本地/电商/国际 SEO，产出按优先级排序的可测行动计划，410 个测试。
- 解决什么：把 SEO 审计做成可复现的 agent 化流程。
- 对主项目价值：①skills 生态参考：其"25 sub-skills + 18 agent 并行 + 测试化"的组织方式是主项目 skills/多 agent 体系的优秀样板（与主项目落地页 SEO 也有间接关系）。

## 60. doorman — ★ Rust API 网关 + 控制平面

- 是什么：Rust 写的 API 网关与控制平面：多协议（REST/SOAP/GraphQL/gRPC/gRPC-Web + AI API）、双存储（内存模式或 MongoDB+Redis）、集中配置/访问管理/流量控制/运营、自托管 Web 客户端。
- 解决什么：把 API 网关的配置、鉴权、限流、运维统一到一个自托管控制平面。
- 对主项目价值：主项目是网关但无"控制平面"概念（配置靠环境变量）；doorman 的"管理面/数据面分离 + 多协议 + Web 控制台"是主项目网关演进（尤其多协议/可视化管理）的可借鉴架构。

## 61. pipecat — ◐ 实时语音/多模态 agent 框架（Python）

- 是什么：开源 Python 框架：构建实时语音与多模态对话 agent，支持语音助手、多 agent 系统（总线协调）、音频/视频/AI 服务/传输管线编排。
- 解决什么：实时语音/视频对话类 agent。
- 对主项目价值：②多模态音频域；主项目是图像+文本，语音对话是潜在扩展方向；其管线/总线架构可参考。

## 62. AutoHedge — ○ 自主 agent 对冲基金

- 是什么：企业级自主 agent 量化交易基金（Solana 全自动交易，swarm 智能 + 风险优先架构）。
- 解决什么：AI 自动交易。
- 对主项目价值：无关（量化交易域）。

## 63. katana — ◐ 下一代爬虫/爬网框架（Go）

- 是什么：projectdiscovery 的 katana：下一代 crawling/spidering 框架（Go），高速网页/API 爬取，常用作攻击面/侦察。
- 解决什么：高效爬取站点与 API。
- 对主项目价值：⑤安全/侦察域；主项目 proxy_pool/cf_solver 涉及访问外部站点，katana 的抓取能力可参考（非核心）。

## 64. codeg — ◐ 多 agent 编码工作区（桌面+服务器+移动端）

- 是什么：聚合所有 agent CLI 会话到一个可搜索工作区，主 agent 可把任务委托给其他类型的 sub-agent；任务进 todo board 各自分支无人值守跑、待审后合入；桌面 app/独立服务器/Docker + iOS/Android，内置 15 个 agent，支持任意 ACP agent。
- 解决什么：一站式运行/管理/委托多编码 agent。
- 对主项目价值：④+①域；其"任务委托 + 分支隔离 + 多端"产品形态是主项目 agent 任务管理/前端可参考的完整样例。

## 65. open-steps — ◐ 面向人的 agent 开发 skills 集

- 是什么：一系列 skills：把开发过程开放给运行它的人（会话、决策、下一步都用自然语言），面向非工程师的 vibe coding 辅助。
- 解决什么：让 agent 开发过程透明、可控、可接续。
- 对主项目价值：①skills 工程；其"过程可见性"主张与主项目 SSE 事件流/任务审计理念一致，skills 写法可参考。

## 66. .claude — ○ 空目录（占位）

- 是什么：参考项目根下的 `.claude/` 目录，当前为空（可能为 git 占位/遗留，未发现规则或配置内容）。
- 解决什么：无。
- 对主项目价值：无。无需处理。

## 67. maestro — ◐ 多模型任务分解编排（经典参考）

- 是什么：经典 Python 脚本：用 Opus（规划）+ Haiku（执行）把目标拆成子任务、执行、再合并成连贯结果；已支持 LiteLLM 多 API（Anthropic/Gemini/OpenAI/本地）。
- 解决什么：两层模型分工的任务分解-执行-合成。
- 对主项目价值：主项目 agent 化（意图识别/DAG）的概念先驱；其"规划模型+执行模型分层"与主项目多 agent 分工一致，可作教学参考。

## 68. max-sixty__worktrunk — ◐ git worktree 管理器（Rust）

- 是什么：最流行的 git worktree 管理器（Rust）：快速创建/管理并行工作树，编码 agent 工作流常用隔离。
- 解决什么：并行分支/多 agent 隔离开发。
- 对主项目价值：主项目多 agent/桌面自升级涉及工作区管理，worktrunk 可作为 agent 隔离执行的环境工具参考。

## 69. QuantMind — ○ 量化投研平台

- 是什么：AI 原生量化大脑：13 种模型工场、因子自主进化、QMT/通达信实盘、多市场量化投研平台。
- 解决什么：工业级量化研究与实盘。
- 对主项目价值：无关（量化交易域）。

## 70. edgequake-edgequake-main — ★ Rust Graph-RAG 框架

- 是什么：高性能 Rust Graph-RAG 框架：文档→智能知识图谱→更优检索与生成，含 Sigma 图查看器，PDF/嵌入安全限制完善。
- 解决什么：高吞吐、低资源地把文档变成可检索知识图谱。
- 对主项目价值：与主项目记忆/知识检索同域；若主项目记忆巩固要升级为图谱检索，Rust 高性能 Graph-RAG 是候选底座（对比 graphiti 的图数据库方案）。

## 71. soul-sol__claude-md-patterns — ★ CLAUDE.md 可绑定规则模式

- 是什么：skill：给出"真正绑得住"的 CLAUDE.md 规则四件套——Trigger（触发条件）/Check（可 grep 的检查）/Stop condition（明确 ABORT）/Evidence（留证据），规则可被机器验证。
- 解决什么：解决 CLAUDE.md 规则"读了不执行"的问题——不可检查的规则等于没有规则。
- 对主项目价值：主项目 CLAUDE.md/rules 体系庞大，其"可验证规则 + 证据留存"模式可直接改进主项目规则质量与 agent 执行力（把规则变断言）。

## 72. vps-audit — ◐ VPS 安全审计脚本

- 是什么：单个 Bash 脚本对 VPS 做安全+性能审计（SSH 配置/root 登录/密码认证等），输出带建议的报告。
- 解决什么：快速检查 VPS 安全基线。
- 对主项目价值：⑤安全域；主项目部署环境（若自建 VPS）可参考其检查清单，属运维安全小工具。

## 73. sopaco__deepwiki-rs — ◐ AI 仓库文档生成器（Rust，DeepWiki 类）

- 是什么：高性能 AI 驱动的智能文档生成器（DeepWiki-like，Rust）：自动为任意代码库生成高质量 Repo-Wiki，含 skills。
- 解决什么：一键生成可读的仓库文档/架构 wiki。
- 对主项目价值：⑤文档工程；主项目有 docs/ + 计划书，deepwiki-rs 可作为"自动生成项目文档/wiki"的工具参考（低成本提升文档维护效率）。

## 74. paper2code-main — ◐ 论文→引用锚定实现（skill）

- 是什么：skill：输入 arxiv URL → 输出 citation-anchored 实现（代码按论文章节标注来源 + 复现笔记）。
- 解决什么：让论文复现可溯源、可验证。
- 对主项目价值：①skills 工程；"代码-文献引用锚定"模式可参考（主项目若引入新算法/方法时规范复现），价值一般。

## 75. claude-devtools — ◐ Claude Code 调试工具（桌面）

- 是什么：Electron 桌面工具：读取 Claude Code 本地日志，可视化会话记录、检查工具调用、跟踪 token 用量——"让你看到 Claude 做了什么"。
- 解决什么：agent 行为黑盒问题——本地日志的可视化调试。
- 对主项目价值：主项目有 SSE 事件流/任务审计 + 桌面 sidecar；其"会话日志可视化 + token 用量"交互可参考进主项目管理面板 Logs 页（主项目已有 Logs 页，可对比增强）。

## 76. MaxHu-xuan__chat-archive-guard — ○ 聊天归档只读守护

- 是什么：Python 工具：对聊天导出做本地只读检查（隐私/敏感/合规）后再保存/迁移/共享。
- 解决什么：防止聊天导出泄露敏感信息。
- 对主项目价值：低相关（隐私检查域），其只读扫描思路可参考主项目日志脱敏/数据治理。

## 77. lemoncrow-lab__lemoncrow — ★ 上下文工程运行时（本地代码图+精确读）

- 是什么：运行在 Claude Code/Codex 等之下的上下文工程层：本地代码图、精确范围读取、有界输出、持久记忆、已验证运行时控制；全本地免账号；号称检索 MRR 比 ripgrep 高 ~1.9x、SWE-bench 输出 token 少 27.9%。
- 解决什么：让 agent 读得更少、输出更少且不失正确性——上下文工程量化优化。
- 对主项目价值：与主项目 codegraph/graft/上下文工程同域，且带**量化基准**（tool calls -37.8%、token 减少）；主项目 graft 用法可对照其收益测量方法验证自身效果。

## 78. VCPToolBox-main — ○ VCP 聊天桌面客户端

- 是什么：为 VCP（Variable & Command Protocol）服务器打造的 AI 聊天桌面客户端（含壁纸包/音频解码包）。
- 解决什么：VCP 协议下的 AI 聊天 UI。
- 对主项目价值：无关（私有协议客户端），其聊天桌面 UI 可作参考。

## 79. langflow — ★ 可视化 agent/工作流构建平台

- 是什么：可视化拖拽构建 + 部署 AI agent/workflow 的平台：视觉编排、内置 API + MCP 服务器（工作流即成工具）、支持主流 LLM/向量库/AI 工具，batteries included。
- 解决什么：让非工程师也能搭 agent 工作流，且每个工作流可当 API/MCP 工具被外部应用调用。
- 对主项目价值：主项目有自研 DAG 编排 + MCP 服务端；langflow 的"可视化编排 + 工作流即 MCP/API 工具"产品形态是主项目 DAG 编排可视化与管理面板的成熟对标（可评估借鉴其节点/边模型与执行引擎）。

## 80. remnic — ★ 本地优先跨 agent 记忆（markdown 文件 + 混合检索）

- 是什么：本地优先记忆：每条记忆是带 YAML frontmatter 的 markdown 文件；一个存储多 agent 共享（Claude Code/Codex/Cursor/OpenClaw 等 + 任意 MCP client）；自动提取/蒸馏/回注；混合检索（BM25+向量+重排）+ 图谱召回 + 记忆价值打分 + provenance。
- 解决什么：让所有 agent 共享同一份可 `cat`/`grep`/版本控制的记忆，自动蒸馏与精准召回。
- 对主项目价值：与主项目记忆巩固/OpenWolf 体系同域；其"markdown 即记忆 + 混合检索 + 价值打分"与主项目 .wolf 记忆（文档型）理念一致，检索增强（重排/打分/provenance）可借鉴。

---

## 汇总

### 高价值对标（★，建议优先深读）
| 项目 | 主项目对应点 |
|---|---|
| **OmniRoute** | 网关/路由/免费 provider 聚合/fallback/token 压缩/审计——头号对标 |
| **cc-switch** | Tauri2 桌面 + 多 provider 切换管理 |
| **semantix** | 语义缓存/自适应调度/预取——预算门禁外的省钱维度 |
| **mnemosyne** | SQLite 零云记忆层——技术栈与主项目完全一致 |
| **graphiti** | 时序知识图谱记忆层（记忆巩固升级方向） |
| **semantica-agi** | 上下文图 + 决策 provenance |
| **OpenLore** | 确定性记忆 + 变更守卫（无 LLM 热路径） |
| **sandbox-runtime** | OS 级沙箱（cf_solver/agent 进程隔离） |
| **SafeLine** | WAF（网关前置防护） |
| **doorman** | API 网关控制平面（管理面/数据面分离） |
| **atlas** | agent checkpoint 溯源（会话↔变更↔记忆） |
| **reef** | 自改进 agent 闭环（harness 级学习） |
| **EverOS-main** | 长时记忆方法 + 基准（EverMemBench 可评估主项目记忆） |
| **hyperresearch** | 深度研究管线 + 源 vault |
| **ripwire** | 确定性调用图 + 受影响测试推荐 |
| **lemoncrow** | 上下文工程量化基准（对照验证 graft 效果） |
| **langflow** | 可视化 DAG 编排 + 工作流即 MCP/API |
| **OpenBot** | 可信 agent 隔离身份 + 审批 + 审计 |
| **edgequake** | Rust Graph-RAG（图谱检索底座候选） |
| **claude-md-patterns** | CLAUDE.md 可验证规则（Trigger/Check/Stop/Evidence） |

### 图像生成域资产（②低成本高契合）
- **handraw-style**（216 种手绘风格提示词库，可直接做风格库功能）
- **imgcompress**（生成结果后处理：压缩/格式转换/抠图）
- **awesome-generative-ai-apps**（图像/电商类 SaaS 端到端模板）

### 明确无关（○，一句话定位即可）
meetily（会议助手）、netwatch（网络监控）、FreeToken/Magnitude（本地推理）、AutoSeg-SAM2（视频分割）、robin/GhostTrack（OSINT，涉敏感域）、AutoHedge/QuantMind（量化交易）、hermes-venice-web（web 搜索插件）、awesome-autoresearch/awesome-claude-code/awesome-system-prompts/awesome-autoresearch（清单类）、VCPToolBox（私有协议客户端）、.claude（空目录）、chat-archive-guard（聊天归档检查）。

### 备注
- 全组未发现需要安装/运行/联网验证的内容，纯静态识别；判定依据全部来自 README 首部 + 目录结构。
- 涉及敏感/争议域（robin 暗网 OSINT、GhostTrack 位置追踪）仅记录定位，不建议引入。
