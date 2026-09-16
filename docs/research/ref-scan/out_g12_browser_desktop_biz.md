# g12_browser_desktop_biz 组扫描报告

> 扫描范围：16 个目录（浏览器自动化 6 + 桌面端 6 + 电商/PPT 4）
> 主项目视角：①电商场景扩展 ②桌面应用交互(Tauri2 sidecar 托盘/快捷键/通知/自启) ③浏览器自动化质量保障 ④PPT/办公文档生成
> 说明：`browser-use`/`browser-use__browser-use`、`UI-TARS-desktop`/`bytedance__UI-TARS-desktop` 为同一源码仓库的复制（diff 仅 .git 差异），合并分析。

---

## 1. abundantbeing__hermes-browser-extension

- 定位：Hermes Agent 的 Chrome MV3 侧栏扩展，把活动浏览器上下文接入本地/云端 Hermes 运行时；含 Hermes Assist（站点感知的拟稿面板）与 30+ 站点写作环境适配。
- 技术栈：Manifest V3（sidePanel + debugger + scripting）/ 原生 JS ES Module / 内部 pytools（Python 契约校验脚本）/ 多语言 _locales
- 亮点：
  1. **浏览器上下文安全分级体系**（`extension/lib/browser-control-safety.mjs`）：动作分三档 `SAFE_ACTIONS`（浏览/点击/输入免审批）/ `APPROVAL`（提交/支付/删除等要确认）/ `BROWSER_CONTROL_PRIVILEGED_ACTIONS`（console/evaluate/CDP/上传/PDF 永远需显式批准）；用正则分类目标（`SUBMISSION_KEY_RE`/`PAYMENT_RE`/`CREDENTIAL_RE`/`MFA_RE`/`SECRET_TEXT_RE`），对 `api_key:`、`sk-*`、JWT`eyJ...` 做脱敏判定——这是「危险动作分级 + 敏感信息脱敏」的教科书实现。
  2. **Truthful Page-Only 作用域控制**（v0.3.2）：默认只把活动 tab 计入 prompt（`1/N tabs`），其余 tab 严格排除防 token 膨胀；多关键字 tab 搜索、AI Tab Triage（`/sort-tabs` 按主题聚类、重复域名检测、推荐关闭清单）。
  3. **内容提取核心**（`extension/lib/content-extraction-core.mjs`）：`EXTRACTION_SCHEMA` 版本化协议、显式常量上限（文本 12K/envelope 24K/context 32K）、`NOISE_SELECTORS` 噪声节点白名单（script/style/nav/footer/ad/cookie/consent/newsletter…）、JSON-LD 提取上限、`[truncated]` 标记。
  4. **Hermes Assist 保守写入原则**：结构化编辑框默认只「预览/复制」，绝不自动点 Send/Submit/Navigate/Purchase——AI 生成内容落地的安全边界。
- 对主项目价值：直接借鉴（浏览器上下文采集 + 危险动作拦截均可落到主项目 browser skill / Playwright 验证层）
- 借鉴点：①危险动作三级分类（SAFE/APPROVAL/BLOCKED）+ 敏感文本正则脱敏，套到电商自动发布（进入支付/删除/提交页必须人工确认）；②NOISE_SELECTORS 噪声白名单 + 显式容量上限，作为主项目网页抓取/正文提取的默认清洗规则；③数据流协议版本化文档（`DATA-FLOW.md`：Local/Cloud/Remote 三连接模式 + 每种模式能发什么、不能发什么）
- 评分：5

---

## 2. browser-harness-js

- 定位：「最薄的 LLM→Chrome 桥」——不做任何 helper 封装，把 CDP 全部 56 域 652 方法生成为类型化 TS 调用，一个持久 WebSocket 会话。
- 技术栈：Bun / TypeScript / `browser_protocol.json` + `js_protocol.json` 代码生成（`sdk/gen.ts`→`sdk/generated.ts`）/ SKILL.md（作为 skill 分发）
- 亮点：
  1. **代码生成对抗协议漂移**：SDK 从 Chrome 官方 protocol JSON 重新生成，新方法换 JSON 即出现；类型即文档（每个 CDP 方法带完整 JSDoc）。
  2. **反「helper 是谎言」哲学**：`click(x,y)` 掩盖了 `Input.dispatchMouseEvent` 的 14 个参数，Agent 能力被静默阉割——只补 CDP 缺失的原语（`listPageTargets`/`resolveWsUrl` 读 `DevToolsActivePort`/`session.use(targetId)` 路由/`waitFor(method,pred,timeout)`）。
  3. **interaction-skills 配方库**：dropdown 框架/shadow-DOM 陷阱/网络等待模式等非显然 CDP 配方，一条一个文件，纯 CDP 实现，鼓励社区贡献。
- 对主项目价值：局部借鉴（深链浏览器自动化时的 CDP 原语哲学）
- 借鉴点：主项目 browser skill 若直接驱动真实浏览器，可借鉴「用官方 protocol 生成封装、helper 保持最小、配方以 CDP 原语沉淀」的思路——避免为每个站点写脆弱 helper。
- 评分：4

---

## 3. browser-use（与 browser-use__browser-use 同源，合并）

- 定位：最成熟的开放 AI 浏览器 Agent 库——Agent + CDP 直连 Chrome，DOM 快照级可交互元素识别，多 LLM 提供商，带 Judge 评估与云服务。
- 技术栈：Python / pydantic / CDP 直连 / Playwright 可选 / telemetry + OpenTelemetry / skills 生态（cloud/open-source/qa/remote-browser/x402）
- 亮点：
  1. **EnhancedSnapshot 只取必需 computed styles**（`dom/enhanced_snapshot.py`）：为防重站点崩溃，仅抓 `display/visibility/opacity/overflow/cursor/pointer-events/position/background-color` 10 个样式；**敏感输入脱敏**（`password/file/hidden` + `autocomplete=cc-*/one-time-code` 的实时值绝不序列化给 LLM/日志）——浏览器快照质量与安全的双重样板。
  2. **ClickableElementDetector**（`dom/serializer/clickable_elements.py`）：JS click 监听检测（CDP 无 DOM 变更识别 React/Vue/Angular onClick）、label `for` 代理规避防双触发、iframe >100px 门槛、size-0 可交互覆盖层提示。
  3. **Registry 工具注册架构**（`tools/registry/service.py`）：ActionRegistry + exclude_action 动态排除、SpecialActionParameters 标准化参数注入、内置 pyotp（OTP 支持）。
  4. **Judge 评估系统**（`agent/judge.py`）：对执行轨迹（截图+文本）打分校验任务完成度，截图 base64 + 文本截断——主项目 critic 自反思的同构参考。
  5. **Sandbox 沙箱执行**（`sandbox/sandbox.py`）：agent 代码/脚本在受限环境执行，SSE 事件流返回结果。
- 对主项目价值：直接借鉴（浏览器自动化的质量保障主参照）
- 借鉴点：①快照「最小样式集 + 敏感字段脱敏」原则，直接用于主项目 browser skill 抓取；②工具注册 + 排除机制（对齐主项目 MCP/skills 工具注册表）；③Judge 对浏览器任务轨迹打分，可与主项目 critic skill 合并演进。
- 评分：5

---

## 4. browsercode

- 定位：browser-use 团队出的浏览器原生编码 Agent——TUI（`bcode`）+ headless 运行，驱动真实浏览器做「写脚本复用」式任务（如航班/比价抓取）。
- 技术栈：Bun / Nix（flake）/ TUI / Browser Use Cloud API / opencode provider 兼容 / install-bytecode
- 亮点：
  1. **「适配运行时 site、留脚本复用」理念**：Agent 每站动态适配，成功后沉淀复用脚本（`artifacts/`）——把一次性抓取升级为可复用资产，正好对应电商采集的主图/竞品监控场景。
  2. **任意 LLM provider 接入**（`/connect` + opencode providers），含 BU Bench 模型榜单驱动选型。
- 对主项目价值：扩展方向参考
- 借鉴点：主项目 ecommerce skill 可把「站点适配→脚本沉淀→复用」做成产物闭环（抓取的页面结构模板化持久化）。
- 评分：3

---

## 5. camofox-browser

- 定位：基于 Camoufox（Firefox C++ 指纹伪造分支）的反检测浏览器 REST 服务，专为 AI Agent 设计——可访问性快照代替 HTML、稳定元素 ref、搜索宏、会话隔离。
- 技术栈：Node.js / Express `/ Fastify 类插件 / Playwright / Camoufox(Firefox fork) / 可选 yt-dlp / Docker / OpenAPI 自动生成
- 亮点：
  1. **Token 高效快照 + 分页窗口**（`lib/snapshot.js`）：accessibility 快照比 HTML 小 ~90%；`windowSnapshot()` 大页人脸截 80K 字符 + **尾部 5K 永久保底分页/导航链接**（offset 分页继续读），`[truncated at char N…]` 标记——大网页抓取的窗口化范式，与主项目大模型上下文控制直接相关。
  2. **JSON Schema 结构化提取**（`lib/extract.js`）：`POST /tabs/:id/extract` 传 JSON Schema，属性经 `x-ref` 映射到快照元素，`SUPPORTED_TYPES` 白名单校验 + `coerceValue`（从噪声文本提取 number/integer/boolean）——电商页面商品字段（价格/评分/标题）结构化抽取的现成配方。
  3. **稳定元素 ref（e1/e2/e3）+ 搜索宏**（`lib/macros.js`）：`@amazon_search`/`@google_search`/`@reddit_subreddit` 等 14 个宏直接跳转搜索页——电商采集（亚马逊/淘宝主图批量提取）的入口捷径。
  4. **认证中间件分层**（`lib/auth.js`）：`CAMOFOX_API_KEY` 主键 + `CAMOFOX_ACCESS_KEY` 超管键 + 生产外允许回环 + timing-safe 比较——与主项目 `IF_API_KEYS` 鉴权同构且更细。
  5. **会话隔离/cookie 导入/VNC 可视化登录导出 storage state**——号池/邮箱池之外的「浏览器会话资产」管理思路。
- 对主项目价值：直接借鉴（电商抓取 + 反检测 + 结构化提取三合一，最贴合主项目电商方向）
- 借鉴点：①快照分页窗口与结构化提取，直接落到 ecommerce skill 的商品页采集；②搜索宏 + 稳定 ref 机制，做主图批量抓取的默认导航层；③session trace 录制（后端 API 提供 trace zip）做质检测绘。
- 评分：5

---

## 6. nanobrowser__nanobrowser

- 定位：浏览器内运行的开源 OpenAI Operator 替代——Chrome 扩展 + 多 Agent（Planner/Navigator 协作）完成网页工作流。
- 技术栈：Chrome MV3 扩展 / LangChain / Zod / pnpm monorepo / 多 LLM（含自定义 OpenAI-compatible 端点）
- 亮点：
  1. **Planner 结构化输出契约**（`agent/agents/planner.ts`）：Zod schema 严格约束（observation/challenges/done/next_steps/final_answer/web_task），`done`/`web_task` 支持字符串→布尔容错转换——Agent 间协议即 schema，主项目 DAG 编排节点间通信的可复制模式。
  2. **错误分类体系**（`agent/agents/errors.ts`）：ChatModelAuthError/ChatModelForbiddenError/BadRequest/Aborted/RequestCancelled 细分，并按错误类型决定重试/降级——主项目 LLM 调用错误路由参考。
  3. **消息过滤**（`agent/messages/utils.ts` `filterExternalContent`）+ guardrails 服务目录（`services/guardrails/`）——外部内容进上下文前过滤。
  4. strip/`event/` 事件流：多 Agent 动作以事件流对外观测（step_start 等）。
- 对主项目价值：直接借鉴（agent 协议 + 错误分类，对齐主项目意图识别/DAG 编排）
- 借鉴点：①Planner/Navigator 的 Zod 输出契约 + 事件流，强化主项目 agent 链节点间协议；②LLM 错误分类→重试/降级策略并入主项目重试策略模块。
- 评分：4

---

## 7. Aether-desktop-orchestrator

- 定位：疑似 AI 生成的桌面助手「幽灵仓库」——191 行营销式 README + 一个含混淆 JS 的空 index.html，**无任何实质源码**。
- 技术栈：无（README 声称 Windows/macOS/Linux，无代码）
- 亮点：README 描述的概念（系统级上下文感知、多 agent 编排、技能插件生态）无实现，不可验证。README 架构图（Context Engine / Episodic Memory Store / Plugin Manager）作为概念清单可参考，但零产品价值。
- 对主项目价值：无价值（警惕此类 AI 注水仓库）
- 借鉴点：无。仅警示：仓库扫描需先验「有真实源码还是 README 吹水」。
- 评分：0

---

## 8. Hermes-CN-Desktop

- 定位：Hermes Agent 中文社区出品的桌面客户端（Tauri v2 + Rust + React），原生 Windows/macOS，内置 Hermes-CN 内核。
- 技术栈：Tauri v2 / Rust / React / TS / GitHub Actions（web-test/rust-test/release-desktop 三条 CI）/ PolyForm NC 协议
- 亮点：
  1. **Tauri v2 跨平台桌面 + 完整发布流水线**：workflows 区分 `web-test`（前端单测）`rust-test`（Rust 单测）`release-desktop`（多平台打包发布），带安全审查（当前码表 90857）——主项目 Tauri2 sidecar 的发布/CI 蓝本。
  2. **桌面工作台能力密度**：工作台/归档/对话（LaTeX/Markdown 渲染）/任务控制台/Skills/Memory/模型服务商配置/用量统计/系统健康/运行时诊断，功能覆盖与主项目管理面板 15 页高度对应。
  3. **飞书平台接入**（生态集成点）。
- 对主项目价值：扩展方向参考（主项目若做 Tauri2 桌面壳，此为同技术栈但更完整的参考）
- 借鉴点：①Tauri2 + React 的桌面集成结构（前端复用现有 React 面板）；②release-desktop 多平台发布流水线（含签名资产管理）。
- 评分：3

---

## 9. UI-TARS-desktop（与 bytedance__UI-TARS-desktop 同源，合并）

- 定位：字节开源的 GUI Agent 桌面应用（Electron），基于 UI-TARS 多模态模型，本地/远程控制电脑与浏览器。
- 技术栈：Electron + electron-builder/forge / pnpm monorepo（packages: agent-infra + ui-tars sdk + operators）/ nut-js（桌面控制）/ Vitest + Playwright（e2e）
- 亮点：
  1. **动作空间显式契约**（`apps/ui-tars/src/main/agent/operator.ts` `ACTION_SPACES`）：click(left/right/double)/drag/hotkey/type(转义 `\n` 提交)/scroll/wait(5s 截图)/finished()/call_user()——GUI Agent 的可枚举动作原语，主项目桌面自动化（托盘/快捷键/通知之外的「操作桌面」）可直接采用。
  2. **多 operator 抽象**（`packages/ui-tars/operators/`）：adb（移动端）/browser-operator/localbrowser/remote browser/browserbase/nut-js 统一 `Operator` 接口——「同一种操作语义、多执行后端」的抽象，主项目号池+浏览器自动化可选同构。
  3. **browser-operator 快捷键映射**（`operators/browser-operator/src/shortcuts.ts`）：`Meta+KeyA→SelectAll` 等通过 CDP `Input.dispatchKeyEvent` + editor command 映射，主项目全局快捷键（计划中）可参考其 key-map 封装。
  4. **截图链路**：desktopCapturer + physical/logical/scaleFactor 换算，主窗口截屏做多模态输入。
- 对主项目价值：局部借鉴（GUI/桌面操作的 action 原语 + 多 operator 抽象）
- 借鉴点：主项目桌面 sidecar 若扩展「操作真实应用」，直接搬 ACTION_SPACES 契约与 nut-js operator；浏览器 operator 的快捷键映射纳入全局快捷键计划。
- 评分：4

---

## 10. deepseek-harness-desktop

- 定位：DeepSeek Harness Desktop 的发行版仓库——上游 DSH 源码 + 大量 `_*.patch`（安全/修复/测试结构/redaction BOM）+ 应用打包（apps/）的社区维护 Windows 驱动。
- 技术栈：上游（临时）Node/Web + **patch-based 继承模型** + Electron 打包 / PRIVACY 文档 / capture 脚本
- 亮点：
  1. **patch 级上游管理**：`_release-security.patch`/`_release-redaction-bom.mjs`/`_fix-extension-test-structure.patch` 等，发行版对上游以补丁文件显式记录所有改动（含评审与修复追踪），比 fork 分支更可审计——主项目多仓库/上游依赖的维护范式参考。
  2. **发布安全与脱敏**：redaction 脚本 + BOM 处理，说明其重视发布产物清洗（密钥/占位符）；bug-report 文档化 + patch 对应。
- 对主项目价值：无价值（作为独立产品与主项目不同域；patch 管理思路可微借鉴）
- 借鉴点：patch 化对上游维护（可审计、可回滚）理念，主项目若 vendoring 上游可考虑。
- 评分：2

---

## 11. dsh-desktop

- 定位：deepseek-harness-desktop 的正式社区发行版（同族但更完整）——Windows Electron AI 编程桌面客户端，含插件体系/扩展坞/记忆/自更新/托盘/安全模式。
- 技术栈：Electron / Cordis 插件框架（@deepseek-ai/cordis + schemastery 配置）/ TS / pnpm / asar
- 亮点：
  1. **桌面自更新全生命周期**（`dsh-plugin-desktop/src/updates.ts` + `update-checker.ts` + `update-download.ts` + `update-lifecycle.ts`）：后台轮询策略（初始延迟/间隔/超时全部可配）、版本检查端点 + **release channel 分流（stable/beta）**、严格 SemVer 解析（数值用字符串防溢出、prerelease 排序）、累加安装/回滚；还挂 `registerTrayItem` 动态托盘命令（Check for Updates/Downloading vX…）。**主项目已有 IF_DESKTOP_UPDATER 自升级，这是最完整的对照实现**。
  2. **托盘体系**（`tray-icons.ts`/`tray-locale.ts`）：完整托盘菜单（New Profile/Check Updates/Enter Safe Mode/Export Diagnostics/Quit/Switch Language），桌面交互事件完备。
  3. **启动恢复与安全模式**（`startup-recovery-controller.ts`/`startup-recovery-window.ts`/`safe-mode.ts`）：profile checkpoint 槽位、恢复窗口授权、safe mode 启动诊断、`windows-acl-runner.ts` 限权执行、`mask-secrets.ts` 脱敏——桌面端崩溃恢复与安全执行样板。
  4. **诊断导出**（`diagnostic-export.ts`）：一键打包日志/配置诊断，用户侧排障。
- 对主项目价值：直接借鉴（主项目 Tauri2 sidecar 的托盘/自更新/恢复/诊断全对照）
- 借鉴点：①更新机制补强：channel(stable/beta) 分流 + 严格 SemVer + 可配轮询策略，升级主项目 IF_DESKTOP_UPDATER；②托盘菜单能力全集（含 update/safe-mode/diagnostics 状态）；③启动恢复 checkpoint + 安全模式，桌面 sidecar 的可靠性基线。
- 评分：5

---

## 12. vastsa__PI-Desktop（app 域内置 deepseek-harness 变体）

- 定位：PI-Desktop——又一个 AI 桌面聚合客户端（Rust+Tauri+Node 混合 monorepo），内置/联动的社区市场生态（profiles/market/fabric）。
- 技术栈：Rust (Cargo) + Tauri 前端 + pnpm monorepo + deepseek-harness 集成 + cordis 插件
- 亮点：
  1. **社区市场/插件分发生态**（profiles/reference marketplace）：插件+profile 商店化的分发模型，主项目 skills 生态可参考「安装/版本/供应链」。
  2. **跨端架构**：多语言混编（Rust 核心 + TS 前端 + 上游 harness 进程）的承载方式。
- 对主项目价值：扩展方向参考
- 借鉴点：插件市场供应链模型（若主项目做 skills 商店）；其余与 dsh-desktop 重叠。
- 评分：2

---

## 13. subhacademic-cmd__prompt-craft-ecommerce-visuals

- 定位：电商视觉生成的概念级「Atelier」——README 315 行给你一个产品级系统设计（品牌画像/平台规格/季节上下文/批量管线），**无实际代码**（index.html 为空）。
- 技术栈：无（概念设计；README 声称 Node/Python + DALL·E3/Stable Diffusion/Midjourney）
- 亮点：
  1. **品牌画像 YAML 契约**（概念）：`brand-profile.yaml` 结构化定义 visual_identity（palette/typography_mood/composition_style）、target_demographic、product_categories（visual_contexts/key_features/emotional_triggers）、seasonal_modifiers、platform_specifications（instagram/amazon/shopify 每种 aspect_ratios/style_intensity/background 规则）——电商商品图生成的「上下文上下文最全的结构化输入模板」。
  2. **平台规格差异化**：同一商品按站（Amazon 白底/高细节、Instagram 1:1/4:5/9:16 高冲击、Shopify 3:4 生活方式）生成——主项目 ecommerce skill 最缺的「多平台输出差异化」概念。
  3. **转化反馈环**（mermaid 图）：生成→部署→转化分析→回喂 prompt 工程的闭环设计。
- 对主项目价值：局部借鉴（纯设计文档，但品牌画像/平台规格结构直接可用）
- 借鉴点：把 brand-profile.yaml 的字段模型当作主项目 ecommerce skill 的商品图 prompt 输入 schema；平台规格表（比例/背景/风格强度）做成可配置多平台输出策略。
- 评分：2（无代码扣分；文档对电商场景有价值）

---

## 14. ppt-master

- 定位：AI 生成「原生可编辑 PowerPoint」的项目（skill 化的 PPT 生成器）——不是填模板，而是推理论证结构后生成原生 OOXML/编辑型 shape。
- 技术栈：Python（OOXML 处理）/ SVG 中间层（svg→pptx 转换）/ skill 化文档体系（references/executor/templates/brands）
- 亮点：
  1. **「先论证后设计」产品哲学**：`references/modes/_index.md` 定义 5 种叙述骨架（pyramid 结论先行/narrative 故事弧/instructional 概念拆解/showcase 视觉冲击/briefing 简报），mode=怎么论证 与 visual-style=长什么样 独立解耦（任何 mode×任何 style）——这是 PPT 生成内容质量的核心分层，主项目 ppt 场景可直接吸收。
  2. **OOXML 原生可编辑性**（`scripts/pptx_ooxml/`）：`ooxml.py`/`clone.py`/`edit_safety.py`（图表/表格编辑前分类校验，classic vs chartex 命名空间识别）、`pptx_shapes/semantic_hash.py`（shape 语义指纹做去重/预览一致）、`xml_safety.py`——生成的 PPTX 进 PowerPoint 后形状全可编辑，而非平铺文本框。
  3. **executor 懒加载知识架构**（`references/executor-base.md`）：页面遇到什么能力才读取对应模块文档（structured→图表→表格→形状→特效→图片→公式→超链接→演讲者备注），条件分支一次扫描、批量加载——大型 skill 库「按需路由加载」的工程范式，主项目 skills 库（ecommerce/ppt/image_quality…）可复用该 loading 策略。
  4. **品牌/模板/图表模板体系**（`templates/brands/` `templates/charts/` `templates/decks/`）+ 图标库 + 视觉风格目录——模板化复用资产库。
  5. **工作流分层**：Quick（快速单次）vs Default（规范多门禁）两套 profile，重流程与轻流程并存。
- 对主项目价值：直接借鉴（④PPT/办公文档生成的标杆）
- 借鉴点：①5 模式论证骨架 → 主项目 ppt skill 的「大纲→设计」分层；②OOXML 原生生成 + edit_safety 安全编辑，若主项目做 PPTX 服务端生成；③executor 按需路由加载的文档架构，重构主项目 skill 仓库；④品牌模板资产库结构。
- 评分：5

---

# 本组汇总：Top3 最值得主项目借鉴项

1. **camofox-browser 的「反检测浏览 + 分页快照窗口 + JSON Schema 结构化提取」**（评分 5）
   直接命中主项目两方向：电商采集（搜索宏 `@amazon_search` + 稳定元素 ref + x-ref 商品字段抽取）与浏览器自动化质量保障（accessibility 快照比 HTML 小 90%、大页 offset 分页保底导航尾部、session trace 录制）。三合一落地为 ecommerce/browser skill 的基础设施。

2. **dsh-desktop 的桌面自更新 + 托盘 + 启动恢复全生命周期**（评分 5）
   主项目 Tauri2 sidecar（托盘/通知/自升级/全局快捷键计划中）的最完整对照：release channel(stable/beta) 分流 + 严格 SemVer + 可配后台轮询策略 + 托盘动态命令（Check/Downloading vX…）+ profile checkpoint 启动恢复 + safe mode 诊断导出。主项目已有 `IF_DESKTOP_UPDATER`，可按此补强多通道与回滚。

3. **browser-use / hermes-browser-extension 的浏览器安全与快照质量原则**（评分 5/5）
   「最小 computed styles 集 + 敏感字段脱敏（password/autocomplete/API key/JWT）+ 危险动作三级拦截（SAFE/APPROVAL/BLOCKED）+ 噪声白名单 + 容量上限」——浏览器自动化抓取质量与安全的两大成套做法，与 camofox 结合即主项目浏览器自动化的完整质量底座；其 Judge 执行轨迹评分与主项目 critic 自反思同构。

> 附加：ppt-master 的「5 模式论证骨架 + OOXML 原生可编辑 + executor 按需加载」是④PPT 方向的最佳参照（评分 5）；nanobrowser 的 Zod 输出契约 + LLM 错误分类 可直接强化主项目 agent/DAG 编排；subhacademic 的品牌画像 YAML/平台规格表 可作为 ecommerce skill 的输入 schema 草案。Aether-desktop-orchestrator 为无源码 AI 注水仓库（评分 0），已剔除。

---

*扫描纪律：全程只读分析，未修改任何文件、未运行副作用命令、未安装依赖、未联网。*