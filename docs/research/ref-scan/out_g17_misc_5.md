# g17_misc_5 扫描结论（80 目录）

扫描方式：ls + README 前段 + 关键目录确认。只读分析，未修改任何文件。

**价值判断标准**：①agent/skills/mcp/context 工程 ②图片/视频/音频生成、电商、PPT/办公、多模态 ③网关/API/队列/任务编排 ④桌面/浏览器/自动化 ⑤工程规范/交互/性能/安全。★ = 疑似高价值，已深入确认。

---

## ★ 高价值（对标主项目「听风AI」）

1. **freellmapi** ★★★ —— 免费 LLM 聚合网关：34 家免费提供商 / 635 个免费模型端点聚合成单一 OpenAI 兼容 `/v1` API，含 key 加密存储、路由器按 free-tier 配额自动 fallback、每 key 用量追踪、自更新模型目录。与主项目「听风AI」的架构几乎同构（多上游聚合 + /v1 统一接口 + 配额/限流 + 号池思想），是**最强对标对象**：可迁移其免费额度聚合策略、配额计算、fallback 路由、密钥加密方案。
2. **litellm** ★★★ —— LLM 统一网关（100+ 模型 OpenAI 格式），业界事实标准。主项目网关层应长期对标：路由/重试/预算/密钥管理/mock 测试方法论均可参考，尤其其企业级 budget & rate limit 与主项目预算门禁是同一问题域。
3. **caura（原 MemClaw）** ★★★ —— 多租户多 agent 共享「治理化记忆层」：agent 写纯文本→转可搜索/治理/自改进记忆，含 MCP 集成。直接对标主项目 agent 化「记忆巩固」模块，记忆治理/多租户隔离是主项目缺失的能力。
4. **cocoindex** ★★★ —— 增量索引引擎（Rust+Python）：只重处理 Δ 增量、为 agent 提供始终新鲜的上下文 RAG 管道。对标主项目 context 工程：增量爬取/向量化/文档解析管道设计可直接借鉴。
5. **deepeval** ★★ —— LLM 评估框架（断言/指标/CI 集成，支持 Pydantic Agent 测试）。对标主项目 critic 自反思与 agent 质量评估：可给 critic 增加结构化指标而非纯文本反馈。
6. **graphify-3** ★★★ —— AI 编码 assistant 的 knowledge-graph 技能：读取文件构建知识图谱，19 语言 tree-sitter AST，多模态（代码/PDF/截图/白板照）。与主项目 codegraph/graft 同类，可直接借鉴其技能封装方式与多模态抽取管线。
7. **mempalace-main** ★★ —— 自述「benchmark 最高分」的 AI 记忆系统，Python 包 + hooks + benchmarks。对标主项目记忆巩固：其记忆架构/评分方法可参考，**需实测验证基准真实性**。
8. **memvid** ★★ —— 单文件、无数据库的持久化/版本化 agent 记忆层（Rust，瞬时检索+长期记忆）。对标主项目记忆巩固：轻量无 DB 方案可作为 SQLite 之外的备选，注意与项目 aiosqlite 技术栈差异。
9. **anything-analyzer** ★★ —— Electron+React 流量捕获逆向分析器：抓网页/桌面/终端/Python/移动端流量，AI 自动逆向工程（含报告）。对标主项目浏览器自动化/流量分析，对号池风控逆向有价值。
10. **prompt-optimizer** ★★★ —— 提示词优化器（Chrome 插件 + API + 前端全栈，中文团队），多策略 prompt 重写/评测。对标主项目 agent 意图识别与提示词工程：优化策略可直接复用。
11. **system-design-101** ★★ —— ByteByteGo 系统设计图解/资料库（交互式，Next.js）。对标主项目工程规范与架构文档：优质参考教材，可给主项目架构演进/评审提供素材。
12. **JIT** ★★ —— JIT-Agent 元代理：按任务即席生成「可执行 harness 包裹任意 agentic LLM」（Model-as-a-Harness，含 memory/planning/action/capability 四模块）。对标主项目 agent 编排：harness 生成思想可移植到主项目 DAG 编排层。
13. **openclaw** ★★ —— OpenClaw 个人 AI 助手（设备/聊天多渠道，custodian-skills、扩展）。主项目上下文多次提及 OpenClaw 生态（OpenMAIC/openclaw-to-hermes/OpenClaw 集成），其 skills 体系与多渠道是 agent 化参照。
14. **ZeroSlop** ★★ —— AI 写作「slop 检测器」技能：找 AI 腔措辞/机械节奏/空泛主张，守卫人名/数字/链接/引文。主项目引入 LLM 输出质量把关时可参考，纯文本技能轻量易迁移。
15. **aicheck** ★★ —— Rust 离线 AI 生成内容检测器（无 API key/无配置，多语言）。可作主项目内容审核/质量门禁的本地检测参考。
16. **semtools** ★★ —— Rust CLI 文档解析+语义搜索+AI ask（PDF/DOCX→markdown，本地多语种 embedding，工作区管理）。对标主项目文档/知识库处理工具链，Rust 性能参考。
17. **OpenKB** ★★ —— 开放 LLM 知识库：长文档规模、基于推理的检索、原生多模态、**无向量库**、Google OKF 规范。对标主项目 context/RAG：无向量库的检索方案是差异化参考。
18. **OpenContext (0xranx__OpenContext)** ★★ —— 给 AI assistant 持久记忆（Rust/TS + src-tauri 桌面 + MCP + iOS）。对标主项目记忆层 + 桌面端：MCP 服务端实现与多端记忆同步可参考。
19. **ccg-workflow-main** ★★ —— Claude+Codex+Gemini 多模型协作工作流（npm 包，139 测试，中文）。对标主项目多模型路由/agent 协作，工作流模板与测试方法论可参考。
20. **free-claude-code** ★★ —— 免费 Claude Code 替代客户端（Python，聚焦成本/网关），与主项目免费聚合定位同向。
21. **ENZO** ★★ —— 浏览器内 AES-256-GCM 加密密钥、服务端只做中继不存 key 的 LLM 网关。对标主项目安全：密钥本地加密 + 服务端零存储的中继架构值得借鉴，与主项目「密钥不落库」诉求一致。
22. **MoltBrain-main** ★★ —— OpenClaw/MoltBook/Claude Code 的长期记忆层（自动学习并召回项目上下文，含 plugin/schemas/migrations/templates）。与 caura/mempalace 同属「记忆层」对标集，其自动学习-召回机制与主项目记忆巩固模块直接相关。
23. **getpaseo__paseo** ★★ —— Paseo：本地优先/多语言（英日中韩）的 AI 学习或任务协作平台（docker + fastlane + nix 分发，monorepo）。与主项目交集一般，但其本地优先+多端分发工程值得扫读。
24. **tianrking__EdgeMirror** ★★ —— EdgeMirror：Cloudflare Worker 实现的无缓存只读网关镜像（35 个系统仓库 + 13 个开发适配器 + 48 配置），专为加速系统/开发源仓库访问。对标主项目 cf_solver/CF Workers 边缘能力与上游代理池思路，边缘只读网关设计可参考。
25. **Anything-Analyzer 已列。freellmapi 已列。**
23. **humanlayer__humanlayer** —— 仓库已废弃（README 声明全部 deprecated，迁移至 humanlayer.com）。低价值，仅留档。
24. **hermes-quota-plugin / llmquota** —— Hermes Desktop 配额状态插件 + 多 LLM 配额 TUI 管理器（Claude/Codex/Cursor/Hermes）。对标主项目号池/配额管理：配额窗口统计与 UI 展示可参考。

---

## 中价值（可局部借鉴）

25. **ApeAdmin** —— 面向 AI 应用的 100% 开源后台管理框架（Python3.11/FastAPI + Vue3.5，插件市场）。主项目 React 管理面板若考虑后台脚手架/权限体系可参考，但技术栈不同（Vue vs React）。
26. **x1xhlol__system-prompts-and-models-of-ai-tools** —— 海量 AI 工具 system prompt 与模型配置集（Amp/Anthropic/Cursor/Devin/Lovable/Manus…）。主项目技能库/提示词工程的重要语料来源。
27. **orbi** —— GitHub Issue 驱动的本地 AI 开发 worker：认领 issue→隔离 worktree 开发→PR→独立审查合并门禁，**GitHub Issues 即任务池，无 DB/队列/daemon**。对标主项目 DAG 编排/任务状态管理：无中心存储的状态设计值得参考。
28. **ai-maestro** —— 「AI 优先组织的 OS」：任意 agent 编排 + 持久记忆 + agent 间消息 + 多机支持。对标主项目 agent 编排/通信层。
29. **no_human** —— 开源「ticket→已评审 PR」AI 编码工厂（桌面 app + 看板，Python），与主项目 agent 化 DAG 编排同域，可参考其看板/审批流交互。
30. **Polaris** —— 端到端自主 AI 科研：文献→评审论文，长运行 agent 核 + 可续跑 + 人工门禁。对标主项目 critic/DAG 续跑 + 审批持久化（v13 已落地同类），人机门禁设计可参考。
31. **The_Code_Factory_Working_V2-main** —— 商业「自主软件工程师」多 agent 编排（AI+DLT+多 agent）。概念对标主项目 DAG 编排，但 Proprietary 许可，仅思想参考。
32. **Auto-Company** —— 14 个自主 agent 组「全自主 AI 公司」（Claude Code/Codex，含 Dashboard）。对标主项目多 agent 编排，营销/产品 agent 角色分工可参考。
33. **ralph-main** —— Ralph 循环：反复启动 AI 编码工具直到 PRD 全项完成（每轮全新 context，git+progress.txt+prd.json 持久记忆）。极简状态管理，主项目 agent 循环可借鉴其「每轮清 context + 文件级持久」模式。
34. **nikivdev__code** —— `flow`：项目加速 CLI 工具（Rust，flow.toml 配置）。工程规范参考，与主项目关系弱。
35. **Logic** —— 全栈日志分析器（Lucene/SPL/LogQL 查询 + 阈值/异常告警 webhook，Axiom HUD 风格）。主项目有 Logs 页与日志体系，其查询语法/告警可参考。
36. **thunderbolt-main** —— Thunderbird 的 AI 聊天前端「AI You Control」：自托管、自选模型、免锁定，企业私有部署。对标主项目对话网关前端/私有部署，思路同向但偏前端。
37. **Understand-Anything** —— 把任意代码库/知识库转成可探索可问答的交互式知识图谱（Claude Code/Codex 多端）。与 graphify-3 同类，可并入主项目 codegraph 对标。
38. **HolyClaude** —— 一条命令拉起完整 AI 开发工作站容器（Claude Code + web UI + headless 浏览器 + 8 个 AI CLI + 50+ 工具，Docker compose）。对标主项目桌面/部署体验，环境编排可参考。
39. **Likec4** —— 「架构即代码」：从代码生成并保持最新的架构图（VS Code 插件 + playground）。对标主项目架构文档/演进记录，可视化架构图工具。
40. **cronalytics** —— Cronalytics（Python + plugin.yaml + skills/ + dashboard）：时间序列分析/记录类工具。主项目有 OTel/遥测，可参考其技能封装与仪表盘。
41. **strix** —— 开源 AI 渗透测试工具：自主 AI 黑客发现/修复应用漏洞。与主项目安全审查相关但侧重红队，L3 安全参考。
42. **lonkero** —— Rust 专业级漏洞扫描器（模块化，浏览器辅助扩展）。安全参考，与主项目交集低。
43. **cubeplex** —— 全栈平台（backend/frontend/monorepo + skills-lock），疑似 agent 平台类，README 未读完即识别为中后台套件。价值中，未深挖。
44. **foremerge** —— Rust：合并前检测「意图冲突」（intent conflicts）而非代码冲突。对标主项目多 agent 并行改码的冲突检测，思路有启发。

---

## 低价值 / 无关（一句话定位）

45. **searxng** —— 目录为空（仅 .git），无内容，跳过。
46. **hydra** —— Hydra Download Manager：多源下载管理器/加速器（C++/Rust）。与主项目无关。
47. **greptimedb** —— 时序数据库（metrics/logs/traces，Rust，对象存储）。主项目用 SQLite+OTel，无直接需求。
48. **ricoui-design-md** —— 以 DESIGN.md 为中心的本地优先设计系统工作区（Next.js，Supabase 可选）。前端设计系统参考，价值中低。
49. **agor** —— 自托管多人在线 agent 编码工作区（浏览器跑 Claude Code/Codex 于隔离 git 分支，MCP 端点）。agent 工程中价值，已并入上表思路。
50. **Learnova** —— AI 学习工作区（任务/笔记/测验/闪卡/PDF 解析，全栈）。办公/学习工具，与主项目无关。
51. **formbricks** —— 开源体验管理/调查问卷平台（Qualtrics 替代）。与主项目无关。
52. **MultiPost-Extension** —— 浏览器扩展：一键多平台社交发布。社交工具，无关。
53. **autonomous-os** —— 机器人操作系统「Android for Robots」：agent 推理 + 技能 + 学习循环（Go）。与主项目无关但技能/学习循环思想可扫读。
54. **openclaw-to-hermes** —— OpenClaw→Hermes 迁移工具（已并入 Hermes 原生 `hermes claw migrate`）。生态迁移工具，低价值。
55. **vimona3ds__hermes-snapcompact** —— Hermes 插件：上下文满时把旧轮次渲染成位图 PNG，视觉模型约 1/3 token 成本读回。**context 压缩思路新颖**，中价值（省 token），但依赖 vision 模型。
56. **holaOS** —— Agent 工作空间：应用与 agent 并排的本地优先工作区。对标 agent 化桌面体验，中低价值。
57. **ai-website-cloner-template-master** —— AI 网站克隆模板：逆向任意网站成 Next.js 代码（/clone-website）。电商/建站相关，与主项目无关。
58. **Jazee6__cloudflare-ai-web** —— Cloudflare AI Web 前端（Next.js，配 CF Workers AI key）。ChatGPT 风格前端参考，与主项目聊天前端同域，中低价值。
59. **Alchemy-main** —— 自动化 AI 科研标准化环境（交付 algorithm.py+hyperparameter.yaml）。科研工具，无关。
60. **Nutlope__hallmark** —— Claude Code/Cursor/Codex 的设计 skill：拒绝「AI 生成感」外观（21 主题）。主项目前端设计可借鉴反模板风格，中低价值。
61. **VaultS3** —— 轻量 S3 兼容对象存储（单二进制 17MB，内置 dashboard，Go）。主项目文件存储层备选，中价值（图片产物存储）。
62. **zvec-main** —— 阿里向量数据库 zvec（C++/Python，词向量检索）。主项目无向量需求（可作 RAG 备选），低-中。
63. **Vibe-Trading** —— 个人交易 agent（一条命令给 agent 交易能力，含桌面/前端）。交易工具，无关。
64. **nodeterm** —— 节点式终端管理器：无限画布上挂多个真实终端 + Trello 式 Claude Code 会话看板（Electron）。对标主项目多 agent 会话管理 UX，中低价值。
65. **xl-converter** —— 图像格式转换器（现代格式，Windows/Linux，Python）。图片工具，低价值。
66. **HBAI-Ltd__Toonflow-app** —— 图像批量处理工作流工具（Electron，Toon 风格批处理）。图片处理，低-中价值（与主项目生图后处理相关）。
67. **CodeStable** —— AI 编码项目演进中保持边界/证据/记忆（8 个 skills，WORKFLOW.md/SKILL_CATALOG.md）。工程规范/技能体系参考，中价值。
68. **ghidra** —— NSA 反汇编/逆向框架（Java/Gradle）。安全逆向，与主项目无关。
69. **ccstatusline-main** —— Claude Code 状态行增强（底部状态条，TypeScript）。开发体验小工具，低价值。
70. **caveman-compression-main** —— LLM 上下文的「无损语义压缩」脚本（Python，多种模式）。**context 压缩参考**，中价值（省 token，主项目长对话可用）。
71. **Hands-On-AI-Engineering** —— 动手 AI 工程教程集（OCR/agent/fine-tuning/multimodal/RAG）。学习资料，低价值（方法论可参考）。
72. **cmux** —— macOS 终端应用（Ghostty 构建，垂直标签页 + AI agent 通知）。桌面工具，低价值。
73. **FireRed-OpenStoryline** —— 腾讯 FireRed 开源故事/长视频生成（LLM 讲故事 + 音频/视频）。**与主项目视频/音频生成域相关**，中价值：多模态生成管线可参考。
74. **AutoSploit** —— 自动化渗透利用工具（Shodan 收集目标 + Metasploit 模块，Python）。红队工具，主项目不涉及，低价值（仅安全参考）。
75. **ogallotti__rtk-hermes** —— Hermes 插件：执行前用 RTK 把冗长 shell 命令重写成低 context 等价形式。**context 优化小工具**，中低价值。
76. **caura** —— 已列 ★。重复项忽略。
77. **HERO-Anti-OverDefense** —— Claude Code 反过度防御研究：识别 agent「为免责而非做好工作」的四种形态（Hashing/Edge cases/Rubrics/Overbuild）+ 案例。**工程规范/agent 行为研究**，中价值：给主项目 critic 提供「反过度工程」检查视角。
78. **deepeval** —— 已列 ★。
79. **strix** —— 已列。
80. **foremerge** —— 已列。

---

## 汇总（按主项目价值分组）

- **第一梯队（建议精读）**：freellmapi、litellm、caura、cocoindex、graphify-3、prompt-optimizer、deepeval、mempalace、memvid、ENZO（密钥中继）、OpenContext（MCP+桌面记忆）。
- **第二梯队（局部借鉴）**：JIT（harness 生成）、ralph（极简循环状态）、orbi（无中心存储编排）、no_human/Polaris（人机门禁+续跑）、Anything-Analyzer（流量逆向）、system-design-101（架构教材）、ZeroSlop/aicheck（内容质检）、OpenKB（无向量检索）、snapcompact/caveman/rtk-hermes（context 压缩家族）、FireRed-OpenStoryline（多模态生成）、VaultS3（对象存储）、HERO（反过度工程）。
- **生态相关**：openclaw、openclaw-to-hermes、holaOS、HolyClaude（部署工作站）。
- **无关/低价值（24 个左右）**：searxng(空)、hydra、greptimedb、formbricks、Learnova、MultiPost、autonomous-os、Alchemy、Jazee6、xl-converter、ghidra、ccstatusline、cmux、AutoSploit、Vibe-Trading、Hands-On-AI-Engineering、zvec、likc4、ApeAdmin(栈不同)、Logic、thunderbolt、x1xhlol(语料)、semtools 等——均已一句话定位。

**给主项目的三个可落地结论**：
1. **免费聚合网关**：freellmapi 是主项目「听风AI」最接近的同行实现，其「自更新模型目录 + 每 key 配额追踪 + fallback 路由」三件套应优先对标移植。
2. **记忆层**：caura（多租户治理）与 memvid/mempalace（轻量单文件）代表两条记忆路线，主项目记忆巩固模块可对照取舍。
3. **context 压缩**：snapcompact(位图)/caveman(语义无损)/rtk-hermes(命令改写) 三个轻量技能提供低风险 token 优化路径，可直接技能化。
