# 扫描报告 · g05_agent_skill_b（28 目录）— 主协调补扫版

> 生成：2026-09-16 ｜ 原 sub-agent（scan_g05）idle 但未落盘交付物，由主协调按任务卡补扫 28 目录全部读取（ls 结构 + README/配置首部定位 + 高价值深入）。
> 纪律：只读分析，未修改任何参考项目文件。评分 0-5。
> 主项目背景：听风AI（FastAPI 图像/对话网关 + agent 化）关注 ①技能沉淀/教学化/小白易用 ②电商/PPT/多模态扩展 ③工程规范。

---

## 1. anthropics__skills — ★★★★★
- **定位**：Anthropic 官方 Agent Skills 标准实现库（`skills/` + `spec/` + `template/`），配套 agentskills.io 规范。
- **技术栈**：Markdown SKILL.md + 可选 scripts + frontmatter。
- **亮点**：①官方 **Agent Skills 规范**（agentskills.io）——SKILL.md frontmatter（name/description）+ 渐进式披露（正文按需注入）的标准定义源；②`template/` 给出了新建技能的官方骨架；③技能与 Claude Code/Cursor/Codex 跨工具可移植。
- **对主项目价值**：直接借鉴（主项目 `api/skills/` 已有 loader，但未对齐官方 frontmatter/渐进式披露规范）。
- **借鉴点**：用官方 spec 校准 `api/skills/loader.py` 的 frontmatter 解析；新增 `template/` 式技能骨架生成器；正文「按需注入」替代全量注入。
- **评分**：5

## 2. antigravity-awesome-skills-main — ★★★★
- **定位**：1,381+ 可安装 Agent Skill 的巨型目录库（CATALOG.md + registry-sync: skills=1381）。
- **技术栈**：SKILL.md 集合 + npm 安装器 + bundles/workflows。
- **亮点**：技能**目录检索/安装/捆绑分发**的生态化组织（registry-sync 版本化、changelog、贡献规范）。
- **对主项目价值**：局部借鉴——主项目若开放技能市场，可复用其「目录 + 分类 + 安装器」组织模型。
- **借鉴点**：`CATALOG.md` 式技能索引页（前端 Agent 页可加）；技能安装/卸载幂等流程。
- **评分**：4

## 3. claude-skills-main — ★★★★
- **定位**：233 个生产级 Claude Code skills/plugins，覆盖 11 个编码工具（engineering/DevOps/marketing/compliance/C-level）。
- **技术栈**：SKILL.md + 插件，跨工具兼容。
- **亮点**：①技能**覆盖面广度**与分级（通用 vs 角色化）；②AUDIT_REPORT/CHANGELOG/CONVENTIONS 工程化；③跨 11 工具单一来源（一套技能多处可用）。
- **对主项目价值**：局部借鉴——主项目 5 类 skills（ecommerce/ppt/image_quality/prompt_refine/critic）可对照其覆盖与工程规范，补充如 compliance/marketing 类模板。
- **借鉴点**：技能库的目录分层（通用层/业务层/角色层）；CHANGELOG 式技能版本演进。
- **评分**：4

## 4. book-to-skill — ★★★★
- **定位**：把「一本书」蒸馏成可安装的 SKILL 集合（Booklin wizard：书 → 有序网格的技能集）。
- **技术栈**：Markdown + 生成管线（AGENTS.md/CLAUDE.md/CHANGELOG 完备）。
- **亮点**：**知识 → 技能的结构化蒸馏方法论**（章节拆分、要点提取、技能化打包）。
- **对主项目价值**：直接命中「沉淀训练用户自己的 skills」——用户可把自己的书籍/文档转成 agent 技能。
- **借鉴点**：新增 `POST /v1/agent/skills/from-doc`（用户上传文档 → LLM 蒸馏候选技能 → 审批 adopt，与 SkillClaw 闭环衔接）。
- **评分**：4

## 5. baoyu-skills — ★★★
- **定位**：宝玉维护的技能集（中英双语，CHANGELOG 完善）。
- **技术栈**：SKILL.md 集合 + docs。
- **亮点**：多语言（中英）技能文档组织；CHANGELOG 双语文档。
- **对主项目价值**：局部借鉴——中文社区技能组织的样例；配合主项目 i18n 方向。
- **评分**：3

## 6. benjamin-plus-skill — ★★★★★
- **定位**：benjamin-plus 技能（带 hooks、RULESET.md、EXPECTED-RESULTS.md、SHA256SUMS.txt、injected-instruction.md 的可验证技能包）。
- **技术栈**：SKILL.md + hooks + 规则集 + 校验和 + 预期结果清单。
- **亮点**：①**EXPECTED-RESULTS.md**（预期结果显式化——技能质量可验收）；②**SHA256SUMS.txt**（分发完整性校验）；③hooks + injected-instruction（运行时注入 + 钩子）。
- **对主项目价值**：直接借鉴——技能「可验证/可校验/可验收」的完整样例，对准主项目「真实闭环」铁律。
- **借鉴点**：技能包加 `expected_results` 字段（DAG 重放验证）；技能分发加哈希校验；前端技能详情展示预期结果清单（教学化）。
- **评分**：5

## 7. dashi-ppt-skill — ★★★★★
- **定位**：大师 PPT / 网页 PPT / **可编辑 PPTX** 生成技能，npm-dist + skills/。
- **技术栈**：SKILL.md + 生成管线（PPTX 可编辑 = OOXML 写回）。
- **亮点**：①「网页 PPT + 可编辑 PPTX 双格式」；②npm-dist 分发；③直接命中主项目 PPT 扩展方向（ppt skill 已存在，此为其增强范式）。
- **对主项目价值**：直接借鉴（PPT 扩展 No.1 参照，与 ppt-master 互补）。
- **借鉴点**：主项目 `api/skills/ppt/` 升级为「可编辑 PPTX 输出 + 网页预览 + 模板体系」；前端 PPT 页增加模板选择与预览。
- **评分**：5

## 8. feichanggege__ecommerce-visual-copywriting-skill — ★★★★★
- **定位**：电商视觉文案设计 Skill（SKILL.md + SKILL.en.md + ROADMAP，中英）。
- **技术栈**：SKILL.md 中文电商文案方法论。
- **亮点**：①电商视觉文案（主图/详情页文案策略）系统性方法论；②双语（中文主 + English）；③ROADMAP 演进规划。
- **对主项目价值**：直接借鉴（用户明确提到电商场景；v12 深侦察已标其为 SKILL 黄金模板引用，此处确认）。
- **借鉴点**：主项目 `api/skills/ecommerce/` 补「视觉文案」子技能（文案方法论 + 生成模板 + 自审清单）；双语 frontmatter。
- **评分**：5

## 9. kangarooking__promo-creator-skills — ★★★★★
- **定位**：推广素材创作技能**包**（promo-brief / promo-asset-producer / promo-editor / promo-music-maker 四技能组合）。
- **技术栈**：多技能组合包（brief → 素材产出 → 剪辑 → 配乐 流水线）。
- **亮点**：**技能组合成工作流**（上游产出下游消费）的清晰案例——比单技能更有价值。
- **对主项目价值**：直接借鉴——主项目 DAG 编排端到端映射：brief=输入意图节点，producer=生图节点，editor/music=后处理节点。
- **借鉴点**：把 ecommerce/ppt 等多技能编排成「组合技能工作流」（对齐 DAG 节点）；推广素材场景可作为生图扩展方向输入。
- **评分**：5

## 10. marketing-skills — ★★★★
- **定位**：开源 Marketing Skills OS（营销技能操作系统，含 VALIDATION.md）。
- **技术栈**：SKILL.md 集合 + 验证规范。
- **亮点**：①营销技能系统化（不只单一技能）；②**VALIDATION.md**（技能验证规范——营销领域的可验证口径）。
- **对主项目价值**：局部借鉴——营销/推广类技能库（配合电商扩展）；VALIDATION 规范可并入 `scripts/validate_skills.py`。
- **评分**：4

## 11. claude-deep-research-skill-main — ★★★★
- **定位**：企业级深度研究技能（citation-backed、source credibility scoring、多搜索源、schemas/tests/reference/templates 完备）。
- **技术栈**：SKILL.md + schemas/ + tests/ + scripts + templates。
- **亮点**：①**自带 tests/** 与 **schemas/**（技能级 JSON Schema 契约 + 测试）——可验证技能标杆；②供应链评分（source credibility）。
- **对主项目价值**：局部借鉴——research 类技能模板 + 技能自带 schema/tests 范式（与 100x-skill-tiktok 四件套同思路）。
- **评分**：4

## 12. browser-act__skills — ★★★★
- **定位**：BrowserAct 浏览器操作技能 + skill-forge（技能锻造工具），docs + solutions + requirements.txt。
- **技术栈**：Python + 浏览器操作技能族 + forge 生成工具。
- **亮点**：**skill-forge**（用工具批量生成/锻造技能的自动化）——技能生产的流水线。
- **对主项目价值**：局部借鉴——「技能锻造器」思想（与 SkillClaw 沉淀、book-to-skill 蒸馏同方向）。
- **评分**：4

## 13. claude-code-skill / chrome-cdp-skill — ★★★
- **定位**：让 agent 直接看/操作用户**已登录的活 Chrome 会话**（不另起浏览器、不重新登录）。
- **技术栈**：CDP 客户端 + skills/。
- **亮点**：活会话接管（已有 session 复用）——比新开 Playwright 上下文更贴近真实用户环境。
- **对主项目价值**：局部借鉴——主项目浏览器自动化/号池真人会话（如上游签到）可考虑 CDP 活会话方案。
- **评分**：3

## 14. gitskills-sample — ★★★
- **定位**：Agent Skill 格式样本（SKILL.md 结构 + MSR 2027 挖掘挑战用 plots/agent_skills_sample.zip）。
- **技术栈**：SKILL.md 样例。
- **亮点**：SKILL.md 最小有效格式的教科书样例（学术标注）。
- **对主项目价值**：低-中——技能格式基准参考。
- **评分**：2

## 15. codex-skills-main — ★★★
- **定位**：Codex/agent skills（planning / 文档访问 / 前端开发 / 浏览器自动化），agents/ + bin/ + hooks/ + package.json。
- **技术栈**：Codex 侧技能 + hooks + bin 脚本。
- **亮点**：面向 planning/前端/浏览器的技能切片；hooks 挂点。
- **对主项目价值**：局部——planning 类技能与前端生成技能模板。
- **评分**：3

## 16. andrej-karpathy-skills-main — ★★★
- **定位**：Karpathy 观察衍生的一页 CLAUDE.md 行为指南（EXAMPLES + skills/）。
- **技术栈**：CLAUDE.md 指南。
- **亮点**：把 LLM 编码坑（过度自信/冗长/越权）转成行为约束清单——「反模式 → 约束」方法。
- **对主项目价值**：局部——主项目提示词/技能里的「诚实性硬规则」（如 qtyasupo 负向三段）可参考其问题清单结构。
- **评分**：3

## 17. js-reverse-skill — ★★★
- **定位**：网页 JS 请求参数逆向与纯协议还原技能（签名/Cookie/设备指纹/混淆/WASM/JSVMP 覆盖）。
- **技术栈**：SKILL.md + cases/ + references/（案例库）。
- **亮点**：**cases/（案例库）** 驱动 —— 每类难题有可复现案例；references/ 参考资料。
- **对主项目价值**：局部——「案例库驱动技能」模式（主项目技能可加 cases/ 目录，教学化）；与逆向工程相关但非主项目核心。
- **评分**：3

## 18. android-reverse-engineering-skill / ghidra-re-skill-main / 19. cangjie-skill / 20. darwin-skill-master — ★★
- **定位**：逆向/二进制/特定语言技能（安卓逆向、Ghidra RE、仓颉语言、darwin 视觉）。
- **亮点**：ghidra-re 的双编码工具（Codex+Claude 同技能）与 bridge 形态可参考；其余为主项目非核心域。
- **对主项目价值**：低——仅技能工程形态参考（多语言 README、bridge 架构）。
- **评分**：2

## 21. ffmpeg-skill — ★★★
- **定位**：FFmpeg 媒体处理技能（CHANGELOG/CRITICAL_ISSUES/assets/bin 完整工程化）。
- **技术栈**：SKILL.md + bin + assets。
- **亮点**：**CRITICAL_ISSUES.md**（已知坑显式记录——防止 agent 重蹈覆辙）+ CHANGELOG 工程；媒体处理技能模板。
- **对主项目价值**：直接相关——主项目扩展视频/音频处理（视频扩展方向），ffmpeg 技能可直接复用「已知坑清单」模式。
- **评分**：3

## 22. last30days-skill — ★★★
- **定位**：last30days 技能（多语言 README×8 + CONCEPTS/CONFIGURATION/HERMES_SETUP/CHANGELOG 极完整文档化）。
- **技术栈**：SKILL.md + 超全配置文档。
- **亮点**：**文档完备度天花板**（CONCEPT/CONFIGURATION/HERMES_SETUP 分章）——技能可配置化样例。
- **对主项目价值**：局部——技能「可配置参数 + 安装文档」工程范式。
- **评分**：3

## 23. jakubkrehel__skills / 24. magiccreator-ai__gpt-image-2-5-prompt-skill / 25. awesome-design-skills / 26. awesome-ux-skills / 27. application-skills / 28. cangjie 等 — ★★★
- **定位**：技能集合类（interfaces.dev、GPT-image-2.5 prompt 技能、Design skills、UX skills、Membrane 应用技能）。
- **亮点**：①design/UX 技能集（awesome-ux 有 accessibility/ai-governors/ai-inputs/ai-trust-builders 等**分类体系**）→ 主项目技能分类可参考；②GPT-image-2.5 prompt 技能 → 主项目生图 prompt 资产增强（与 v8 视频组 image prompt 集合呼应）。
- **对主项目价值**：中——UX/Design 技能分类体系（前端教学化）+ 生图 prompt 技能（对主项目 Generate 页可呈现）。
- **评分**：3

---

## 本组汇总：Top6 最值得主项目借鉴项（技能沉淀/工程化方向）

1. **anthropics__skills（官方 Agent Skills 规范）** — 用 agentskills.io 标准校准主项目 `api/skills/loader.py` frontmatter/渐进式披露；新增官方 template 式技能骨架生成器。**（基础校准，P1）**
2. **benjamin-plus-skill** — 技能包加 `expected_results`（预期结果可验收）+ 分发哈希校验 + hooks/injected-instruction（运行时注入）。对准「真实闭环」。**（技能可验证化，P1）**
3. **dashi-ppt-skill + feichanggege__ecommerce-visual-copywriting-skill** — PPT 扩展（可编辑 PPTX + 网页预览 + 模板）与电商扩展（视觉文案子技能 + 双语）两大场景技能直接补强主项目现有 ecommerce/ppt skills。**（扩展场景，P1）**
4. **kangarooking__promo-creator-skills** — 「技能组合成工作流」（brief→producer→editor→music）与主项目 DAG 编排端到端映射。**（组合技能/工作流，P2）**
5. **book-to-skill + browser-act skill-forge** — 「文档→技能蒸馏」与「技能锻造器」两类技能生产自动化 → 用户沉淀 skills 闭环的供给侧。**（技能生产管线，P2）**
6. **ffmpeg-skill 的 CRITICAL_ISSUES.md 与 claude-deep-research 的 schemas/tests** — 技能自带「已知坑清单」+「schema/测试」双重可验证化，并入统一 `scripts/validate_skills.py` 门禁。**（技能工程规范，P2）**

> 注：本组为「技能生态与工程化」密度最高的一组，与 g04（SkillClaw/SkillOpt/100x-tiktok/SkillSpector）合并构成主项目「沉淀训练用户自己的 skills + 开放技能市场」方向的完整参照池。