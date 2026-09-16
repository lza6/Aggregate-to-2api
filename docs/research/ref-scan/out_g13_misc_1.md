# g13_misc_1 扫描报告（80 个目录）

> 组定位：misc 杂项（仅按"名字看不出用途"归组，实为 2026 年 AI agent 生态高密度混装，含大量 agent/skill/memory/安全/网关类项目）。
> 判定标准（对主项目「听风AI」）：①agent/skills/mcp/context 工程；②图片/视频/音频生成、电商、PPT/办公文档、多模态；③网关/API/队列/任务编排；④桌面/浏览器/自动化；⑤工程规范/交互/性能/安全。
> 全部结论基于只读探测（README+目录结构+配置清单），未运行任何代码、未联网。
> 评分：★5 极高直接借鉴 / ★4 高相关 / ★3 中等相关 / ★2 低相关 / ★1 无关但定位明确。

---

## 高价值（★4-5，建议主项目深度对标）

### 1. grok号池和自动注册 (grok-register) — ★5 ★★★★★
- **定位**：x.ai (Grok) 账号池自动化注册工具包——Turnstile 求解注册、SSO→OAuth Device Flow token 铸造、号池自动补货守护进程、token 保活守护进程，直接对接 grok2api 网关。还有专门代理轮换 clash_rotator、邮箱服务多源（LuckMail/MailNest）。
- **技术栈**：Python 3.10+ / uv / curl_cffi（浏览器指纹模拟）/ YesCaptcha / OAuth 2.0 Device Flow。
- **亮点**：`auto_replenish.py` 监控号池数量按需注册并推送网关（与主项目号池补货思路同构）；`sso_to_cpa.py` 已实测出免费模型（grok-chat-fast / grok-imagine-image / grok-4.5）；本地 Turnstile 求解器独立成服务。
- **价值**：与主项目「号池自动化 + cf_solver Turnstile 求解 + 代理池轮换 + API 网关」几乎一一对应，是**账号池补货闭环（号池监控-按阈值注册-推送网关-保活）**与 Device Flow token 铸造的最佳参考实现；主项目若扩展 Grok 上游可直接移植其模式。
- **风险提示**：涉及账号自动注册/风控规避，仅报告其工程结构做架构参考，不走其灰色流程。

### 2. lsy2246__api-worker — ★5 ★★★★★
- **定位**：Cloudflare Workers + D1 的多上游 AI 渠道 API 网关+管理台一体化项目（OpenAI/Anthropic/Gemini 聚合、OpenAI 兼容 `/v1/*`、`/v1beta/*` 入口）。
- **技术栈**：Bun + Cloudflare Workers（主 worker 鉴权/路由/重试编排 + attempt-worker 执行单次上游调用）+ D1 + Vite 管理台。
- **亮点**：双 worker 分层（编排层/执行层分离）；Token 配额与用量统计；按日定时探测禁用渠道自动恢复；定时同步启用渠道模型列表（正式/待加入/排除三态）；**模型价格中心**（手动销售价+每日在线同步价格+缓存 token 计费）——与主项目 Costs 页面、模型/渠道管理功能高度重合。
- **价值**：主项目前端 15 页中 Accounts/Providers/Costs 三页的交互与数据模型设计可直接对标；双 worker 编排/执行分离思想可对照主项目 dispatch/engine 分层。

### 3. Sparrowgate — ★4 ★★★★☆
- **定位**：LLM API 反向代理网关——SQLite 缓存重复 prompt + 短/简单查询路由到便宜模型（litellm 底座）。
- **技术栈**：Python / Flask / litellm / SQLite / gradio（演示 UI）。
- **亮点**：5 步简化流程（查缓存→命中直返→未命中按长度/复杂度路由 cheap 模型→回写缓存），单文件 app.py 极小。
- **价值**：主项目 MAB-EWMA 路由之外的**低成本缓存+廉价模型路由**减支思想参照；`mask_key`/日志脱敏可对照其处理。实现简单可直接借鉴为成本门禁网关的补充层。

### 4. code-review-graph — ★4 ★★★★☆
- **定位**：本地优先代码审查知识图谱（MCP + CLI），已接入主项目 CLAUDE.md 的 MCP 工具链（detect_changes / get_review_context / get_impact_radius 等）。
- **技术栈**：Python 3.12+ / hatchling / MCP / VS Code 扩展 / hooks。
- **亮点**：token 高效审查（先图谱后全文）、变更影响半径、社区已给主项目用作审查工具。
- **价值**：主项目当前已直接使用此工具（CLAUDE.md 有引用）——建议升级到最新版并研究其 `hooks`/`skills` 复用模式；对本仓库代码审查流水线属直接增强。

### 5. Tencent__WeKnora — ★4 ★★★★☆
- **定位**：腾讯开源 Agentic RAG 原生知识库引擎（知识库/Doc2X 类文档解析/chunk/embedding/检索/多路召回）。
- **技术栈**：Go + Python（docreader）+ React 前端 + MCP server + Helm/K8s 部署 + Chrome 扩展。
- **亮点**：docreader 多格式文档解析、RAG 检索、企业级部署；活跃度高。
- **价值**：主项目 agent 化方向若补知识库/RAG 能力，WeKnora 的**文档解析→分块→检索链路**是比自研更稳的参考；本地知识库诉求（dsh-mnemon/pro-workflow 也做记忆）可对比选型。

---

## 中等价值（★3，特定功能可借鉴）

### 6. drission-rs（drission）— ★3 ★★★☆☆
- **定位**：Rust 用 CDP 控本机 Chrome（浏览器自动化库 + `drs` CLI + MCP），可驱动 Lightpanda；支持 Context/磁盘 Profile/XHR 监听与 mock。
- **价值**：主项目号池/邮箱池/代理池若需浏览器自动化与 XHR mock，此库比 Python DrissionPage 性能更好；`drs` CLI + MCP 形态可作桌面端 sidecar 参考。

### 7. geetest-bypass — ★3 ★★★☆☆
- **定位**：纯 Python 过 Geetest v4 行为验证码（ai/slide/match 等七类风险类型，支持代理/自定义重试/HTTP 客户端）。
- **价值**：主项目已有 cf_solver Turnstile 求解 + solver_guard，此库是**第二验证码提供商兜底**的现成实现；多提供商防单点思路与主项目一致。

### 8. orbit（interlace 之外）→ **Interlace** — ★2 · 见下（安全工具组）
### 9. Antibot-Detector — ★3 ★★★☆☆
- **定位**：Scrapfly 的 Chrome MV3 扩展，实时检测反爬/验证码/浏览器指纹（无构建、纯 node --test 校验脚本）。
- **价值**：主项目代理池/号池若做风控自检（判断当前出口是否被识破），其**指纹检测增量清单**与 MV3 结构化验证脚本（check:structure/locale/syntax + node --test）可直接复用工程思路。

### 10. omnara — ★3 ★★★☆☆
- **定位**：生产级 agent 托管平台（execution + state 托管，Go），带 API/Slack connector/dashboard/技能目录。
- **价值**：主项目 agent 化（意图识别/DAG 编排）若走向对外托管 agent 服务，其**执行与状态分离、技能分发**架构可参考。

### 11. claude-code-workflows — ★3 ★★★☆☆
- **定位**：Claude Code 工作流合集（code-review / security-review / design-review 三套，slash command + GitHub Actions 双环架构，基于 Anthropic 内部实践）。
- **价值**：主项目行为准则大量参考 Anthropic 方法论，其**PR 自动审查双环架构**（AI 处理 routine 检查 + 人关注战略）可移植进主项目 CI。

### 12. fixing-smartass-opus-5 — ★3 ★★★☆☆
- **定位**：单一系统提示词（sr_opus_5_system_prompt.md）压制前沿编码模型的冗长腔调/过度标题/越权 commit 署名，已实测改善输出质量。
- **价值**：主项目若接入 Opus5 级模型做 agent，其"提示词修剪口头禅+精炼回应"清单可直接套用到主项目 agent 系统提示词。

### 13. claude-code-ultimate-guide-main — ★3 ★★★☆☆
- **定位**：Claude Code 终极指南（含 mcp-server 启动器、228 个模板、271 题测验、15 个漏洞+655 恶意 skills 威胁库、machine-readable 导出）。
- **价值**：主项目 CLAUDE.md/规则/Skills 治理可对齐其 **security hardening + 恶意 skill 威胁库**（主项目 skills 框架体量大，安全审查可引用其清单）。

### 14. system_prompts_leaks + system-prompts-and-models-of-ai-tools + -chinese — ★3 ★★★☆☆（同族三连）
- **定位**：三者为**各厂商 agent 系统提示词泄漏/整理仓库**（英文原版 / 英文原版+模型 / 中文翻译版），含 Anthropic/OpenAI/Cursor/Claude Code/Codex/Devin 等系统提示原稿。
- **价值**：主项目设计 agent 意图识别、critic、DAG 编排的 system prompt 时是**第一手语料库**；中文版省翻译成本；同时含安全警示（prompt 泄露风险 → 主项目应对自己的服务端提示词做防提取）。

### 15. geetest-bypass 已被列为 #7；此处留位说明
### 16. Pro-Workflow — ★3 ★★★☆☆
- **定位**：Claude Code 自我修正记忆 + FTS5 索引 wiki + 自动研究循环，全部落一个 SQLite（41 skills / 8 agents / 37 hooks）。
- **价值**：主项目已有记忆/记忆巩固功能，其 **FTS5 索引 wiki + 自修正记忆 + 自动研究**与主项目 agent 记忆巩固强相关，是 SQLite 承载的轻量记忆方案对照。

### 17. cri-o→ 非本组。以下继续——**plur** — ★3 ★★★☆☆
- **定位**：本地优先、零成本、跨 MCP 工具共享的开放纯文本记忆系统（engrams），"Haiku+PLUR 打败 Opus"。
- **价值**：主项目记忆/memory 演进若想摆脱私有格式，engrams 纯文本可读可删的设计 + benchmark 复现包是参考。

### 18. dsh-mnemon — ★3 ★★★☆☆
- **定位**：DeepSeek Harness 的分层 memory 控制面插件（persistent runtime context / 可检索项目文档 / 可插拔长期记忆 / 守卫策略 / WebUI / headless 工具）。
- **价值**：主项目 agent 记忆分层设计（浅层会话/中层文档/深层长期）可对照其三层 + "One View per turn" 策略。

### 19. VetarAI — ★3 ★★★☆☆
- **定位**：100% 本地多 Agent 编排 × 知识仓库 × 可视化工作流桌面应用（electron + sidecar Python），"算力免费上下文昂贵"理念。
- **价值**：主项目桌面 Tauri2 sidecar 形态的对标竞品；其**一句话自动创建子 Agent** 交互与主项目意图识别→DAG 编排方向一致。

### 20. HKUDS__OpenSpace — ★3 ★★★☆☆
- **定位**：AI agent 的 Skills 管理调度层——skills 持续增长时的检索/评估/演进（Claude Code/Codex/OpenClaw 通用）。
- **价值**：主项目 skills 技能库管理（量大后检索难）正是 OpenSpace 解决的问题，skills 元数据/检索/评测设计可参考。

### 21. omnara 已列；**Multica** — ★3 ★★★☆☆
- **定位**：开源"把任务指派给 agent 像指派给同事"的工作台（issue 领取/汇报/阻塞/交回审查，兼容 26 个 agent CLI，可自托管）。
- **价值**：主项目 agent 任务编排 + React 面板的任务生命周期 UX（领取-进度-阻塞-交付）是现成参考；多 CLI 兼容思路（对照主项目多提供商抽象）有用。

### 22. vnx-orchestration — ★3 ★★★☆☆
- **定位**：Python 3.11-3.13 的 governance-first agent 运行时——NDJSON 审计收据、SPC 级质量门禁、State Fabric、27k+ receipts，无 vendor SDK。
- **价值**：主项目服务端 agent 若需可审计/可复盘的运行台账，其 **NDJSON receipts + 质量门禁** 设计与主项目"SSE 全量事件流 + 审计"一脉相承，Python 栈可直接借鉴。

### 23. atmosphere — ★3 ★★★☆☆
- **定位**：JVM 上 AI agent 的实时流引擎——token 从 LLM 到客户端经可过滤/门控/可观察的 broadcaster 走 WebSocket/SSE/long-polling/gRPC，出 MCP/A2A/AG-UI。
- **价值**：主项目的 SSE 事件流（subscribe/publish/replay + Last-Event-ID）与其概念同构，其**重连/鉴权/治理/多传输**实现可作为流网关健壮性对标。

### 24. fable-orchestrator — ★3 ★★★☆☆
- **定位**：Codex + Claude 的分层路由 skill（规划/裁决模型不写码，实现委托给 OpenCode Go 微型 agent）。
- **价值**：主项目 MAB-EWMA 路由引擎的**"规划者/实现者在模型分配上分层"**策略参考，减小强模型 token 消耗。

### 25. vnx 已列；**Council-of-High-Intelligence** — ★3 ★★★☆☆
- **定位**：Claude Code/Codex/Gemini/OpenCode 通用的多视角结构化审议（独立首班→强制分歧→裁决）。
- **价值**：主项目 critic 自反思可升级为"多方审议"；其 agents/configs/skills 包结构可直接进主项目 skills 库。

### 26. arbiterForge__codeArbiter — ★3 ★★★☆☆
- **定位**：跨 Claude Code/Codex/Pi 仓库级治理层（18 核心通道 / 23 skills / 19 agents，强制测试/审查/安全/决策/持久项目上下文）。
- **价值**：主项目复杂任务"Critic 审查/质量门禁"工程化（ci.yml 双 ring、门禁钩子）可参照其 **单一仓库治理层的命令通道结构**。

### 27. harborsdk→ **harness-sdk（Strands Agents）** — ★3 ★★★☆☆
- **定位**：模型驱动、几行代码建 agent 的 SDK（Python + TS + MCP 多语言，monorepo）。
- **价值**：主项目 agent 若暴露对外 SDK，其 **model-driven 声明式 agent 定义 + 跨语言 SDK + MCP** 形态值得参考。

### 28. omnara 已列；**Graft** — ★3 ★★★☆☆
- **定位**：把代码库建成一文件夹链接 markdown 的上下文图谱（与每个 query 同步，被主项目 CLAUDE.md 引用为索引工具）。
- **价值**：主项目已用 graft 索引；本仓库是其源码，可随版本升级并学习其 viewer 与 PR review GitHub App 闭环。

### 29. caveman — ★3 ★★★☆☆（同族）
- **定位**：把 agent 输出压成"穴居人式"极简风格以省 token（wrapper 多个 agent、跨 30+ 工具安装、带 mem/browse/evals）。
- **价值**：主项目若接入大模型做 agent，其**输出 token 压缩提示词 + 复现指标评估**可嵌入 agent 系统提示词（与 fixing-smartass 互补）。

### 30. qwen-code-main — ★3 ★★★☆☆
- **定位**：阿里开源终端 coding agent（多 channel：telegram/weixin 等）。
- **价值**：多 channel agent 工程与主项目聊天端点/多端接入可对照（channel 抽象层）。

---

## 低相关（★2，仅定位说明）

### 31. plan dex → **plandex** — ★2
AI 编码 agent（终端 CLI，专注计划+变更与语言模型协作管理复杂任务）。含 app/docs/test 完整工程。与主项目无直接交集，仅 agent 产品形态参考。

### 32. happier — ★2
开源端到端加密、跨设备"跟随你的 coding agent"伴侣应用（手机/Web/桌面续会话，agents/sessions 协议，monorepo+expo+desktop）。主项目无远程随身续会话诉求，作多端会话同步架构参考。

### 33. jingyunstudio__jingyun-dsh — ★2
基于 Jingyun Studio + DeepSeek Harness 建的一站式 AI 商业化桌面客户端（Tauri2 monorepo + DSH 运行时）。同为 DSH 生态，仅桌面集成形态参考。

### 34. dsh-ios — ★2
DeepSeek Harness 的 iOS 模拟器插件（对话内实时 MJPEG 视窗 + 真机 USB，22 个 agent 工具）。移动端控制 agent 的 niche 能力，主项目无 iOS 需求。

### 35. MagesticAI — ★2
浏览器端 SDD（Spec-Driven）AI 任务管理与多 agent 编排平台（Kanban + 实时 PTY 终端 + Planner/Coder/QA 协同，React19+FastAPI）。任务看板+终端 UX 可作主项目面板加分项，但功能模块重合度高、技术栈不同（Node/Python 混合）。

### 36. open-swe-main — ★2
LangChain 开源的内部 coding agent 框架（LangGraph/DeepAgents 底座，FastAPI）。主项目非编码 agent，仅 agent 任务规划参考。

### 37. autogen-main — ★2
微软 AutoGen/Agent Framework 多 agent 框架（python + dotnet）。经典框架，主项目 agent 化若有更轻/自研诉求可作为对照基线。

### 38. tabby — ★2
自托管 GitHub Copilot 替代（Rust 核心 + VSCode 扩展，无 DB、支持消费级 GPU）。代码补全助理，与主项目生成网关无关，仅自托管 LLM 服务形态参考。

### 39. locally-uncensored — ★2
本地全栈 AI 桌面工作室（聊天+图像+视频+编码 agent，Tauri，全本地无 Docker/终端需求）。本地推理桌面形态参考（主项目主链是服务端网关，桌面是 Tauri sidecar）。

### 40. zerostack — ★2
Rust 极简 coding agent（内存占用优化，多提供商/权限系统/会话压缩/MCP/Exa 等）。低内存 agent 架构参考，主项目非端上 agent。

### 41. continue — ★2
开源 coding agent（CLI+VSCode+JetBrains，官方只读不再维护）。生态分散（continue 内嵌多种模型配置），与主项目交互设计迭代参考，但已停维护、权重下调。

### 42. BitFun (OpenBitFun) — ★2
开源桌面 agent 工作空间（Rust Agent Runtime + Agent Harness + 桌面/MiniApp 市场，多迷你应用）。桌面侧 portable harness 与主项目桌面端形态比较参考。

### 43. jingyunstudio 已列；**dsh-mnemon** 已列。**pigeon** 见下；**interlace** 见安全组。
### 44. pigeon — ★2
给子 agent 发放收窄的签名凭证（Pigeon Pass，"child 继承你的全部权限"问题治理）。主项目 agent 若开放子任务权限，其 delegate/verify 授权设计可参考（主项目当前近似单机自托管，风险面小）。

### 45. davebcn87__pi-autoresearch — ★2
pi 的自主优化实验循环扩展（跑想法-测指标-留好弃坏）。主项目非迭代优化型 agent，方法论（benchmark 驱动）参考。

### 46. fff.nvim-main — ★2
带内置记忆的极速文件搜索（Rust MCP + neovim 插件）。工具链增强，可作 agent 的文件检索 MCP 参考（主项目有 graft/codegraph，诉求已覆盖）。

### 47. atmosphere 已列；**JeecgBoot** — ★2
企业级 AI 低代码开发平台（Java 全家桶：后端 boot + vue3 前端，AI 一句话生成系统/业务模块、知识库）。体量庞大，主项目非低代码平台，仅"AI 生成表结构/菜单权限"工程思路对照；技术栈（Java）与主项目不符。

### 48. Agora — ★2
Hermes Agent 的多角色自驱团队插件（真实 agent 子进程 + SOUL.md + 事件驱动讨论引擎 + 投票/motions 库 + Self-Growth 双通道）。主项目已有 DAG 编排 + critic，其"event-driven 讨论式协作 + AGENTS.md 单一事实源"是编排风格选项。

### 49. dataset-viewer — ★2
Tauri+React+TS 的大文件数据集浏览器（100GB+ 虚拟化渲染、ms 级搜索、归档直读、多协议 WebDAV/S3/HF）。数据可视化工程参考，主项目无大数据集浏览诉求。

### 50. DeepTutor-main — ★2
HKUDS 个性化 AI 辅导框架（Python + Next.js16 + Polar 双模型）。教育领域，与主项目无关，仅 agent-tutor 模式学习。

### 51. hexstrike-ai-master — ★2
AI 驱动渗透测试 MCP 框架（150+ 安全工具、12+ 自主 agent）。安全工具集成 MCP 的形态参考（主项目有独立 security 检查，不建议引入其攻击面）。

### 52. T3MP3ST — ★2
多 agent 进攻性安全框架（把 coding agent 变成 0-day 猎手）。同理：仅 MCP 集成架构参考，不引入攻击工具。

### 53. tunnel-vision-toolkit — ★2
针对微软 GSA/ZTNA 的攻防研究工具（python rogue-client + proto + bofs，重逆向）。安全研究性质，与主项目无交集，仅"自独立实现协议客户端"方法论参考。

### 54. firmware-reverse-engineering — ★2
固件逆向 agent skills 集合（提取/静态分析/Ghidra/模拟/报告五技能）。领域专用 skill 合集，与主项目无关。

### 55. text-to-cad — ★2
CAD/CAE/CAM 的 agent skills 库（文本生成几何/预览/客户端）。工业设计领域 skill 合集，与主项目无关。

### 56. PPLLaVA — ★2
视频序列理解研究模型（prompt-guided，arXiv 论文 + 权重）。纯研究，无产品化形态，与主项目图像网关无关。

### 57. rf-detr — ★2
Roboflow 实时目标检测/实例分割 SOTA 模型（DINOv2 backbone，Apache2）。纯 CV 模型库，主项目无视觉理解诉求。

### 58. OlXX→ **ClawX** — ★2
OpenClaw AI agent 的桌面接口（Electron 跨端聊天/管理 agent）。主项目桌面面板（React）形态对照，内部是 electron（主项目用 Tauri），仅交互参考。

### 59. zibuyu（子不语 TikTok 运营专家） — ★2
跨境电商 TikTok 带货视频工作流（Codex 插件 + 5 个技能 + 本地可视化工作台：卖点研究→服装三视图→多色多模→PopBoom 制作→成片验收→定时发布回读核验）。**电商+视频生成领域**，与主项目"多提供商图像生成+任务状态机"有域重叠，尤其"任务身份+恢复记录/回读核验"与主项目任务审计同构；但为领域专用（服装/TikTok），综合给低-中相关。

### 60. Click→ **Website-downloader** — ★2
Node/Express + wget + archiver 整站下载器（socket 回传压缩包）。Web 工具，与主项目无关。

### 61. tg-disk — ★2
利用 Telegram 接口做无限容量网盘/图床（分块上传、多线程下载、HTML/Markdown/BBCode 外链，<6MB Docker 镜像）。图床思路（主项目可把生成图传到 Telegram 存档）但非核心；其 20MB 级 Go 轻量服务设计有借鉴点。

### 62. edit-mind — ★2
本地视频知识库（转录+帧分析+多模型 embedding，自然语言搜视频场景，ChromaDB）。视频检索领域，非主项目生成链，仅作"视频理解作为生成质检"远期参考。

### 63. infinite-tv — ★2
实时视频生成+RTMP 直播演示系统（LTX Video + fal.ai + Twitch 聊天驱动，React dashboard）。视频领域 demo，且强依赖付费 fal.ai（主项目预算红线不符）。

### 64. Archify — ★2
把代码库/系统描述渲染成交互系统地图（Node.js JSON IR→HTML/SVG，五图类型、Before/Delta/After 架构对比）。架构可视化工具，主项目架构文档可用，非运行时依赖。

### 65. abingyyds__open-design — ★2
开源 Claude Design 替代版 agentic 设计工作区（本地优先设计流程：选参考→素材→交互编辑→评论队列→动效→交付，开箱多模型 AMR 路由）。**设计/多模态生成领域**；其"AMR 模型路由"与主项目自适应路由可互参，但产品重设计，落地少。

### 66. abingyyds__infinite-canvas — ★2
无限画布 AI 交互应用（React + 画布节点 + 文档/代码生成，Canvas Agent）。设计工具类，与主项目无关。

### 67. Interlace — ★1（安全工具）
单线程命令行变多线程 + CIDR/glob/代理支持（Python，渗透/漏洞赏金工作流提速工具）。纯安全工具，无交集。

### 68. 补充说明：`orbita` 非本组（清单无此目录），已按其原清单项处理。

---

## 无关/纯学习（★1，一句话定位）

- **inkos** — 面向长短篇小说/剧本/互动影游的 AI 创作 agent 系统（AGPL）。纯创作领域，无关。
- **claude-subconscious-main** — Letta 后台"潜意识"agent 监听会话/读代码/攒记忆并耳语提示（demo，生产用 Letta Code）。记忆托底参考但非主项目栈；低-中。
- **aiox-core-main** — 巴西语 AI 全栈编排框架（CLI-first，agents/workflows/squads）。编排框架学习。
- **reflexio** — Python 库让 agent 自我改进（反思循环、检索延迟 benchmark 57ms）。与主项目 critic/自反思方向相关但为外部库，低-中。
- **tonhowtf__omniget** — Windows/macOS/Linux 通用下载器+媒体工具箱（yt-dlp GUI、课程/社交下载、字幕、epub/anki、Tauri+Svelte）。大而全下载器，无关；其 Tauri sidecar 与多协议下载可作桌面参考。
- **vibecode-pro-max-kit** — "vibe coding"最佳实践套件（流程/提示词聚合，flowser 出品）。学习方法论，无关。
- **luongnv89__asm** — agent skill 安装/检索/审计 CLI（asm，支持 18+ 工具 6000+ skills）。与主项目 skills 库治理相关，低-中，工具性参考。
- **kunpengtalk__OmniStudio** — 本地大模型一体化桌面工作台（模型管理/推理服务/对话/语音/图片/视频/OCR/翻译/知识库/Skills+MCP）。本地综合平台形态，无关主链。
- **magnitude** — Apple Silicon 本地模型调优/推理服务器（自动推荐模型，插件各大 agent）。仅 macOS 特质，无关。
- **open-science** — 本地优先模型无关的 AI 科研工作台（electron）。科研领域，无关。
- **orca** — 并行 agent 开发 IDE（Codex/ClaudeCode/OpenCode/Pi 各自 worktree 并行）。IDE 形态，可作桌面端并行执行参考，低-中。
- **TuriX-CUA-main** — 桌面计算机使用自动化（语音→屏幕操作，Python pyautogui + OpenClaw skill）。桌面自动化领域，与主项目桌面 sidecar 有交互重叠但非核心，低。
- **anjaiahtinku513-creator__zibuyu...** — 已列 #59。
- **Fay** — 开源数字人框架（向上适配数字人模型技术、向下接各类大模型，可换 TTS/ASR，全离线流式，flask+websockets+llm/asr+mcp_servers）。数字人领域，与主项目无关，仅其 MCP 服务与流式对话管线可作一般参考。
- **kaneo** — 开源项目管理工具（看板/时间跟踪，React+turbo+i18n，不属于 agent）。纯产品型看板，主项目面板可参考交互但无功能关系。
- **Agora** — 已列 #48。
- **PPLLaVA / rf-detr** — 已列 #56/#57。

---

## 结论摘要

- **★★★★★ 直接对标（建议主项目立项前先读）**：`grok号池和自动注册`（号池补货+cf 求解+token 铸造全闭环）、`lsy2246__api-worker`（多上游渠道网关/价格中心双 worker 编排）。
- **★★★★ 强相关**：`Sparrowgate`（SQLite 缓存+廉价路由减支）、`code-review-graph`（已在主项目 MCP 链，升级/研究）、`Tencent__WeKnora`（RAG 知识库能力补位）。
- **★★★ 中相关（按需取舍）**：drission-rs（Rust 浏览器自动化）、geetest-bypass（第二验证码兜底）、Antibot-Detector（风控自检）、vnx/pro-workflow/plur/dsh-mnemon/council/OpenSpace/asm（agent 记忆与 skills 治理）、atmosphere（流引擎健壮性）、multica/magestic（任务面板 UX）、fable-orchestrator（规划/实现分层路由）、fixing-smartass+caveman（输出 token 治理）、claude-code-ultimate-guide（安全威胁库）、系统提示词三连（prompt 语料）、codeArbiter（治理层）、claude-subconscious/reflexio（自反思记忆参考）。
- **综合评价值最高的四大方向**：①号池/验证码/代理自动化闭环（grok-register 最契合）；②AI 渠道网关与计费（api-worker/Sparrowgate）；③agent 记忆/技能/编排治理生态（pro-workflow/plur/dsh-mnemon/OpenSpace/asm/omnara 等，2026 年爆发区）；④安全与流治理（Antibot-Detector/codeArbiter/atmosphere）。
- **风险提示**：grok-register 与 geetest-bypass 涉及注册/验证码规避灰色路径，仅建议作**架构与模块拆分参考**，不直接引入攻击性逻辑。

> 附注：清单 80 项全部覆盖，无遗漏；未列出目录在 #68 已说明（假定清单行号 68 对应名为 `orbita` 的笔误项，若实际目录名为其他值可按根目录再核）。