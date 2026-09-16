# g06_agent_skill_c 组扫描报告（SKILLS 类，26 目录）

> 扫描方式：只读分析。逐目录 ls → 读 SKILL.md/README 首部 → 深读高价值技能的 frontmatter/验证脚本/evals 机制。
> 主项目现状对照：主项目「听风AI」已有 skills 库（ecommerce/ppt/image_quality/prompt_refine/critic），当前关注①skills 沉淀与验证机制、②agent 深度优化（黑匣子打开/教学化/小白易用/沉淀训练用户自己的 skills）。
> 评分 0-5：5=高价值可立即迁移；0=与主项目无关。

---

## marketingskills
- 定位：营销领域 Agent Skills 库，约 60+ 个技能覆盖 SEO/CRO/文案/广告/增长全链路。
- 技能领域/技术栈：Marketing / 纯 Markdown SKILL.md（Agent Skills spec，跨 Claude Code/Codex/Cursor/Windsurf）。
- 亮点：
  1. **自动生成技能注册表**：README 内 `<!-- SKILLS:START -->` 注释块 + 脚本同步 60+ 技能表（`scripts/sync-partners.mjs` 模式，见 README L23），目录即索引。
  2. **技能依赖图**：`product-marketing` 为地基技能，其它技能「先读它再动手」；README 有 ASCII 依赖图 + 每个技能 frontmatter 的 description 末尾用 `For X, see Y` 做 Related Skills 交叉引用（`skills/copywriting/SKILL.md` frontmatter 可见），形成显式 skill-to-skill 路由。
  3. **确定性验证脚本**：`validate-skills.sh` 校验 frontmatter（name 1-64 字符小写+连字符、必须匹配目录名、description 1-1024 且含触发词 "when/mention/use"、SKILL.md <500 行、version 必须放 metadata 下），输出 Passed/Warnings/Issues 三态报告 —— 纯 shell 无依赖，CI 可直接跑。
  4. **诚实边界/服务条款分离**：`tools/PARTNERS.md` + `partners.json` 声明赞助商与中性工具的边界，透明度工程化。
- 对主项目价值：直接借鉴（格式规范 + 验证脚本 + 技能互引模式）。
- 借鉴点：
  - 主项目 5 个 skills 可加同类 `validate-skills.sh`（frontmatter 校验：name/description/版本/目录一致性/<500 行门禁），纳入 CI。
  - 在 README/`skills_list.txt` 用注释块自动生成技能注册表，避免手动维护。
  - 在 ecommerce/ppt 等跨技能场景加「先读前置技能」的依赖声明。
- 评分：5

---

## mattpocock__skills
- 定位：「真实工程师技能集」，聚焦解决 agent 与用户对齐失败、工程流程失控，设计哲学是「小而可组合、任何模型可用」，反对 GSD/BMAD 式大而全流程接管。
- 技能领域/技术栈：软件工程工作流（tdd/implement/code-review/diagnosing-bugs/grill-me/handoff/teach 等）+ productivity，Markdown SKILL.md。
- 亮点：
  1. **`teach` 技能 = 教学化工作区协议（对主项目"教学化/沉淀训练用户自己的 skills"最相关）**：把当前目录当教学工作区，用 `MISSION.md`（学习动机）/ `reference/*.html`（压缩知识点=cheat sheet）/ `RESOURCES.md` / `learning-records/*.md`（学习记录≈架构决策记录 ADR，编号 `0001-*.md`，用于计算最近发展区 ZPD）/ `lessons/*.html`（单课=一次完成一个明确小目标）组织状态；引入 **Fluency vs Storage strength**（即时检索 vs 长期记忆）设计「合意困难」的练习。这正是主项目「沉淀训练用户自己的 skills」想要的机制。
  2. **`grill-me` 技能**：用 `disable-model-invocation: true` + `argument-hint` 做成纯交互式提问技能（"A relentless interview to sharpen a plan or design"），主 agent 不自动调用、用户显式触发 —— 是「黑匣子打开/需求澄清」的模板。
  3. **`handoff` 技能**：把会话压缩成 handoff 文档（含 suggested skills 章节、引用既有工件路径、脱敏），解决多 agent 交接上下文丢失 —— 与主项目 SSE/断点续跑思路同构。
  4. 工程化：CHANGELOG + Claude Code plugin 双通道发布（插件=只读可更新 bundle，`npx skills@latest add` = 可编辑副本），`docs/` 按 engineering/productivity 分类。
- 对主项目价值：直接借鉴（尤其 teach 教学化协议）。
- 借鉴点：
  - 主项目若做「训练用户自己的 skills」，直接采用 teach 的工作区文件协议（MISSION/RESOURCES/learning-records/lessons 四件套 + 编号记录 + ZPD 计算）。
  - 把主项目现有技能按「核心交互流程用 SKILL.md、知识点压缩进 references/*.html 打印友好件」重组，降低小白学习成本。
  - 引入 `disable-model-invocation` 区分「自动路由技能」vs「用户显式调用技能」，减少误触发。
- 评分：5

---

## microsoft__SkillOpt
- 定位：微软开源「以训练神经网络的方式训练 agent skills」——把 SKILL.md 当可训练参数，用 rollout→reflect→aggregate→select→update→evaluate 循环 + 留出验证门控（held-out validation gate）自动改进技能文本，零推理期开销。
- 技能领域/技术栈：Skill self-evolution / Python（`pip install skillopt`）/ 多后端（OpenAI/Azure/Claude/Qwen/MiniMax）/ 三执行 harness（direct chat、Codex CLI、Claude Code CLI）。
- 亮点：
  1. **确定性训练循环 + 严格接受门**：候选编辑只有严格提升 held-out 验证分才被接受；有 textual learning-rate budget、rejected-edit buffer、epoch 级 slow/meta update —— 防止技能越改越差。
  2. **产出物是 300-2000 token 的 `best_skill.md`**，可在未改动目标模型上直接部署，跨模型/跨 harness/跨邻近 benchmark 迁移（GPT-5.5 提升 +19~+24 分）。
  3. **SkillOpt-Sleep**：夜间离线自进化引擎（harvest→mine→replay→consolidate + held-out gate），`skillopt-sleep` CLI —— 与主项目「记忆 L1-L3 巩固」方向高度契合。
  4. 工程化完备：PyPI 发版 + CHANGELOG + WebUI（Gradio 监控仪表盘）+ 新 backend/benchmark 接入契约文档。
- 对主项目价值：扩展方向参考（这是研究级方法论，实施成本高，但理念可借鉴）。
- 借鉴点：
  - 主项目 critic 自反思目前是「一次性改进」，可参考 SkillOpt 引入**留出验证集 + 只接受严格提升的改动**，防止 skill 迭代劣化。
  - 把「技能版本 + 验证分数」纳入主项目 skills 元数据，形成可回滚的 skill 迭代历史。
- 评分：4

---

## mono-color-skill
- 定位：单色/双色编辑印刷风 AI 图像生成技能（抗 slop、风格一致性极强），把「设计系统」机器可读化。
- 技能领域/技术栈：图像生成 prompt 工程 / SKILL.md + `design-system/` JSON 目录（colors/compositions/rhythm/typography/carriers/imperfections）+ evals。
- 亮点：
  1. **设计系统目录化（机器可读源真相）**：`design-system/*.json` 存 palette ID/hex、排版角色、构图 ID、节奏档位，SKILL.md 里的 YAML manifest 让 agent「从目录取值，不自由发挥」，风格一致性由数据目录而非散文保证。
  2. **JSON Schema 驱动的 evals**：`evals/schema.json`（JSON Schema draft 2020-12）严格定义每条评估的 assertions（ratio/mode/ink_hexes/plate_roles/layout/exact_text/must_not 等枚举与正则），`evals/evals.json` 含 12+ 条真实用例；`scripts/validate_evals.py` + `validate_design_system.py` 用脚本确定性校验 schema 与目录一致性 —— **这是「技能验证机制」的黄金范例**。
  3. 输出三件套（prompt + 生成图 + recipe note）+ 可复现的 `imperfection_seed`（由 recipe 稳定哈希），支持对照复现。
- 对主项目价值：直接借鉴（evals schema 机制对主项目 prompt_refine/image_quality 技能直接可迁移）。
- 借鉴点：
  - 主项目 image_quality/prompt_refine 技能引入 `evals/schema.json`（JSON Schema 定义 assertions）+ `evals/evals.json`（真实用例）+ validate 脚本，纳入 CI 门禁。
  - 把主项目设计/审美规范（若有）抽成 JSON 目录而非散文，增强一致性。
- 评分：5

---

## narrator-ai-cli-skill
- 定位：AI 电影/短剧解说视频自动生成 CLI 技能（搜片→选模板→选 BGM→选配音→生成文案→合成视频全流程）。
- 技能领域/技术栈：视频二创/TTS/CLI 集成，SKILL.md 直接嵌入 `metadata.openclaw.install`（pip 安装说明 + requires.bins + env `NARRATOR_APP_KEY`）。
- 亮点：
  1. **frontmatter 带完整安装契约**：`version` + `license` + `metadata.openclaw`（emoji/primaryEnv/install 的 pip spec/requires bins+env）——技能自描述依赖与环境要求。
  2. **references/ 分主题拆分**（resources/workflows/magic-video/operations），SKILL.md 只留决策流 + 管线图 + Agent Rules。
  3. **强约束 Agent Rules**：`Always/Never` 两栏（确认后行动、绝不发明数据、分页拉全再 grep、轮询必须用 while 循环、易错参数对照表如 `task_id` vs `task_order_num`）——把真实踩坑写成硬规则。
- 对主项目价值：局部借鉴（无自有视频上游，但 CLI 集成与规则书写模式可参考）。
- 借鉴点：
  - 主项目如需给用户暴露 cf_solver 等 CLI 技能，用同样 frontmatter 声明安装与环境要求。
  - 用 Always/Never 两栏硬规则沉淀主项目技能里的真实踩坑（如 SSE Last-Event-ID、路由参数易错点）。
- 评分：3

---

## nuwa-skill
- 定位：「女娲造人术」——从人名/模糊需求蒸馏出可运行的人物思维 Skill（心智模型/决策启发式/表达 DNA/反模式/诚实边界）。
- 技能领域/技术栈：Skill 生成/人物画像蒸馏 / SKILL.md（多语言 README 营销化运营）。
- 亮点：
  1. **「提炼思维框架而非复制言论」**：明确 HOW they think vs WHAT they said，输出为可运行的认知操作系统五件套（镜片/直觉规则/DNA/反模式/诚实边界）——这是「把模糊人物知识沉淀成技能」的领域方法论。
  2. **双路径入口分流**（明确人名→直接蒸馏；模糊需求→诊断推荐→再蒸馏）+ 成本档位明示（快速/标准/深度三档，开跑前说清成本量级）——「小白易用 + 预算透明」。
  3. 本地语料优先策略（一手素材 > 网络搜索），默认值策略「确认不阻塞交付」。
- 对主项目价值：直接借鉴（「训练用户自己的 skills」+「把专家/场景沉淀为技能」正是主项目关注方向）。
- 借鉴点：
  - 主项目可做「蒸馏技能」：把用户口头经验/单次任务产出蒸馏成可复用 skills，采用 nuwa 的「HOW 而非 WHAT + 反模式 + 诚实边界」框架。
  - 主项目 MCP 预算门禁可借鉴 nuwa 的「三档成本明示 + 开跑前确认」交互。
- 评分：4

---

## obsidian-skills
- 定位：Obsidian 生态技能集（json-canvas/obsidian-bases/obsidian-markdown/obsidian-cli/defuddle）。
- 技能领域/技术栈：Obsidian 工具链 / 简洁 SKILL.md（frontmatter 只有 name+description，正文即 JSON Canvas spec 等规范说明）。
- 亮点：
  1. 极简 frontmatter（name+description），技能即「格式规范文档」，无脚本无验证 —— 展示轻量技能的最低成本形态。
- 对主项目价值：无价值（工具生态无关，形态过简）。
- 借鉴点：无（仅佐证 SKILL.md 可以很轻）。
- 评分：1

---

## pi-skills-main
- 定位：Pi (π) 模型的实用技能集（brave-search/browser-tools/transcribe/youtube-transcript/gccli/gdcli/gmcli/vscode）。
- 技能领域/技术栈：工具类技能（搜索/转录/浏览器/VSCode），SKILL.md + 一个可执行文件（search.js/transcript.js）单文件实现。
- 亮点：
  1. 每技能 = SKILL.md + 单个依赖 package.json 的 JS 脚本，把「重逻辑锁进脚本、SKILL.md 只管触发与用法」的极简模式做到极致。
- 对主项目价值：局部借鉴（形态示范：脚本封装确定性操作）。
- 借鉴点：主项目技能脚本统一为「单文件 CLI + SKILL.md 引用」的最小形态。
- 评分：2

---

## pm-skills
- 定位：产品经理全链路技能库（20 个技能：PRD/评审/优先级/路线图/实验/埋点/问卷/竞品/复盘/原型 + 7 个专家顾问团）。
- 技能领域/技术栈：产品管理领域方法论（Cagan/Torres/俞军/Mom Test/Story Mapping），SKILL.md。
- 亮点：
  1. **总控路由技能 `pm-master`**：不自己产出内容，只「判断问题类型→路由到正确 Skill 或编排多 Skill 链路→保证上一步产出能被下一步直接使用」，成员名册用表格声明每个子技能的输入→输出契约 —— **技能编排（orchestration）的示范**，与主项目 DAG 编排思路呼应。
  2. 单一职责技能划分：每个 pm-* 技能只做一件事，frontmatter description 写触发词。
- 对主项目价值：局部借鉴（编排总控模式可借鉴到主项目 skills 入口）。
- 借鉴点：主项目可增加一个「skills 总控」入口技能，按用户意图路由/编排 ecommerce→ppt 等多技能接力，并声明每个技能的输入→输出契约。
- 评分：3

---

## ppt-agent-skills
- 定位：专业 PPT 全流程 AI 生成技能，模拟顶级设计公司工作流（调研→大纲→策划稿→设计稿），输出 HTML 演示文稿。
- 技能领域/技术栈：PPT/演示设计 / SKILL.md「主控制台合同」+ `references/`（blocks/charts/layouts/prompts/playbooks）+ `scripts/`（10+ 校验器）。
- 亮点：
  1. **主控制台合同（最强工程约束范例）**：主 agent「只做维护计划/调用 harness/管理 subagent/校验 Gate」，「不做」代写任何正式产物——内容生产全量外包给 subagent，主 agent 手写产物=合同违规；步骤锁（P0→P5 固定链）、Gate 守门（前序 Gate 不过不进入下步）、失败只允许 RETRY_CURRENT_STEP 或 ROLLBACK、人工审计断点。
  2. **subagent 强制调度 + 上下文隔离**：每步必须创建对应类型 subagent（ResearchSynth/Outline/Style/PageAgent-N），subagent 只可见 prompt 文件显式传递的内容，主 agent 对话历史/环境变量不泄露 —— 防越权与上下文污染。
  3. **10+ 确定性校验器**：`contract_validator.py`（校验 interview/search/outline/style/planning/delivery-manifest 各工件契约）、`planning_validator.py`、`check_skill.py`（防 docs 与 validator 漂移）、`visual_qa.py`、`html2png` 等 —— 覆盖「格式契约 + 内容契约 + 视觉验收」三层。
- 对主项目价值：直接借鉴（主项目已有 ppt skill，这份「合同化 + 子代理隔离 + 校验器」工程可直接对标升级）。
- 借鉴点：
  - 主项目 ppt skill 引入「主 agent 只编排不代写产物 + 每步校验器 + Gate 门控 + 失败只重试当前步」的合同化改造。
  - 主项目多 subagent 编排借鉴「上下文隔离」：subagent 只见显式 prompt 文件，防越权。
  - 用 contract_validator 式脚本校验主项目 skills 的中间产物格式。
- 评分：5

---

## qtyasupo__image25-prompt-skill
- 定位：GPT Image 2.5 提示词技能（文生图/参考图编辑/中文海报/多图融合/草图/系列素材）。
- 技能领域/技术栈：图像 prompt 工程 / SKILL.md + `references/` 按任务分表（prompt-design/editing/templates/model-notes/verification/sources）。
- 亮点：
  1. **任务边界宣言（防越权/防谎报）**：「不调用生图、不要求 API Key」「工具未暴露后端版本时标注模型版本未暴露；在提示词中写模型名不会切换模型。不得把宿主默认生成包装成指定版本实测」「未收到或无法查看的图不得描述成已检查」——诚实性硬规则，直击主项目「真实闭环」红线。
  2. **「按需参考」表格**：SKILL.md 主体只有决策流程 + 输出协议，具体知识全在 references，任务类型→该读哪篇的映射表；「简单请求不必读完所有参考」——上下文按需加载。
  3. **输出协议标准化**：默认交付「可直接使用的提示词 + 关键验收点 2-4 项」，没有图时只做文字审查不做视觉验收。
  4. 工程化：`scripts/validate_package.py` + `tests/test_validate_package.py` 校验技能包完整性；frontmatter 带 `verified_on` 日期。
- 对主项目价值：直接借鉴（prompt 类技能的设计范式）。
- 借鉴点：
  - 主项目 prompt_refine/image_quality 技能加入「任务边界 + 诚实性硬规则」段落（不谎报模型版本、没图不做视觉验收）。
  - 采用「决策流程在 SKILL.md、详情在 references + 按需参考表」的上下文节俭结构。
- 评分：5

---

## repo-to-skill
- 定位：从 GitHub 开源仓库自动生成可用的 agent skill（克隆→分析→生成→测试→评估）。
- 技能领域/技术栈：Skill 生成器 / SKILL.md 驱动 + `scripts/analyze_repo.sh` + `references/`（eval-schemas/skill-format）。
- 亮点：
  1. **「生成+测试+评估」闭环**：不仅生成 SKILL.md，还「用测试提示词与断言评估技能」——技能生成自带验收，与主项目「真实闭环」一致。
  2. 分析优先级清单（README→docs→examples→CLI help→依赖→源码），「stop when you have enough」避免过度分析。
- 对主项目价值：局部借鉴（主项目「沉淀训练用户自己的 skills」可复用此管道思路）。
- 借鉴点：若主项目做「仓库→技能」工具，直接移植该分析顺序 + 生成后自测闭环。
- 评分：3

---

## reverse-skill
- 定位：大型安全/逆向技能库（40+ 模块），主控 + 路由 + 独立模块，每个模块独立 SKILL.md。
- 技能领域/技术栈：逆向/渗透/恶意分析（api-security/apk-reverse/ida-reverse/js-reverse/firmware-pentest 等），多平台脚本。
- 亮点：
  1. **确定性路由契约（MASTER-ROUTING.md）**：「先路由后动手」→ PRIMARY 路径 + 一句话依据 → case-init scope（auth 未 granted 禁止 ACT）→ 指定 lead/specialist 角色 → 工具路径只认 tool-index（缺则 bootstrap）→ Evidence→Finding→Path 结论链；路由用 `config/routing.json` + 平台原生 router 脚本（Windows/Linux 双实现，语义一致）。
  2. **索引自动生成**：`INDEX.md` 由脚本从各模块 frontmatter description 自动生成（"请勿手改"），保证路由表与真实技能同步。
  3. **scope 门禁 + 授权模型**：case-guard（未就绪 exit 2）、Force 不能绕过硬门、离线样本 preset——安全边界工程化，与主项目「权限边界」理念一致。
  4. 深度分级：1 个主控 + 1 层子路由 + 40 模块，模块间职责清晰、可独立拷走。
- 对主项目价值：扩展方向参考（体量过大，但路由/索引/门禁机制可借鉴）。
- 借鉴点：
  - 主项目若 skills 数量增长到 10+，引入「路由主控技能 + routing.json + 自动生成索引」的分层治理。
  - 借鉴「工具路径只认 tool-index、缺工具走 bootstrap」的依赖管理。
- 评分：4

---

## scientific-agent-skills
- 定位：科研领域大规模 Agent Skills 库（120+ 技能覆盖生物/化学/医学/数据科学），生产级工程化。
- 技能领域/技术栈：科学计算/生物信息学（scanpy/qiskit/rdkit/dask/polars/transformers 等按库封装的技能），SKILL.md + plugin.json。
- 亮点：
  1. **plugin.json 标准化发布**：遵循 `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`（name/version/author/homepage/license/keywords），技能库可作为插件市场发布。
  2. **安全扫描流水线（scan_skills.py）**：用 `cisco-ai-skill-scanner`（LLM 分析器 BehavioralAnalyzer/LLMAnalyzer/TriggerAnalyzer）对全部技能做安全扫描，输出 `docs/security-report.md` + `.json`；**增量缓存**（技能内容未变则复用上次报告，按内容哈希判定）+ 并发扫描（8 workers）+ 30 天强制全扫——防技能投毒/恶意 prompt 注入。
  3. **按库封装模式**：每个 Python 库一个技能（目录名=库名），frontmatter description 即触发词，标准化 SKILL.md + assets + references + scripts 四件套。
- 对主项目价值：直接借鉴（安全扫描 + plugin 标准化对主项目 skills 治理直接可用）。
- 借鉴点：
  - 主项目对自有 skills 引入内容哈希 + LLM 扫描的安全审查流水线（防第三方 skills 注入恶意指令）。
  - 主项目 skills 库可加 plugin.json 以支持市场发布/版本管理。
- 评分：4

---

## scroll-video-website-skill
- 定位：滚动视频网站（scroll-driven video site）生成技能。
- 技能领域/技术栈：前端动效网站 / 极简 SKILL.md + `references/optimize.md` + `agents/openai.yaml`。
- 亮点：
  1. 配套 `agents/openai.yaml`（OpenAI 兼容 agent 配置文件），技能同时适配多 runtime。
- 对主项目价值：无价值（单点小技能）。
- 借鉴点：无。
- 评分：1

---

## shuohao-skills
- 定位：AI 短剧/小说五件套技能库（novel-outline/novel-storyboard/novel-characters/novel-script/novel-art），质量门由脚本确定性检查。
- 技能领域/技术栈：短剧内容生产 / Node.js 标准库脚本（零 npm 依赖）+ SKILL.md。
- 亮点：
  1. **脚本确定性质量门（14/17 道）**：novel-outline 有 14 道、novel-storyboard 有 17 道质量门「全部由脚本确定性检查（角色分档上限、场景上限动态、爽点间隔≤3 集、钩子悬念必填……），不靠模型自觉」——**把「主观质量」转成「可执行断言」的极致示范**，与主项目「真实闭环/反伪实现」直接共鸣。
  2. **frontmatter 声明运行时契约**：`allowed-tools`（Read/Write/Bash/Task/Glob）+ `triggers`（多语触发词）+ `metadata.requires.bins`（node>=18，只用标准库）+ `runtimes`（claude-code/codex）——技能可移植性显式化。
  3. **门失败累积（.gates.jsonl + stats）试点**：只在 novel-storyboard 上跑「门失败日志」，CLAUDE.md 明言「先验证 stats 是否指向真问题，再决定推广，不主动推广」——克制的数据驱动迭代（与主项目「Converge 达标即停」一致）。
  4. 自包含原则：CLAUDE.md 规定「skill 必须自包含可单独拷走，不依赖第三方 skill；外部方法论学习后内化为 references 并注明来源」「渲染产物不进版本控制」。
- 对主项目价值：直接借鉴（主项目 ppt/storyboard 类技能 + 质量门机制）。
- 借鉴点：
  - 主项目 ppt skill 引入「脚本确定性质量门 + .gates 失败日志」：用可执行断言替代模型自觉，先试点再推广。
  - 技能 frontmatter 增加 allowed-tools/triggers/requires/runtimes 契约字段。
  - 遵循「自包含 + 渲染产物不进版本控制」规范。
- 评分：5

---

## skillroster
- 定位：SkillRoster——统一盘点多个 agent 里散落的 skills，为每个 agent 配置合适的「Core + On-demand」技能名册，确定性 CLI（Rust），带 Plan/Apply/Undo。
- 技能领域/技术栈：Skill 治理工具链 / Rust CLI（Cargo）+ SQLite + 不可变 Plan 模型。
- 亮点：
  1. **治理三原则「看得清/配得准/改得回」**：先用确定性 CLI 盘点事实（Snapshot+Evidence→Findings），AI 只负责理解意图、CLI 返回有边界的事实并执行已批准变更；**不加载预写结果**（公开验收实际执行 Scan/Report/Plan/Apply/Undo）。
  2. **不可变 Plan + Receipt + Undo**：没有完整 Plan 和用户确认就不改 agent 文件；Apply 留 Receipt、可撤销——与主项目「不可逆操作需授权」高度一致，且做成工具。
  3. **Core vs On-demand 技能分层**：为每个 agent 保留常用 Core 技能，窄能力转可检索 On-demand——直接解决「技能占默认上下文」问题（主项目 skills 也会面临）。
  4. 自身也是一个 SKILL.md（`skill/` 目录含模板 + validate-metadata.py），dogfooding。
- 对主项目价值：扩展方向参考（治理工具是独立产品，但理念可借鉴；主项目 skills 少暂时不需要）。
- 借鉴点：
  - 主项目若 skills 增长、多 agent 部署，用「Core/On-demand 分层 + 使用证据 + 可撤销变更」思路管理。
  - 借鉴「确定性事实 vs agent 判断」分离：facts 由脚本产出，不靠模型自觉。
- 评分：4

---

## skills（匿名目录）
- 定位：通用 skills 集合（package.json + scripts + assets + skills/）。
- 技能领域/技术栈：未命名技能库。
- 亮点：
  1. 结构标准（package.json 管理依赖 + skills/ 目录），说明技能库工程化需要包管理。
- 对主项目价值：无价值（信息量低）。
- 借鉴点：无。
- 评分：1

---

## skills-best-practices
- 定位：Agent 技能编写最佳实践指南（结构/frontmatter 可发现性/渐进披露/确定性脚本/技能组合）。
- 技能领域/技术栈：方法论文档 + 配套 skillgrade 工具（LLM 评估 + 回归预防）+ 一个示例技能（含 validate-metadata.py）。
- 亮点：
  1. **可发现性优化法则**：name 1-64 字符小写+连字符、必须匹配目录名；description ≤1024 且带**负面触发词**（"Don't use it for Vue/Svelte..."）——路由准确性。
  2. **渐进披露 + JiT 加载**：SKILL.md <500 行只做导航，细节放 references/scripts/assets 且**只一层深**；显式指示 agent 何时读某个文件（"See references/... for..."）；用相对路径正斜杠。
  3. **确定性脚本封装**：脆弱/重复操作锁进 scripts/，脚本返回描述性错误信息让 agent 自纠；不打包库代码。
  4. **技能组合（router skills）**：子技能条件包含的 YAML 范例。
- 对主项目价值：直接借鉴（这是技能编写的浓缩规范，可直接作为主项目 skills 规范文档）。
- 借鉴点：
  - 主项目 skills 规范直接采用：SKILL.md<500 行 / references 一层深 / JiT 显式加载 / 负面触发词 description / 脚本返回自纠错误信息。
- 评分：5

---

## skills-manager
- 定位：跨 agent 的 Skills 管理桌面应用（Tauri 2 + Vite + React），统一技能库 + 市场 + 预设 + 多工作区（Global/Project/Agent）+ 备份同步。
- 技能领域/技术栈：Skill 生命周期管理 GUI / Tauri2 + React + Tailwind + TypeScript。
- 亮点：
  1. **Presets 机制**：技能分组为命名预设，一键在指定 agent 作用域激活/停用（一次性拷贝非实时同步）——批量治理体验。
  2. **「让 agent 管理 skills」**：agent 通过驱动 Skills Manager 来安装/部署/报告技能位置，而不是直接写 agent 文件夹（保持来源/预设/更新追踪/每 agent 状态完整）——主项目已有桌面 Tauri2 sidecar，方向直接契合。
  3. 多工作区视图 + 备份与多设备同步 + Marketplace（skills.sh）。
- 对主项目价值：局部借鉴（主项目已有 Tauri2 桌面端，可扩展技能管理能力）。
- 借鉴点：
  - 主项目桌面端可加「Skills 管理」面板：技能库浏览/预设/安装到指定 agent，避免直接改 .claude/skills。
- 评分：3

---

## soul-grader-skill
- 定位：Hermes Agent SOUL.md 的评分/评审/改写技能，附带完整评分标准研究工件。
- 技能领域/技术栈：Agent 身份文件评审 / SKILL.md + references/（grading-standard + field-guide + wording）。
- 亮点：
  1. **「唯一规范源」原则**：评分标准只来自随技能捆绑的 `references/soul-md-grading-standard.md` 等研究工件，「不导入通用 prompt 技巧、个人品味、网页文章或 vibes」；冲突时按源等级裁决，参考缺失则停止报告而非凭记忆打分——防评审漂移。
  2. **`skill_view(name, file_path)` 显式加载**：以代码块形式展示加载语法，强制 agent 先加载标准再评。
  3. 附带 `agents/openai.yaml` 配置 + `validate_skill.py` + SSR 发布卫生规范（示例匿名化、路径相对化、无密钥）。
- 对主项目价值：局部借鉴（「唯一规范源 + 源等级裁决」对主项目 critic 自反思技能是强启发）。
- 借鉴点：
  - 主项目 critic skill 可声明「评分标准唯一来源 = 捆绑的 rubric 文件，不引入外部品味」，并规定标准冲突时按等级裁决、缺标准则停止而非乱评。
- 评分：4

---

## taste-skill
- 定位：「Anti-Slop 前端设计框架」技能库——为 premium 前端审美提供风格化技能（brandkit/redesign/brutalist/soft/output 等 13 个变体技能 + 一个主 taste 技能）。
- 技能领域/技术栈：前端设计美学 / SKILL.md 集合 + `skill.sh` 本地技能注册表。
- 亮点：
  1. **风格变体技能族 + 注册表**：`skill.sh` 用 bash associative array 维护技能名→SKILL.md 路径映射（taste-skill/v1/gpt-taste/image-to-code/brandkit/brutalist/soft...），一条命令列出可用技能——轻量技能发现。
  2. 主打「一个主技能 + 多个风格变体」组合（main + variants），用户按审美取向选技能。
- 对主项目价值：无价值（纯前端审美域，主项目前端已有设计规范）。
- 借鉴点：风格变体 + 本地注册表模式可作为主项目多风格 prompt 技能组织参考。
- 评分：2

---

## treylom__prompt-engineering-skills
- 定位：Prompt 工程技能集合（claude-4.7/gemini-3.1/gpt-5.5 各代模型策略 + image-prompt-guide + 通用 prompt 指南）。
- 技能领域/技术栈：Prompt engineering / SKILL.md + references/full.md 巨型参考 + commands/（prompt-sync/prompt-update 等命令）。
- 亮点：
  1. **路由索引 + 巨型参考分离**：`claude-4.7-prompt-strategies` 本体只有 30 行路由索引，正文全在 `references/full.md`（约 900 行），SKILL.md 附「grep 锚点 + 行号表」让 agent 精准定位段落——**超长知识单文件 + 锚点导航**模式。
  2. `version` + `updated` + `disable-model-invocation` 字段；模型版本策略按代管理（旧代=路由索引指向历史，新代=基准文件）。
- 对主项目价值：局部借鉴（锚点导航模式可改善主项目超长 references）。
- 借鉴点：主项目长 reference 文档加「grep 锚点 + 行号表」，SKILL.md 只做索引；模型策略按版本/代管理（与主项目多模型适配呼应）。
- 评分：3

---

## ui-ux-pro-max-skill
- 定位：UI/UX 设计智能技能（79 UI 风格/192 色板/74 字体配对/119 UX 指南/25 图表类型/22 技术栈），数据驱动设计系统。
- 技能领域/技术栈：前端设计 / skill.json（结构化元数据）+ `stack/`（各技术栈接入）+ `cli/`（Playwright 测试 + scripts）+ `src/ui-ux-pro-max`。
- 亮点：
  1. **skill.json 结构化元数据**：name/displayName/description/version/author/license/keywords/**platforms（19 个 runtime）**——跨平台发布标准。
  2. **数据目录化**：大量设计资产（风格/色板/字体/指南）以数据形式组织，CLI 含 Playwright 配置做真实浏览器验收。
- 对主项目价值：扩展方向参考（数据驱动设计系统 + 跨平台 skill.json）。
- 借鉴点：主项目 image/design 类技能可用 skill.json 元数据 + 数据目录驱动，前端交互用 Playwright 真实验收。
- 评分：2

---

## wuyoscar__GPT-Image2-Skill
- 定位：GPT Image 2/2.5 Prompt Gallery + 2 个 agent skills + Python CLI（163 条样例 31 类）。
- 技能领域/技术栈：图像生成 / Python ≥3.11 CLI（`src/gpt_image_cli/cli.py`）+ pytest 测试（test_cli/test_credentials）+ skills/（gpt-image/get-prompt-from-image）。
- 亮点：
  1. **技能 + CLI + Gallery 三合一**：CLI 封装提示词检索，技能驱动 agent，163 条 gallery 样例作上下文。
  2. **凭据安全测试**：`tests/test_credentials.py` 专门测凭据处理（与主项目「密钥仅环境变量注入」红线契合）。
  3. pyproject.toml + CHANGELOG + 双语文档完整工程化。
- 对主项目价值：局部借鉴（主项目可参考「CLI 封装 + 测试 + 安全测试」模式做 prompt 技能）。
- 借鉴点：技能配套 CLI + pytest（含凭据安全用例）作为主项目 skills 的工程化样板。
- 评分：3

---

## z-skills
- 定位：中文创作/知识管理自动化技能集（17 个：网页采集/视频下载/视频学习/文档解析/邮件读取/MD转Word-PDF/证据型问答/手写PPT/四格漫画等），面向中文用户。
- 技能领域/技术栈：内容自动化（python 脚本）/ 每技能 SKILL.md + scripts + evals + examples，双语触发词。
- 亮点：
  1. **evals/evals.json 每技能标配**：如 z-md-to-pdf 有 3 条评估用例（prompt/expected_output/files），且每条有「完成标准」（非空/页数合理/中文可提取），配合脚本验收——中文技能也做 evals。
  2. **「完成标准」显式化**：SKILL.md 开头即「一次任务只有同时满足以下条件才算完成」清单（如 pdfinfo 可读 + pdftotext 能提取中文正文），把验收前置。
  3. **边界声明**：README 用表格明确 z-web-pack 与 z-video-downloader 的职责边界（采集 vs 下载，发现视频只写 media-inventory 不下载）。
  4. 技能自包含：`setup.sh` 自动补环境 + compatibility 字段声明平台依赖。
- 对主项目价值：直接借鉴（中文技能 + evals + 完成标准的完整范例）。
- 借鉴点：
  - 主项目 skills 统一加 evals/evals.json（真实中文用例）+ SKILL.md 开头「完成标准」清单。
  - 用 README 表格声明相邻技能职责边界，防误路由。
- 评分：4

---

# 本组汇总：Top3 最值得主项目借鉴项

**1. 脚本确定性质量门 + evals schema（shuohao-skills / mono-color-skill / z-skills）— 评分 5，直接迁移**
- 把「主观质量/风格一致性」转成「可执行断言」：mono-color 用 JSON Schema 严格定义 evals assertions（枚举+正则+must_not），shuohao 用 Node 脚本做 14/17 道确定性质量门（不靠模型自觉），z-skills 每技能标配 evals.json + SKILL.md 开头「完成标准」清单。
- 迁移：主项目 prompt_refine / image_quality / ppt skills 增加 `evals/schema.json` + `evals/evals.json`（中文真实用例）+ validate 脚本，纳入 CI；把 critic 自反思从「一次性改进」升级为「留出验证集 + 只接受严格提升」（借鉴 SkillOpt 理念）。

**2. teach 教学化工作区协议（mattpocock__skills）+ 蒸馏方法论（nuwa-skill）— 评分 5，直接迁移**
- 直接命中主项目「教学化/小白易用/沉淀训练用户自己的 skills」方向：teach 用 MISSION/RESOURCES/learning-records/lessons 四件套 + 编号学习记录（≈ADR）+ ZPD 计算 + Fluency vs Storage 设计练习；nuwa 用「提炼 HOW 而非 WHAT + 反模式 + 诚实边界 + 三档成本明示」把模糊人物/经验蒸馏成可运行技能。
- 迁移：主项目做「用户自己的 skills」功能时，落地 teach 工作区协议 + nuwa 蒸馏框架，形成「经验→技能」闭环。

**3. 主控制台合同 + 子代理上下文隔离 + 契约校验器（ppt-agent-skills）+ 技能工程规范（skills-best-practices / marketingskills / scientific-agent-skills）— 评分 5，直接迁移**
- ppt-agent 证明「主 agent 只编排不代写、每步校验器、Gate 门控、失败只重试当前步、subagent 只可见显式 prompt」能让复杂技能工程化；skills-best-practices 浓缩了 SKILL.md<500 行/references 一层深/JiT 加载/负面触发词/自纠脚本等规范；marketing 的 validate-skills.sh + 自动索引、scientific 的 plugin.json + 内容哈希安全扫描补全治理闭环。
- 迁移：主项目 ppt skill 按「合同化」改造；整体 skills 库引入 frontmatter 校验脚本（CI 门禁）、plugin.json 发布元数据、以及技能安全扫描（防第三方投毒）。

---

## 附：26 目录一行结论（评分）
| 目录 | 一句话 | 评分 |
|---|---|---|
| marketingskills | 营销技能库：自动索引 + validate-skills.sh + 技能互引 | 5 |
| mattpocock__skills | teach 教学化工作区协议 + grill/handoff，命中"训练用户 skills" | 5 |
| microsoft__SkillOpt | 技能自进化训练器：留出验证门控 + best_skill.md 可回滚迭代 | 4 |
| mono-color-skill | 设计系统 JSON 化 + JSON Schema evals（黄金范例） | 5 |
| narrator-ai-cli-skill | CLI 技能：frontmatter 安装契约 + Always/Never 踩坑硬规则 | 3 |
| nuwa-skill | 人物/经验蒸馏成技能：HOW 思维框架 + 三档成本 | 4 |
| obsidian-skills | Obsidian 工具技能，形态过简 | 1 |
| pi-skills-main | 技能=SKILL.md+单脚本极简形态 | 2 |
| pm-skills | 20 技能 + pm-master 总控路由/编排 + 输入→输出契约 | 3 |
| ppt-agent-skills | 主控制台合同 + 子代理隔离 + 10+ 契约校验器（最强工程范例） | 5 |
| qtyasupo__image25-prompt-skill | prompt 技能范式：任务边界 + 按需参考 + 输出协议 | 5 |
| repo-to-skill | 仓库→技能生成管道（分析→生成→测试→评估） | 3 |
| reverse-skill | 40 模块分层：确定性路由 + 自动索引 + scope 门禁 | 4 |
| scientific-agent-skills | 120 技能 + plugin.json + LLM 安全扫描（增量缓存） | 4 |
| scroll-video-website-skill | 单点动效网站技能 | 1 |
| shuohao-skills | 短剧技能：14/17 道脚本质量门 + frontmatter 运行时契约 + 门失败试点 | 5 |
| skillroster | Rust 技能治理 CLI：Core/On-demand 分层 + 不可变 Plan/Undo | 4 |
| skills | 未命名技能库，信息量低 | 1 |
| skills-best-practices | 技能编写浓缩规范（可发现性/渐进披露/确定性脚本） | 5 |
| skills-manager | Tauri2 跨 agent 技能管理 GUI（Presets/多工作区/备份） | 3 |
| soul-grader-skill | 评审技能：唯一规范源 + 源等级裁决 + 缺标准即停 | 4 |
| taste-skill | 前端审美风格变体技能族 + 本地注册表 | 2 |
| treylom__prompt-engineering-skills | 路由索引 + 900 行 full.md 巨文 + grep 锚点导航 | 3 |
| ui-ux-pro-max-skill | 数据驱动设计系统 + skill.json 跨平台元数据 | 2 |
| wuyoscar__GPT-Image2-Skill | 技能+CLI+gallery 三合一 + pytest（含凭据安全测试） | 3 |
| z-skills | 中文技能 17 个：每技能 evals.json + 完成标准 + 边界声明 | 4 |
