# g04_agent_skill_a · SKILLS 类深度扫描报告（28 目录）

> 扫描方式：只读分析。对每个目录 ls 结构 → 读 README/SKILL.md 首部判断领域 → 深入最有价值的技能定义/验证/工程化设计。
> 主项目 skills 现状：`api/skills/{ecommerce,ppt,image_quality,prompt_refine,critic}/SKILL.md`，frontmatter 仅 `name`+`description`，loader 启动扫描建索引。**本组 28 个项目全部与"技能生命周期"相关，是主项目 agent skills 沉淀/验证机制的最大参照池。**

---

## 00200200__maintainer-skills-lab
- 定位：技能维护实验室——16 个维护/工程技能（humanize/debug/reproduce/verify-fix/triage）+ 6 种 agent 配置，一套 Markdown 源多客户端生成版本。
- 技能领域/技术栈：Codex/Claude Code/Cursor/OpenCode/Grok Bot；Node.js（`npx skills` CLI 安装）、Python 评测脚本、`skill-watch.toml` MCP 看护。
- 亮点：
  1. **`skill-watch.toml` 引用看护**：声明每个技能正文依赖的官方文档 URL + start/end 截断锚点 + owner（`skills/mkl-debug-ml-training/SKILL.md`），把"技能引用来源"变成可追踪、可校验的清单（`docs/skill-watch.md`、`skill-watch.toml`）。
  2. **示例驱动的验收证据**：`examples/{writing,ml-training,bugfix}/` 带 fixtures + `run.py`，README 首部直接给 before/after 对照和 acceptance checks——技能质量用"可运行示例"而非口号证明。
  3. **技能命名即领域**：`mkl-humanize`/`mkl-reproduce-bug`/`mkl-verify-fix` 等，每个 skill 职责单一、可独立安装（`--skill xxx --agent xxx`）。
- 对主项目价值：直接借鉴
- 借鉴点：给每个 skill 配一个 `sources/references` 引用清单（主项目 ecommerce 引用了什么方法论，可登记）+ examples 目录放真实输入/期望输出对，供 LLM 自检和用户验收。
- 评分：4

## 100x-skill-tiktok
- 定位：TikTok/UGC 创意流水线技能集（反推视频/分镜/本地化/人设/夸张/提示词合成），含 router 技能做任务路由。
- 技能领域/技术栈：视频/短内容创意 + 中文运营；Node.js AJV 校验、Python 严格验证器、jsonschema、ffmpeg。
- 亮点：
  1. **schema.json + validate.js 双层验证工程**：每个技能带 `schema.json`（JSON Schema draft-07，AJV 执行结构校验：required/enum/additionalProperties）+ `scripts/validate.js --selftest`（8 条回归断言：真样例通过、注入额外字段失败、越界枚举失败、伪造引用失败、跨市场天花板计算失败/通过回归）——**结构层与跨字段语义层分离**，且自测套件内置。
  2. **metadata.json 全契约文档化**：每技能登记 `input_contract`（A 类必填/B 类软降级/C 类上游可选）、`output_contract`、`validation`（含每条公理如何被机器验证）、`requires_data`（数据来源溯源）——技能的可验证性被写进元数据。
  3. **`skills.json` 仓库级清单**：`planned_total`/`router`/每个技能 `status: validated` + `validate_cmd` + `trigger_examples`（中英双语触发词），配合 `VERSION` 文件版本管理。
  4. **axioms.md / workflow.md / sources.md 拆分**：把"不可违反的公理""降级流程""数据来源"分成独立文件，SKILL.md 只留决策骨架。
- 对主项目价值：直接借鉴（最强技能工程化样板）
- 借鉴点：主项目 5 个 skills 可升级为「SKILL.md + schema.json + validate.py + metadata.json」四件套；trigger_examples 双语收集进 loader 索引增强路由命中；给 image_quality/ecommerce 增加机器可校验的输出契约（如五维自审分数落 JSON schema）。
- 评分：5

## AI-Research-SKILLs
- 定位：AI 研究全生命周期技能库（22 个领域技能：模型架构/训练/对齐/评估/Agent/RAG/多模态/论文写作…），配 autoresearch 总调度技能。
- 技能领域/技术栈：研究/MLOps/Agent；SKILL.md + references/ + templates/ + CLAUDE.md。
- 亮点：
  1. **两级路由架构**：`0-autoresearch-skill` 是总调度（内/外双循环），按任务路由到 01-22 领域技能执行——和主项目"意图识别→技能路由"同构，但规模更大（`references/skill-routing.md` 存路由规则）。
  2. **技能模板工程化**：每技能带 `templates/`（findings.md、research-log.md、research-state.yaml、progress-presentation.html）——结构化产出模板让技能结果可机器消费。
  3. **CITATION.cff + anthropic_official_docs/**：引用与官方文档目录并纳入仓库，知识有出处。
- 对主项目价值：局部借鉴（路由思想）
- 借鉴点：主项目 DAG 编排可参考其"总调度 + 领域执行"两级拆分；技能结果落模板（如 ecommerce 输出固定 YAML/JSON 骨架）增强下游可消费性。
- 评分：4

## AREX-Skill
- 定位：Agent 推理/评测领域技能集（FrontierCS/PaperBench/PassNet 任务 + repo-skills 仓库技能路由），面向科研基准。
- 技能领域/技术栈：AI 评测/研究；Python 脚本 + SKILL.md。
- 亮点：
  1. **任务导向技能**（`task-oriented/PassNet`）：SKILL.md 明确"先 check_pattern 再 GPU 评测、先 analyze_graph 再 author passes"的迭代循环，把"如何省 GPU 预算"写进技能——与主项目预算门禁思路呼应。
  2. **repo-skills + router 双层**：仓库级技能与路由技能分离，`repo-skills-router` 做仓库内技能分发。
- 对主项目价值：扩展方向参考
- 借鉴点：主项目 image_quality 可学"先轻量预检再重跑"的分级验证策略（低费预判 → 高费全检）。
- 评分：3

## Agent-Skills-for-Context-Engineering-main
- 定位：上下文工程技能集（context-fundamentals/degradation/compression、multi-agent-patterns、memory-systems、tool-design、evaluation、LLM-as-a-Judge 等 15 技能）。
- 技能领域/技术栈：上下文工程/Agent 系统设计；SKILL.md + references/ + scripts/ + template/。
- 亮点：
  1. **`template/SKILL.md` 完整作者模板**：frontmatter（name/description）+ 明确"正文 <500 行、超长移 references/"；第三人生成 description（"Processes Excel files…"而非"I can help…"）；"When to Activate"含直接+间接触发词；"信息密度"章节教"每段都要 justify 其 token 成本"——**这是主项目 loader 设计所参考的 SKILL-AUTHORING 标准同源**。
  2. **evaluation/advanced-evaluation 技能**：教 agent 建评测框架、LLM-as-a-Judge 打分——把"技能验证"本身做成技能。
  3. 被论文引用为"静态技能架构"代表作，说明格式规范有学术背书。
- 对主项目价值：直接借鉴
- 借鉴点：把 template/SKILL.md 作者规范吸收进主项目，写《主项目 skill 作者规范》文档；description 强制第三人称 + 中英触发词；evaluation 技能思想用于给 critic skill 建评测集。
- 评分：4

## Anthropic-Cybersecurity-Skills
- 定位：Anthropic 官方网络安全技能库（100+ 技能，覆盖攻击链全阶段）。
- 技能领域/技术栈：网络安全取证/攻击分析；每技能 SKILL.md + references/ + scripts/agent.py + LICENSE。
- 亮点：
  1. **官方级 frontmatter 扩展**：`domain` + `subdomain` + `tags` 结构化元数据（`analyzing-command-and-control-communication/SKILL.md`）——比主项目仅 name/description 多两级分类。
  2. **脚本随附**：每技能 `scripts/agent.py` 把可自动化部分做成脚本，SKILL.md 教判断，脚本做执行——知识+工具合一。
  3. **index.json 全库索引 + ATTACK_COVERAGE.md 覆盖面审计**：技能库可被程序化检索，覆盖度透明可查。
- 对主项目价值：局部借鉴（元数据规范）
- 借鉴点：主项目 skills frontmatter 增加 `domain`/`tags`/`version`；给 image_quality/prompt_refine 配可执行辅助脚本；技能覆盖面表格化。
- 评分：4

## ClaudeSkills
- 定位：中文企业级技能库（Deep Research/Deck Studio/Product Manager/WeChat 文章等 13 技能 + lab 实验技能），带严格质量门禁。
- 技能领域/技术栈：通用生产力/中文场景；Python 验证脚本、静态站点、版本管理（VERSION、CHANGELOG）。
- 亮点：
  1. **`scripts/validate.py` L1 结构门禁**（Skill Quality Standard v1.0）：每个技能强制 frontmatter 有 name+description、description≤1024 字符、SKILL.md≤500 行、无平台硬编码路径（/mnt/skills 等）、**无孤儿文件**（references/scripts/assets 下每个文件必须在正文被引用）；WARN 层检查"三件套"（验收标准/不做什么/陷阱）是否存在——**机器强制技能结构质量，这正是主项目缺失的**。
  2. **frontmatter 富元数据**：`version`/`compatibility`/`metadata`（owner/category/maturity/outputs 文件清单）——技能版本与成熟度可追踪。
  3. **`verification/` 验收台账**：按日期记录可复现验收证据（baseline commit、SHA-256、PASS/BLOCKED/FAIL 计数、r2/r3/r4 修正过程）——与主项目 verification-log.md 同哲学。
  4. **rich 中文三件套**：每技能含"验收标准/自查、不做什么/不用于、已知陷阱"三段——把负向边界显式化。
- 对主项目价值：直接借鉴（验证门禁 + 元数据）
- 借鉴点：为主项目写 `scripts/validate_skills.py`，复制其 L1 门禁（行数/引用完整性/负向三段）；frontmatter 加 version/metadata/outputs；critic skill 输出加"验收标准"段。
- 评分：5

## CyberSecurity-Skills
- 定位：中文网络安全技能库（39 模块 195 技能），按 PTES/OWASP/NIST/MITRE 标准组织。
- 技能领域/技术栈：渗透测试/安全全流程；markdown 技能条目 + index.json + skill_query.py CLI + CI validate。
- 亮点：
  1. **结构化 frontmatter**：每技能条目 `id`/`title`/`category`/`difficulty`/`tools`/`tags`/`nist_csf`/`mitre_attack`——**对照国际标准框架映射**（MITRE ATT&CK ID），技能可被合规检索。
  2. **index.json + skill_query.py 程序化接口**：CLI 支持 list-modules/list-skills/get-skill/search/resolve/validate，`validate` 校验 index.json 与实际文件一致性——**技能库的"目录+查询+一致性校验"三件套**。
  3. CI `.github/workflows/validate.yml` 保证清单与文件不漂移。
- 对主项目价值：局部借鉴（索引/查询接口）
- 借鉴点：主项目 loader 可加 `validate` 子命令（对照 SKILL.md 文件与索引一致性）；skills 加 difficulty/tools 字段；把 skills 清单暴露成 admin 面板可查接口。
- 评分：4

## DevOps-Security-Agent-Skills
- 定位：DevOps/安全/合规领域技能库（devops/security/compliance/infrastructure 四大类，数百技能）。
- 技能领域/技术栈：DevOps/云安全/合规；SKILL.md 扁平组织，frontmatter 含 `license` + `metadata.author/version`。
- 亮点：
  1. **分类即目录**：`compliance/{frameworks,auditing,continuity}`、`security/{secrets,scanning,hardening}` 等三级目录即技能分类，无额外索引文件也清晰。
  2. **frontmatter 轻扩展**：加 `license` + `metadata.author/version`（`security/secrets/aws-secrets-manager/SKILL.md`）——主项目可直接采纳的最小扩展。
- 对主项目价值：局部借鉴（frontmatter 扩展 + 目录组织）
- 借鉴点：skills 目录按 `{domain}/{topic}/` 两级组织；frontmatter 补 license/author/version。
- 评分：3

## EvoSkill-main
- 定位：自动化技能发现/改进框架（GEPA/DSPy 式自改进）——从 agent 失败模式自动提出技能/提示词改进并评估保留最优。
- 技能领域/技术栈：Python 3.10+；GEPA/DSPy 优化、OpenRouter/Anthropic/OpenAI 多模型、agent-agnostic。
- 亮点：
  1. **FeedbackDescent 算法**（`src/feedback_descent.py`）：`generate_initial → propose → evaluate` 循环，带反馈历史，可接任意目标模型——把"技能改进"抽象成通用优化器。
  2. **run_loop + run_eval 分离**：训练循环与评估脚本独立（OfficeQA/LiveCodeBench/SEALQA 多基准），技能改进有分数闭环。
  3. **registry/schemas 结构化**：技能注册表 + pydantic schemas，技能定义类型安全。
- 对主项目价值：扩展方向参考（技能自动优化）
- 借鉴点：远期可为主项目做"skills 自动改进循环"（从任务失败日志提取补丁 → 评估门 → 采纳），但属 L3 大工程，先记入 roadmap。
- 评分：4

## Generative-Media-Skills
- 定位：生成媒体（图/视频/音频/3D）技能库，schema 驱动架构，57 个 library 技能 + 3 个 core 技能。
- 技能领域/技术栈：AI 媒体生成（MuAPI 100+ 模型）；shell 脚本 + `schema_data.json`（JSON Schema 动态模型/端点解析）。
- 亮点：
  1. **schema_data.json 驱动模型/端点解析**：所有脚本读统一 schema 文件解析模型名/输入 schema（`input_schema` 含 `schemas.input_data` + `name.enum` 效应列表）——**技能与底层 API 解耦**，加新模型不改技能只改数据。
  2. **core + library 分层**：core（media/edit/platform 通用原语）+ library（57 个场景配方）——通用能力与场景知识分离，与主项目"引擎 + skills"分层同构。
  3. **recipe pack + expert library 双视图**：同一能力有"配方"（速查）与"专家库"（深度）两种呈现。
- 对主项目价值：直接借鉴（schema 驱动 + 分层）
- 借鉴点：主项目 image_quality/ppt 技能把"模型参数/上游能力清单"抽到 schema 数据文件，技能正文不再硬编码模型名；core(通用) + library(场景) 分层。
- 评分：4

## Leon-Drq__openagentskill
- 定位：技能注册表/决策层平台（Web + CLI + API）——任务→技能解析、信任审计、安装回执、效果闭环。
- 技能领域/技术栈：Next.js 全栈 + CLI + Registry；JSON/text/OpenAPI 多出口。
- 亮点：
  1. **task-to-skill resolve API**：`/api/agent/resolve?task=...&agent=...&max_risk=...` 返回"最佳技能 + 替代 + 风险等级 + 安装回执"——把"技能发现"变成服务。
  2. **Trust Score + 风险分级**：对技能做许可证/维护度/安装安全/权限审计打分（v5 评分体系）。
  3. **outcome loop**：从成功/失败/阻塞的运行收集证据回写——技能库自我进化。
- 对主项目价值：扩展方向参考（技能市场/推荐）
- 借鉴点：主项目远期可做"skills 市场"页（admin 面板展示技能评分/触发词/风险），resolve 逻辑复用现有路由引擎打分思路。
- 评分：3

## Leonxlnx__taste-skill
- 定位：前端"品味"技能框架（anti-slop）——brandkit/brutalist/minimalist/soft/redesign/imagegen-frontend 等 10 技能。
- 技能领域/技术栈：前端设计/UI；SKILL.md 多技能集 + 网站。
- 亮点：
  1. **技能即设计方法论**：每技能封装一套设计语言（风格定义/色板/排版/反模式），用 SKILL.md 把"品味"教给 agent——与主项目 ecommerce "Campaign Style Lock" 思路一致。
  2. **imagegen-frontend-web/mobile 技能**：把图像生成接前端呈现的完整工作流做成技能。
- 对主项目价值：扩展方向参考（设计类技能）
- 借鉴点：主项目 ecommerce 技能可吸收其"风格语言封装"写法（色板/排版/反模式固化）。
- 评分：3

## OJO-Design-Skills
- 定位：UI/UX 设计技能包（app-ui-ux-best-practices），双轨方法论（Convention/Innovation）+ anti-AI-slop 护栏。
- 技能领域/技术栈：前端设计系统；SKILL.md + references/，多语言 README。
- 亮点：
  1. **硬性反模式护栏**：紫色蓝渐变、灰盒占位、单色板被列为 hard-banned 规则而非建议——把"设计红线"写成机器可读禁令。
  2. **双轨方法论 + ISFP 设计师人设**：技能注入"设计决策人设"引导风格判断，非通用模板。
- 对主项目价值：扩展方向参考
- 借鉴点：image_quality 技能可借鉴"硬性禁令清单"（如禁止占位图/低清图判定阈值），提升评审一致性。
- 评分：3

## PE-reverse-skill
- 定位：PE/APK 授权逆向分析本地平台（Go 后端 + Web 前端 + Docker worker + Skill 目录）。
- 技能领域/技术栈：逆向工程/安全；Go + PostgreSQL + Docker + Python provider 生命周期。
- 亮点：
  1. **provider 生命周期统一契约**：`supports → plan → validate → execute → rollback → collect_artifacts`——能力接入有标准六步，含失败关闭验证与回滚。
  2. **reverse-skills/ 技能子库**：CTF-Sandbox-Orchestrator、burp-mcp-full 等技能化工具集成。
  3. **证据清单 + 验收文档**：P11 验收记录真实模型调用/构建/行为比较，`complete_buildable=true`——全链路证据闭环。
- 对主项目价值：局部借鉴（provider 生命周期契约）
- 借鉴点：主项目 providers 可参考其 `plan→validate→execute→rollback→collect_artifacts` 六步契约抽象（当前是 action_sniffer 模式），增强 provider 接入的失败回滚。
- 评分：4

## SecSkills
- 定位：安全技能/MCP 导航站（README 表格汇总 54 个安全相关技能/MCP 仓库链接）。
- 技能领域/技术栈：安全工具聚合；纯 markdown 导航。
- 亮点：
  1. **分类目录导航**：代码审计 12/渗透 14/JS 逆向 2/skills 检查 2 等分类表格，每条带描述+链接——技能发现目录范式。
- 对主项目价值：无价值（仅导航页）
- 借鉴点：无（主项目 skills 已有实际代码实现，不需要链接导航）。可作为"安全相关 skills 从哪里找"的外部索引参考。
- 评分：1

## SkillClaw
- 定位：集体技能演化框架——agent 每次真实交互后台自动消化成技能，跨会话/设备/用户累积，含验证门与服务器端协同演化。
- 技能领域/技术栈：Python 3.10+；Hermes/OpenClaw/Codex/Claude Code 多 agent 兼容；对象存储 + 验证存储 + PRM scorer。
- 亮点：
  1. **自动消化循环**（`evolve_server/engines/agent.py`）：`_summarize_sessions → 提取候选技能 → _upload_skill`，agent 会话后自动沉淀，无需用户显式操作——**"让用户零成本沉淀自己技能"的直接实现**。
  2. **验证门**（`validation_store.py` + `validation_worker.py`）：job/candidate/result/decision 四阶段，空闲窗口触发重放评分（PRM scorer），`_validation_enabled` + 每日配额控制预算——**技能入库前必须通过重放验证，且有预算门**。
  3. **skill_bundle 安全打包**：多文件技能哈希/相对路径校验/忽略目录过滤，防路径穿越（`normalize_bundle_rel_path` 拒绝 `..`/绝对路径）。
  4. **embedding 检索 + 去重**（`skill_manager.py`）：`_compute_skill_embeddings` + `_deduplicate_by_embedding`，重复技能自动合并。
- 对主项目价值：直接借鉴（用户技能沉淀核心参照）
- 借鉴点：主项目"训练用户自己的 skills"功能直接以 SkillClaw 为蓝本：agent 会话后后台摘要 → 候选技能（frontmatter 按主项目格式生成）→ 重放验证门（复用现有评测/意图数据）→ 用户审批 → 入 `api/skills/`；嵌入去重防冗余；预算门控验证开销。
- 评分：5

## SkillOpt
- 定位：技能自我进化训练框架（微软）——把技能文档当"可训练参数"，用 rollout/reflect/aggregate/select/update/evaluate 六阶段循环训练，带验证门。
- 技能领域/技术栈：Python 3.10+；多后端（OpenAI/Azure/Claude/Qwen/MiniMax/Codex CLI/Claude Code CLI）；六个基准 + WebUI。
- 亮点：
  1. **ReflACT 六阶段训练循环**（`skillopt/engine/trainer.py`）：Rollout → Reflect → Aggregate → Select → Update → Evaluate，候选技能只在"严格提升 held-out 验证分"时被接受（`evaluation/gate.py` 的 hard/soft/mixed 三种 gate 指标）——**训练式技能优化，可复现**。
  2. **技能文档保护区**：`<!-- APPENDIX_START/END -->` 和 `<!-- SLOW_UPDATE_START/END -->` 注释块把"执行经验附录"与"慢更新区"与正文隔离——技能正文稳定、经验增量追加。
  3. **SkillOpt-Sleep 夜间离线自演化**（`skillopt_sleep/`）：harvest 会话 → mine 重复任务 → replay 重放 → consolidate（reflect → bounded edit → GATE）→ 用户 adopt，零依赖独立包——**"睡前沉淀当日经验"落地产品**。
  4. **semantic_density 检查**：验证技能文档中 MUST/ALWAYS/NEVER 等强指令密度，防技能退化成废话。
- 对主项目价值：直接借鉴（训练式沉淀 + 夜间循环）
- 借鉴点：主项目 skill 文档加 `<!-- APPENDIX_START -->` 保护区存失败/经验增量；参考 SkillOpt-Sleep 做"每日 agent 会话 → 重放 → 门禁 → 用户采纳"的沉淀定时任务（预算门控）；critic skill 用 gate hard/soft 思路评估补丁。
- 评分：5

## SkillSpector
- 定位：NVIDIA 技能安全扫描器——安装 agent 技能前检测漏洞/恶意模式/风险（71 漏洞模式 17 类 + LLM 语义评估 + 0-100 风险分）。
- 技能领域/技术栈：Python 3.12+；AST 分析/taint tracking/YARA/OSV.dev 实时 CVE；多格式报告（Terminal/JSON/Markdown/SARIF）；MCP/Pi 扩展。
- 亮点：
  1. **两阶段分析 + 风险评分**：快速静态分析 + 可选 LLM 语义评估，71 模式覆盖 prompt 注入/数据外泄/提权/供应链/过度代理等——**"技能安全"被系统化**。
  2. **Baseline 假阳性抑制**（`docs/SUPPRESSION.md`）：已知可接受发现用 glob/fingerprint baseline 压掉，重扫只报新问题，且每条抑制带可审计 reason——增量 CI 友好。
  3. **fail-closed 资源上限**（`docs/ANALYSIS_RESOURCE_BOUNDS.md`）：解析器/嵌套工件/ledger/finding 天花板，扫描本身不失控。
  4. **SKILL.md 解析为安全分析对象**：扫描器原生解析 agent 技能目录（skills/*），说明"技能文件是新的攻击面"已成共识。
- 对主项目价值：直接借鉴（技能安全扫描，主项目用户将创建自定义 skills）
- 借鉴点：主项目开放用户 skills 上传前，用 SkillSpector 思路做 `scripts/skillspector.py` 本地扫描（危险模式：内联脚本执行、数据外泄、密钥硬编码）+ baseline 抑制 + 0-100 风险分进 admin 面板；禁止 prompt 注入技能入库。
- 评分：5

## SkillX-main
- 定位：自动从 agent 经验轨迹构建技能知识库——把原始轨迹蒸馏成三级技能层次（Planning/Functional/Atomic）。
- 技能领域/技术栈：Python；LLM 抽取 + embedding 聚类；AppWorld/BFCL/τ2-Bench 基准。
- 亮点：
  1. **三级技能层次**（`extraction/skill_extractor.py`）：FunctionalSkillExtractor（步骤级子例程）+ AtomicSkillExtractor（工具级用法 + 缺失工具检测 `_get_missing_tools`）——技能按抽象层级分类，弱 agent 可直接插入复用。
  2. **统一 5-key schema**（`core/skill.py`）：`name/document/content/tools/metadata`，两种技能类型同构、可 JSON 序列化、可 embedding（`get_embedding_text`）——**技能的最小机器可读契约**。
  3. **自动蒸馏管线**（`pipeline.py` + clustering）：原始轨迹 → 抽取 → embedding 准备 → 聚类去重 → 入库。
- 对主项目价值：直接借鉴（轨迹→技能自动蒸馏的数据模型）
- 借鉴点：主项目用户技能沉淀可用 5-key schema 做内部表示（name/触发说明/content/tools/metadata）；按"规划/功能/原子"分层沉淀用户经验；轨迹聚类去重。
- 评分：4

## Skills-main
- 定位：Swift/iOS 领域技能集（17 技能：SwiftUI/性能/并发/重构/App Store 发布等），含 skills.json 清单 + 本地 app 化索引。
- 技能领域/技术栈：Swift/SwiftUI/Xcode；SKILL.md + references/ + `docs/skills.json` 索引 + JS app。
- 亮点：
  1. **skills.json 引用清单**：每技能 `name/folder/description/references[]`（标题+文件），references 显式登记参考文档——技能与参考资源关系机器可读。
  2. **reviews/bug-hunt/audit 流程技能化**：`review-swarm`/`bug-hunt-swarm`/`project-skill-audit`——把多 agent 审查/技能审计做成技能（`project-skill-audit` 教"先查项目真实会话/记忆再推荐技能，避免泛化 brainstorm"）。
- 对主项目价值：局部借鉴（references 清单 + skill-audit 技能）
- 借鉴点：`project-skill-audit` 思想可直接移植——主项目"为用户推荐该建什么技能"时先审计 DAG 任务日志/记忆，而非泛泛而谈；skills.json 的 references 字段加入主项目 loader。
- 评分：3

## YouMind-OpenLab__ai-image-prompts-skill
- 定位：图像生成提示词推荐技能——从 10000+ 真实社区提示词库推荐提示词，任何图模型通用。
- 技能领域/技术栈：AI 图像生成/提示词工程；SKILL.md + `_meta.json` + references/*.json（分类提示词库）。
- 亮点：
  1. **提示词即数据文件**：`references/` 下按场景分类的 JSON（ecommerce-main-image、product-marketing、poster-flyer、youtube-thumbnail…），SKILL.md 只做推荐逻辑——**提示词库与技能逻辑分离，可热更新**。
  2. **frontmatter 扩展**：`platforms`（openclaw/claude-code/cursor/codex/gemini-cli 多平台声明）+ 强制"每条推荐必须带样例图"。
  3. **多模型兼容声明**：Nano Banana/Seedream/GPT Image/Midjourney/DALL-E 3/Flux/SD 全兼容，靠 prompt 库抽象规避模型差异。
- 对主项目价值：直接借鉴（提示词库数据化 + ecommerce 直接同场景）
- 借鉴点：主项目 ecommerce/prompt_refine 技能把提示词示例抽成 `references/*.json` 数据文件（按平台/品类分类），技能正文只写策略，提示词库可被管理员热更新；这对"扩展场景（电商/PPT/图片）"是现成素材。
- 评分：4

## addyosmani__agent-skills
- 定位：生产级工程技能集（addy osmani，25 技能），覆盖 6 阶段开发生命周期（spec/plan/build/test/review/ship）+ 9 个 slash command。
- 技能领域/技术栈：软件工程流程（TDD/代码审查/性能/安全/上下文工程等）；SKILL.md + agents/ + commands/ + evals/ + hooks/ + plugin.json。
- 亮点：
  1. **生命周期矩阵 + meta-skill 路由**：`using-agent-skills/SKILL.md` 是 meta-skill，画任务→技能路由决策树；9 个 slash command（/spec /plan /build /test /review /ship…）一键激活对应技能组。
  2. **技能即质量门禁**：每技能封装可执行工作流（如 TDD red-green-refactor、code-review 五轴检查），SKILL.md 内直接带命令/示例。
  3. **evals + hooks + plugin 工程化**：仓库级 evals 评测技能效果、hooks 集成 agent、plugin.json 声明元数据——技能库自身可测试、可分发。
  4. **frontmatter 规范**：`name`+`description`（第三人称、含 Use when…/When NOT to use）——与主项目 loader 同构。
- 对主项目价值：直接借鉴（生命周期路由 + 质量门禁技能化）
- 借鉴点：主项目 5 个 skills 可增加一个 `using-skills` meta-skill 做任务路由决策树；把"工具调用安全护栏""评审五轴"等已固化的规范沉淀成技能；evals 目录给 critic skill 建评测集。
- 评分：4

## agent-skills
- 定位：与 `addyosmani__agent-skills` 内容一致的重复副本（25 技能，同 README/skills 结构）。
- 技能领域/技术栈：同 addyosmani__agent-skills（软件工程流程技能集）。
- 亮点：内容与 addyosmani 完全相同（diff 无差异）——属于同一仓库的镜像/分支快照。
- 对主项目价值：无独立价值（与 addyosmani 重复）
- 借鉴点：无需重复扫描，结论合并到 addyosmani__agent-skills。
- 评分：2（重复副本）

## agent-skills-hub
- 定位：AgentSkillsHub——Claude Skills/MCP/Agent 工具目录站（117,000+ 项目），8 小时刷新，10 维评分。
- 技能领域/技术栈：技能市场/目录；Python 3.12 FastAPI + React 18 + Supabase/SQLite；GitHub Actions 定时管道。
- 亮点：
  1. **6 阶段数据管道**（GitHub API → Collection → Cleaning → Evaluation → Scoring → Presentation），10 加权信号 + 6 质量维度评分（完整性/清晰度/特异性/示例/README 结构/agent 就绪）——**技能质量可量化评分**。
  2. **SkillSpector 集成规范**（`docs/skillspector-integration-spec.md`）：目录站与安全扫描器对接——发现+评分+安全一体。
  3. **对比/场景页**：`/compare/` 与 `/best/{scenario}/`——按场景推荐最佳技能。
- 对主项目价值：扩展方向参考（技能市场/评分）
- 借鉴点：主项目若做"skills 市场/社区沉淀"功能，可参考其评分维度（6 质量维度）与 8h 刷新管道；SkillSpector 集成思路对应用户技能安全审查。
- 评分：3

## agentic-awesome-skills
- 定位：AAS 技能目录聚合平台（1936+ 技能，46k stars）——agent 本地目录搜索 + 栈组合 + 清单持久化（aas-stack.json）。
- 技能领域/技术栈：技能目录/MCP 工具；本地 stdio MCP（search/get/read/compose_stack/inspect_stack/diff_stack）+ CLI（validate/plan）+ Web Workbench。
- 亮点：
  1. **AAS Core：agent 自主选择 + compose_stack 内存校验**：agent 从完整本地目录选技能 → `compose_stack` 只读校验选择 → 持久化 `aas-stack.json`（不可变计划）→ 人工审查——**"技能选择可复现、可审计"**。
  2. **skills_index.json 富元数据**：每技能 `id/path/category/description/risk（safe/critical）/source/date_added/plugin.targets`——风险分级入库。
  3. **多分发层**：direct installs/plugins/bundles/workflows 并存，兼容 Codex/Claude/Cursor/Gemini CLI。
  4. **证据导出**：`aas-selection-evidence.json` 记录选择过程 trace 与能力清单 ledger。
- 对主项目价值：局部借鉴（技能栈清单 + 风险分级）
- 借鉴点：主项目"用户沉淀技能"可加 `skills_stack.json` 清单机制（记录用户启用的技能组合 + 版本，可回滚）；skills_index 加 risk 字段（结合 SkillSpector 扫描结果）。
- 评分：4

## agents-spec-skill
- 定位：agents-spec 技能——审计和组织 agent 指令/Spec/需求/技术决策，中文友好。
- 技能领域/技术栈：Agent 规范审计；SKILL.md + scripts/audit_agents_md.py + tests/（test_skill_package.py）。
- 亮点：
  1. **技能自带测试**：`tests/test_audit_agents_md.py` + `tests/test_skill_package.py`——**技能包有 pytest 单测**（验证 SKILL.md 结构、脚本行为），这是极少数"技能本身可测试"的项目。
  2. **中文 prompt 兼容 + 英文内部指令**：用户可用中文描述任务，技能内部英文指令保证跨 agent 一致。
  3. **npx skills 安装 + 手动安装双路径**，`name:` frontmatter 即安装名。
- 对主项目价值：直接借鉴（技能自带测试的最小范式）
- 借鉴点：主项目每个 skill 可配 `tests/test_skill_package.py`（校验 frontmatter 存在、触发词非空、正文含必要章节），与 loader 集成；对中文用户友好化 critic skill。
- 评分：4

## ai-image-prompts-skill
- 定位：与 `YouMind-OpenLab__ai-image-prompts-skill` 内容一致的同源副本（同 SKILL.md/_meta.json/package.json/references）。
- 技能领域/技术栈：同 YouMind（图像提示词推荐技能）。
- 亮点：内容与 YouMind 版本一致（同包结构），属于同一技能的镜像。
- 对主项目价值：无独立价值（与 YouMind 重复）
- 借鉴点：结论合并到 YouMind-OpenLab__ai-image-prompts-skill。
- 评分：2（重复副本）

---

# 本组汇总：Top3 最值得主项目借鉴项

主项目关注方向①（agent 深度优化：让用户能创建/沉淀/复用自己积累的技能）在本组找到最完整的参照池。按"可直接落地"排序：

## Top1 · SkillClaw + SkillOpt-Sleep → 用户技能自动沉淀闭环（评分 5）
- **机制**：agent 真实会话 → 后台 harvest/摘要 → 生成候选技能 → 重放验证门（GATE，held-out 任务分数不降才接受）→ 用户审批 adopt。SkillClaw 提供"零操作自动消化 + 每日配额预算门 + embedding 去重 + 安全打包"，SkillOpt-Sleep 提供"夜间离线 consolidate + 用户 review-then-adopt 的产品化形态"。
- **对主项目的迁移**：主项目已具备 DAG 任务日志、记忆 L1-L3、critic 自反思、预算门禁——新增一个「技能沉淀服务」：会话结束 → LLM 摘要候选技能（按主项目 frontmatter 格式生成）→ 用历史 DAG 任务重放验证（复用现有意图评测）→ 预算门控 → admin 面板用户审批 → 写入 `api/skills/`（loader 自动索引）。**这是"训练用户自己的 skills"的完整闭环蓝本。**

## Top2 · 100x-skill-tiktok 技能工程化四件套 → 技能可验证化（评分 5）
- **机制**：每个技能 = SKILL.md（决策骨架）+ schema.json（输出 JSON Schema，AJV 结构校验）+ validate.js --selftest（跨字段语义公理回归断言）+ metadata.json（input/output 契约 + validation 说明 + requires_data 溯源）。trigger_examples 中英双语入库。
- **对主项目的迁移**：主项目 5 个 skills 升级为「SKILL.md + schema.json + validate.py + metadata.json」：image_quality/ecommerce 的输出（如五维自审分数、Prompt 列表）定义 JSON Schema 并加校验脚本；loader 索引增读 trigger_examples/version。**配合 ClaudeSkills 的 validate.py L1 门禁（行数/孤儿文件/负向三段），可写一个 `scripts/validate_skills.py` 一键门禁。**

## Top3 · SkillSpector → 用户技能安全扫描（评分 5）
- **机制**：安装 agent 技能前静态扫描（71 漏洞模式：prompt 注入/数据外泄/提权/供应链/过度代理）+ LLM 语义评估 + 0-100 风险分 + baseline 假阳性抑制 + fail-closed 资源上限。
- **对主项目的迁移**：一旦开放用户创建/上传自定义 skills（Top1 闭环落地），必须配套安全扫描——写 `scripts/skillspector.py`（危险模式正则/规则集 + risk 分级进 admin 面板 + baseline 抑制），防止 prompt 注入型技能污染 agent 会话。**属"开放用户技能"的强制前置项（P0 安全边界）。**

## 补充推荐（并行落地）
- **SkillX 5-key schema + 三级层次**：用户沉淀技能的内部表示（name/document/content/tools/metadata），按"规划/功能/原子"分层，轨迹聚类去重。
- **addyosmani / Agent-Skills-for-Context-Engineering 的 meta-skill 路由**：加一个 `using-skills` 技能做任务→技能路由决策树，提升小白易用性。
- **agents-spec-skill 技能自带 pytest**：每技能 `tests/test_skill_package.py`，技能结构质量机器可测。
- **Generative-Media-Skills / YouMind 提示词数据化**：ecommerce/prompt_refine 的提示词示例抽成 `references/*.json`，技能正文只留策略，支持管理员热更新（扩展电商/图片场景现成素材）。
