# g10_gateway_mcp 组扫描报告（28 目录）

> 扫描方式：只读分析。ls 看结构 → README 定位 → 核心模块证据提取。
> 重点方向：①MCP 生态接入（Streamable HTTP 升级）②网关/聚合层设计（多上游统一协议、配额、限流、计费）③工程/安全/性能借鉴。
> 评分 0-5（对主项目「听风AI」的借鉴价值）。

---

## 9router
- 定位：免费 AI 路由器 + Token 节省器，把 Claude Code/Codex/Cursor 等 CLI 工具统一接到 40+ 提供商 100+ 模型，三梯队（订阅→廉价→免费）自动回退。
- 技术栈：Node/Next.js（自托管 dashboard + /v1 OpenAI 兼容端点），src/mitm 内含 MITM 代理、自签 CA（winElevated.js）、HTTPS 拦截。
- 亮点：
  1. **RTK Token Saver**（README 536-548）：对 tool_result 内容（git diff/grep/ls 输出）做无损压缩再发给 LLM，节省 20-40% 输入 token；"peek 首 1KB 自动检测 + 失败/变大则静默保留原文"的安全回退设计（README 541-542）。
  2. **订阅配额最大化**：追踪各订阅剩余配额，重置前用尽；多账户 round-robin 轮询（README 38-45）。
  3. **透明代理 + 格式翻译**：OpenAI↔Claude 格式互转，上游无感（README 57-58）。
- 对主项目价值：局部借鉴（RTK 压缩思路与主项目 SSE 生图结果压缩、工具输出处理同源；配额追踪与主项目预算门禁可互补）。
- 借鉴点：tool 输出无损压缩管线（安全降级设计）、订阅配额追踪/回退梯队、多账户轮询（主项目已有号池）。
- 评分：4

## 9router-Max
- 定位：9router 的中文化增强分支（"OpenClaw 的免费 AI 提供商"），主打免费提供商接入。
- 技术栈：同 9router（Node/Next.js）。
- 亮点：功能与 9router 一致（中文 README，README 第 1-30 行）；含 AGENTS.md/opencode.json/workflow_status.md，工程化完整。
- 对主项目价值：扩展方向参考（与 9router 同源，无需重复深读）。
- 借鉴点：中文文档体系（workflow_status.md 与主项目同型）。
- 评分：3

## NewAPI-Gateway
- 定位：多 NewAPI 供应商透明聚合网关，单一 `ag-xxx` token 调所有上游，自动同步价格/余额/路由表。
- 技术栈：Go + React web 面板，SQLite/MySQL/PostgreSQL。
- 亮点：
  1. **透明代理**：Header 清洗、body 零改动、UA 透传，上游感知不到网关存在（README 核心特性）。
  2. **智能路由**：候选归一匹配 + Priority 分层 + 价值评分加权 + 可选健康调节；每 5 分钟自动同步 pricing/tokens/balance 重建路由表（README 核心特性）。
  3. **SSE 流式代理**完整支持 + 每次调用的模型/供应商/耗时/状态统计（README 核心特性）。
- 对主项目价值：直接借鉴（主项目同样聚合 5 家图像上游；"候选归一匹配"与主项目 MAB-EWMA 路由可对照，"pricing/balance 自动同步重建路由表"正是主项目缺的渠道自愈）。
- 借鉴点：上游 pricing/balance 定时同步驱动路由表重建、Header 清洗的透明代理（主项目 cf_solver/代理池请求出口可用）、SSE 流式代理审计。
- 评分：4

## ProxyPoolWithUI
- 定位：简易免费代理池（带 Web 管理界面），定时爬取+验证+API 取用。
- 技术栈：Python 3.6+ / Flask（main.py:5000）+ 前端。
- 亮点：多源免费代理爬虫（14+ 源，README 表）、定时验证可用性、API 返回随机可用代理、内置 Web 界面（README 1-30）。
- 对主项目价值：局部借鉴（主项目已有 proxy_pool.py 住宅+免费双源轮换；此项目可作免费源扩充参考）。
- 借鉴点：免费代理源清单与验证调度思路（主项目 proxy_pool.py 可扩充源）。
- 评分：3

## The-NeXT-AI__ai-gateway
- 定位：TypeScript + Fastify 的 AI 协议网关，聚合 OpenAI/Anthropic/Gemini，含 **MCP Gateway** 与事件驱动 agent 工作流。
- 技术栈：TypeScript/Fastify；Redis 可选共享状态（多实例）。
- 亮点：
  1. **多协议统一**：OpenAI chat/responses/embeddings/images/videos + Anthropic messages + Gemini generateContent，跨协议转换 + provider fallback + provider 插件（README Features）。
  2. **可插拔共享状态**：idempotency/concurrency/circuit-breaker/scheduling/health-check 各自存储后端可 memory↔redis 切换，一行 env 升级多实例（README 36-50）。
  3. **MCP Gateway + MCP WebSocket RPC + 事件驱动 agent**；外部配置源支持 HTTP/WebSocket/gRPC/stdio（README Features）。
- 对主项目价值：直接借鉴（主项目 MCP 服务端升级 Streamable HTTP、事件驱动 agent 与主项目 DAG/意图识别架构高度契合；Redis 化共享状态切换模式可参考）。
- 借鉴点：跨协议转换层设计、共享状态存储可插拔（memory→redis）、MCP Gateway 与事件驱动 agent 架构。
- 评分：5

## Wei-Shaw__sub2api
- 定位：订阅配额分发型 AI API 网关平台，把 AI 订阅（OAuth/API Key 多账号）转成用户可用的 OpenAI 兼容 API，含计费/支付。
- 技术栈：Go/Gin/Ent + Vue3 + PostgreSQL + Redis。
- 亮点：
  1. **精确计费**：token 级用量追踪与成本计算 + 内置支付系统（EasyPay/支付宝/微信/Stripe 自助充值）（README Features）。
  2. **智能调度**：多账号粘性会话（sticky sessions）+ 每用户/每账号并发限制 + 请求/token 限流（README Features）。
  3. **Composite Groups**：admin 路由层把请求模型解析到具体 provider 的多供应商组（README Features + docs/COMPOSITE_GROUPS.md）。
  4. 注意 Nginx 转发下划线 header（session_id）会被丢弃的踩坑提示（README 200-210）。
- 对主项目价值：直接借鉴（主项目号池+预算门禁，正缺 token 级计费与多账号粘性路由；Composite Groups 与主项目模型组/路由组同型）。
- 借鉴点：token 级计费模型、多账号粘性会话路由、每账号并发限流、内置支付（主项目暂无计费，可作远期路线）。
- 评分：5

## auth2api-main
- 定位：轻量单账号 Claude OAuth→API 代理，服务 Claude Code 与 OpenAI 兼容客户端。
- 技术栈：Node.js 20+。
- 亮点：
  1. **轻量单账号设计**：刻意不做多供应商网关，代码小、易改易跑（README 1-30）。
  2. **双协议**：OpenAI 兼容 /v1/chat/completions 与 Claude 原生 /v1/messages passthrough，Bearer 与 x-api-key 双鉴权（README Features）。
  3. **安全默认**：timing-safe API key 校验、per-IP 限流、localhost-only CORS；上游限流后返回精确 429 而非笼统 503（README 单账号健康处理）。
- 对主项目价值：局部借鉴（主项目聊天端点鉴权已实现；"上游限流映射为精确 429/503 语义"与 OAuth 刷新/冷却策略可参考）。
- 借鉴点：上游 429→429 语义透传、timing-safe key 校验、OAuth token 刷新与冷却。
- 评分：3

## casbin-gateway
- 定位：Apache 出品的本机 AI 编码 agent 网关（桌面应用），一个端点代理所有 coding agent + 所有模型供应商，含 Casbin 权限。
- 技术栈：Go + React（桌面壳），agent/ 目录按 agent 分模块。
- 亮点：
  1. **agent 矩阵管理**：跨 agent 对比/复制 skills、MCP server、prompt、provider，一键从链接导入（ccswitch:// 协议，README 277-279），"写前先读"安全导入（README 279）。
  2. **工具开关粒度控制**：每个 MCP server/工具组独立开关，关掉的工具在请求离开本机前即被剔除，模型永远拿不到（README 289）。
  3. **Casbin 策略矩阵**：`p, claude-code, tool:mcp/github, use, allow` 首匹配规则，允许个别例外（README 301-306）。
  4. 权限规则：用户手写规则优先于开关生成的规则。
- 对主项目价值：直接借鉴（主项目管理面板 15 页可借鉴"按 agent/工具矩阵管理 MCP server 与技能、导入链路"；工具开关剔除进上下文是 agent 安全护栏的现成范式）。
- 借鉴点：MCP server/skills 跨 agent 复制与矩阵管理、ccswitch:// 链接导入、"关掉的工具不出本机"、Casbin 策略首匹配。
- 评分：4

## chatgpt2api
- 定位：ChatGPT 官网能力逆向封装为 OpenAI 兼容图片 API，含号池、多账号导入、Docker 自托管。
- 技术栈：Python（uv）/FastAPI + Web 面板。
- 亮点：
  1. **多存储后端可切换**：STORAGE_BACKEND=json/sqlite/postgres/git（README 100-120），一个开关换数据层。
  2. **稳定代理链**：WARP + Privoxy + FlareSolverr 组合应对 Cloudflare，默认只接管上游 OpenAI/ChatGPT 请求、账号自身代理优先（README 60-90）。
  3. 图片任务管理 + 号池 + 多种账号导入。
- 对主项目价值：局部借鉴（主项目已接 5 家图像上游+cf_solver；WARP/FlareSolverr 备用链路与"账号代理优先级"分层可参考）。
- 借鉴点：多存储后端抽象、WARP/FlareSolverr 稳定代理链、账号代理优先级分层。
- 评分：3

## chatgpt2api1
- 定位：chatgpt2api 的 v3 重写版（全新 Application Database，Vue3 前端，PostgreSQL 可选）。
- 技术栈：Python 3.13/FastAPI + Vue3 + SQLite/PostgreSQL。
- 亮点：
  1. **契约化分层**：api/ 下 call_contract.py/dashboard_contract.py/gallery_contract.py/image_task_contract.py/monitor_contract.py 等 contract 文件，与 services/ 严格分层（api/ 与 services/ 清单）。
  2. **服务完备**：oauth_login_service、proxy_service/proxy_management_service、sub2api_service、update_service（自升级）、bounded_task_runner（有界任务）。
  3. v3 起 3.0 不能直读 2.x 数据，强制升级路径（README 40-50）。
- 对主项目价值：扩展方向参考（契约文件分层与主项目 provider 分组抽象同思路；sub2api_service 说明它与 sub2api 生态打通）。
- 借鉴点：contract 文件作为跨层契约（主项目可作前后端/接口契约参考）、有界任务执行器 bounded_task_runner。
- 评分：3

## free-router
- 定位：本地 OpenAI 兼容网关，`free-best` 先给模型排序、再对每个模型遍历所有免费提供商，自动跳过限流/冷却/空响应。
- 技术栈：Node 20+ 单文件服务（server.mjs/providers.mjs）。
- 亮点：
  1. **模型级路由 + 多提供商同模型兜底**：同一模型可在多个免费提供商间逐个尝试，provider:model 可强制单家（README 路由行为 1-11）。
  2. **每周免费模型发现**：对 discovery catalog 新免费模型做一次性混合评估（确定性推理/指令检查+时延+上下文+工具支持）打分插入排名，付费/下架自动移除（README 每周发现节）。
  3. **安全**：key 永不入库、环境变量注入，转发前对 *_API_KEY/_TOKEN 做环境脱敏；reasoning-only 流缓冲到出内容才转发（README 9-11）。
- 对主项目价值：直接借鉴（主项目路由引擎 MAB-EWMA 打分 + 熔断，可借鉴"模型级多提供商兜底 + 冷却 + 新渠道自动发现评估"；reasoning-only 流缓冲与主项目 SSE 缓冲同理）。
- 借鉴点：模型归一 slug（剥 org 前缀/:free 后缀）、冷却/空响应处理、每周自动发现评估新渠道、环境变量 key 脱敏。
- 评分：5

## new-api
- 定位：One API 的增强复刻（国内最流行的 AI API 网关），渠道/令牌/计费/多协议转换全栈。
- 技术栈：Go + React/Electron，数据兼容原版 One API。
- 亮点：
  1. **格式转换矩阵**：OpenAI Compatible ⇄ Claude Messages、→ Gemini、思考转内容、Responses（READMe.zh_CN 高级功能节）。
  2. **渠道加权随机 + 失败自动重试 + 用户级模型限流**（README 智能路由节）。
  3. **授权登录**：Discord/LinuxDO/Telegram/OIDC 统一认证；Key 查询使用额度（README 授权与安全节）。
  4. 计费：缓存计费统计、组织内按次/按量成本核算（README 授权用量节）。
- 对主项目价值：直接借鉴（主项目 5 家图像上游 + 聊天；new-api 的渠道加权随机/失败重试/用户级限流、格式转换矩阵、OIDC 认证是主项目可对照的成熟范式）。
- 借鉴点：渠道加权随机路由、用户级模型限流、OIDC 多登录源、缓存计费统计。
- 评分：5

## nexus-llm-router
- 定位：**Python 3.11 + asyncio + httpx 的智能多 LLM 路由中间件**（与主项目同技术栈！），任务感知模型选择 + 成本优化 + 回退安全 + OpenAI 兼容 API。
- 技术栈：Python 3.11+/FastAPI/httpx/asyncio，ruff+mypy+pytest（1184 测试）。
- 亮点：
  1. **Observe→Decide→Act 生命周期**（ARCHITECTURE.md）：analyzer 提取复杂度分/领域标签/时延需求/token 预算 → 可插拔策略（RuleBased/Classifier/CostOptimal/LatencyAware/ABRouting）→ 适配器分发。与主项目 MAB-EWMA 同源但策略更丰富。
  2. **适配器归一契约**：BaseProviderAdapter 的 complete/stream/estimate_cost/health_check + ProviderResponse(content/model/input_tokens/output_tokens/cost_usd)；**多段 content 必须全量拼接**（Gemini functionCall、Anthropic thinking/tool_use 前置块）——README 架构注释详细记录了这个坑（ARCHITECTURE.md Response normalization contract）。主项目 provider 抽象可直接对照。
  3. **全套护栏**：ProviderFallbackScoreboard、TenantRateLimiter（token-bucket）、IdempotencyStore（幂等重放）、PromptInjectionGateway（注入拦截）、VirtualKeyStore（哈希虚拟 key+预算+模型白名单）、语义模糊缓存（trigram Jaccard）（README Features）。
- 对主项目价值：直接借鉴（**同 Python/FastAPI/httpx 技术栈**，主项目 MAB-EWMA 路由与 dispatch.py 可对照其策略引擎；幂等重放、注入网关、虚拟 key 预算是主项目安全路线现成参照）。
- 借鉴点：可插拔路由策略框架、适配器 ProviderResponse 归一契约与多段 content 拼接、幂等存储、租户限流、成本感知路由与审计日志（request_id+rationale+cost）。
- 评分：5

## proxypool
- 定位：经典免费代理池（Redis 存储+排序+验证），主打可扩展、简单。
- 技术栈：Python 3.6+ / Redis。
- 亮点：定时抓取-存储-Redis 可用性排序-验证剔除-API 随机取用（README 1-20）；官方代理池原理教程支撑（cuiqingcai.com/7048）。
- 对主项目价值：无价值为主（主项目 proxy_pool.py 已覆盖且更现代）；可作免费源/排序思路参考。
- 借鉴点：Redis 有序集合按可用性排序、验证调度。
- 评分：2

## 2Captcha-MCP
- 定位：把 2Captcha 完整 API 面（43 工具）暴露给 Claude Code 的 stdio MCP server。
- 技术栈：Python 3.11+（官方 mcp SDK + pydantic + mypy strict）。
- 亮点：
  1. **SDK 复用策略**：基于官方 2captcha-python AsyncTwoCaptcha，重试/轮询/解析全交给上游 SDK，SDK 加新类型即自动可用（README 顶部）。
  2. **声明式工具注册**：tools/ 用 ToolDef 泛型 + pydantic BaseModel 作 input schema，`_input_schema_for` 自动生成（server.py 15-32）；webhook_receiver/ 附带签名校验（signature.py）+ 事件存储。
  3. 43 工具 = 31 求解 + 5 管理 + 3 pingback CRUD + 3 webhook + 1 复合 solve-and-wait。
- 对主项目价值：局部借鉴（主项目有 cf_solver 而非 2Captcha，但"声明式工具注册 + 复合 solve-and-wait 工具"可对照主项目 MCP 五工具改造）。
- 借鉴点：ToolDef 声明式工具表驱动注册、复合工具（solve-and-wait）、webhook 签名校验。
- 评分：3

## OWASP-MCP-Governance-and-Risk-Project
- 定位：组织采用 MCP 的治理/风险框架（不是代码实现，是治理文档集）。
- 技术栈：Markdown 框架（v1.0 指南 + 映射 + 参考）。
- 亮点：
  1. **四不原则**：无 owner 不批准、无日志不生产、无范围定义不接入、无审查不部署（README 关键治理规则表）。
  2. **MCP 服务器分级**：按最高风险工具分类（Tier 0-4），本地 stdio 加固要求、预批准目录（README 各角色章节）。
  3. 控制映射到 OWASP MCP Top 10 / LLM Top 10 / NIST AI RMF / ISO 42001 / SOC 2（framework-mapping.md）。
- 对主项目价值：直接借鉴（主项目 MCP 服务端对外开放，可引入其"服务器资产清单+分级+审批证据包"作为管理面板 Security 页/接入审核流程的治理文档依据）。
- 借鉴点：MCP 服务器风险分级与审批台账、工具链（tool chaining）为头号风险视角、日志审计要求（主项目已有 SSE 审计）。
- 评分：4

## Windows-MCP
- 定位：Windows OS 接入 AI agent 的 MCP server（UI 自动化/文件/注册表/进程等），2M+ 用户。
- 技术栈：Python 3.13，按领域分模块（desktop/filesystem/powershell/registry/uia/process/watchdog）。
- 亮点：
  1. **server.json 标准清单**：MCP registry 规范的 server.json（含 transport: stdio、runtimeHint: uvx、pypi 标识），可作为主项目 MCP server 上架目录的模板（server.json 全文）。
  2. **领域分模块工具集**：按 OS 能力域拆分工具包（src/windows_mcp/*），每域独立。
  3. 桌面自动控制（uia）+ powershell + watchdog，适合 agent 操作系统级任务。
- 对主项目价值：局部借鉴（主项目桌面 Tauri sidecar 若想暴露 Windows 能力给 agent，可直接参考其领域模块划分与 server.json 清单）。
- 借鉴点：MCP registry server.json 标准清单、OS 领域模块化工具组织。
- 评分：3

## awesome-mcp-servers
- 定位：MCP 服务器精选清单（数百条目 + 分类目录）。
- 技术栈：纯 Markdown 聚合。
- 亮点：生态地图（aggregators/security/coding agents 等分类）、图例（语言/范围/OS 徽标）、链接 glama.ai 目录与 TDQS 工具定义质量评分工具（README 1-60）。
- 对主项目价值：扩展方向参考（主项目做 MCP 生态，可借用其分类维度与 TDQS 工具定义质量思路）。
- 借鉴点：MCP 服务器目录分类法、TDQS 工具定义质量评分（主项目五工具描述质量可自评）。
- 评分：3

## chrome-devtools-mcp
- 定位：Google 官方 Chrome DevTools MCP server，让 coding agent 控制真实 Chrome（调试/性能/网络/截图）。
- 技术栈：TypeScript/puppeteer/CDP，按能力域拆 tools/（console/network/pages/performance/screenshot/snapshot/slim/...）。
- 亮点：
  1. **能力域工具模块化**：tools/ 下每域一文件 + ToolDefinition.ts 声明式定义（src/tools/*.ts 清单）；slim/ 轻量模式（README --slim）。
  2. **自动等待动作结果**（puppeteer）与 source-mapped 堆栈；性能洞察走 CDP trace + CrUX 字段数据。
  3. 遥测与更新检查默认开、可 opt-out（--no-usage-statistics/--no-update-checks，README 46-66）。
- 对主项目价值：扩展方向参考（主项目管理面板若需浏览器验证/调试能力可借鉴；工具按域声明式定义模式与主项目 provider 分组同思路）。
- 借鉴点：按域拆分工具 + 声明式 ToolDefinition、slim 模式裁剪工具面。
- 评分：3

## mcp-captcha-solver
- 定位：AI agent 验证码求解 MCP server（本地 OCR + 滑块 + 外部服务 + 智能回退）。
- 技术栈：Node.js（captcha-mcp/）+ Tesseract.js 本地 OCR。
- 亮点：多求解源自动切换（CapSolver/CapMonster/2Captcha/Anti-Captcha…，README Capabilities）、本地 OCR 免外部 API、滑块边缘检测、网格坐标映射。
- 对主项目价值：扩展方向参考（主项目 cf_solver 专注 Turnstile；此项目覆盖图文/滑块/网格等通用验证码面，可作能力补充视角）。
- 借鉴点：多求解源智能回退矩阵、本地 OCR 降成本。
- 评分：3

## mcp-chrome
- 定位：Chrome 扩展型 MCP server——直接用用户日常 Chrome（复用登录态/配置），无需独立浏览器进程。
- 技术栈：TypeScript + pnpm workspace + WASM-SIMD 向量加速。
- 亮点：
  1. **扩展型架构对比**：相比 Playwright 型 MCP，启动快、复用登录态、全量 Chrome 原生 API（README 对比表 40-60）。
  2. **Streamable HTTP** 连接 + 跨 tab 上下文 + 内置向量库语义搜索（README Core Features）。
  3. **WASM SIMD 加速**：向量运算 4-8x（README 20-30）。
- 对主项目价值：扩展方向参考（主项目桌面端若做浏览器自动化，扩展型 vs Playwright 型选型可参考；Streamable HTTP 落地实例）。
- 借鉴点：扩展型 MCP server 架构、语义搜索向量库、WASM 加速。
- 评分：3

## mcpstrike
- 定位：MCP server + Ollama 驱动的自主渗透测试框架（TUI 客户端 + MCP 服务器 + 外部后端）。
- 技术栈：Python 3.10+ / FastMCP / Ollama，三组件分离（client/server/backend）。
- 亮点：FastMCP 实现 15 工具（会话/命令管理）；策略层 policy.py 控制 agent 调用边界；client/ollama_bridge.py 连接本地 LLM 驱动工具调用。
- 对主项目价值：无价值为主（渗透测试方向与主项目无关）；可看"策略层约束 agent 工具调用"与主项目工具安全护栏同思路。
- 借鉴点：client 侧策略文件约束 MCP 工具调用（policy.py）。
- 评分：2

## mobile-mcp
- 定位：iOS/Android 移动自动化 MCP server（模拟器/真机统一接口）。
- 技术栈：TypeScript，src/ 按平台（ios.ts/android.ts/mobile-device.ts/webdriver-agent.ts）。
- 亮点：**无障碍树优先**（不依赖视觉模型/图像 token，快且省），必要时回退截图+坐标（README Main Features 40-60）；一套 API 覆盖 iOS+Android 模拟器/真机。
- 对主项目价值：扩展方向参考（agent 若需移动端操作；"无障碍树优先、视觉回退"的省 token 设计思路可借鉴）。
- 借鉴点：结构化可访问性快照 + 坐标回退、平台无关抽象。
- 评分：2

## smart-mcp-proxy__mcpproxy-go
- 定位：**MCP 服务器联邦代理**——几百个上游 MCP server 统一收敛成一个安全端点，规避 Cursor 40 工具/OpenAI 128 函数上限，省 token 且带安全隔离。
- 技术栈：Go 单二进制 + 内嵌 Web UI + macOS 托盘；上游支持 stdio/HTTP(streamable-http)/SSE，配置支持 Cursor/Claude Code/VS Code（internal/connect/clients.go）。
- 亮点：
  1. **retrieve_tools 渐进式工具暴露**：agent 只加载一个 retrieve_tools 函数（BM25 检索，internal/index/bleve.go），按需用 describe_tool 取全 schema（批量≤5），工具名 `server:tool` 寻址；宣称 ~99% token 削减 + 43% 准确率提升（README Why 节）。
  2. **调用意图分级 + 注解校验**：call_tool_read/write/destructive 三变体，intent.operation_type 必须匹配工具注解（read 调不到 destructive），参数与响应都过敏感数据扫描（README How 节 2-3）。
  3. **安全隔离**：Tool Poisoning 自动隔离（新 server 未批准即 quarantine）+ Docker 扫描插件（Snyk/Semgrep/Trivy 归一 SARIF + 复合风险分）；每个调用进 Activity Log 含 request_id 可关联审计（README How 节 3 + features 清单）。
  4. **tools preflight**：无接触上游即可预检工具是否可用（隔离/OAuth 过期/改版/拼错），返回结构化退出码供 cron/CI 门禁（README 230-260）。
  5. /mcp 端点多路由模式：default/direct(code_execution)/retrieve_tools 由 routing_mode 绑定（internal/httpapi/server.go 1296-1304），session 管理与 initialize 握手超时（server.go 1833）。
- 对主项目价值：**直接借鉴（主项目 MCP 服务端 Streamable HTTP 升级 + 外部 client 接入的头号参照）**：retrieve_tools 渐进暴露正好解决"主项目技能库工具多、描述占上下文"问题；意图分级/注解校验即主项目"工具调用安全护栏"的升级版；activity 审计与主项目 SSE 审计互补。
- 借鉴点：BM25 渐进式工具检索（retrieve_tools/describe_tool）、读/写/破坏性三意图注解校验、新工具自动隔离审批（quarantine）、Docker 扫描插件归一 SARIF、tools preflight 门禁、/mcp 多路由模式。
- 评分：5

## stealth-browser-mcp
- 定位：隐身浏览器自动化 MCP server，专攻 Cloudflare 挑战/反爬/登录墙。
- 技术栈：Python 3.10+ / nodriver(CDP) / FastMCP。
- 亮点：nodriver 无头 CDP 直接驱动真实 Chrome 系浏览器，隐身指纹 + 代理 + 自动等待；FastMCP 实现；带 Agent Skill 与 Trust Model 文档（README TOC）。
- 对主项目价值：扩展方向参考（主项目 cf_solver 处理 Turnstile；此项目从浏览器侧绕过反爬，可作为复杂场景备用视角）。
- 借鉴点：nodriver 直接 CDP 驱动、隐身指纹参数化。
- 评分：3

## token-optimizer-mcp
- 定位：context/工具调用优化 MCP 插件——让昂贵的 Read/Grep/Edit 变不可能或降级为 diff，附知识图谱与自计量 dashbaord。
- 技术栈：Node 22+，hooks/ 钩子机制（install-hooks.ps1 支持 Windows），MCP server + 本地图谱。
- 亮点：
  1. **工具调用降级**：会话内重读文件只返回 diff；超限 Read 直接拒绝并指出缓存替换（README 30-second 版 1）。
  2. **per-project 知识图谱**：findings/decisions/dead-ends 随工作累积并回喂，一条 finding ~150 token vs 重新推导 5k-50k（README 2）。
  3. **自计量/归因**：materialized before/actual-return 计量，按操作与 MCP 握手身份归因到各 client（Codex/Claude/Gemini 分开行）（README 4）；token 记账契约文档 docs/TOKEN_ACCOUNTING.md。
- 对主项目价值：直接借鉴（主项目记忆 L1-L3 巩固 + skills 库，可借鉴"知识图谱回喂降本 + 工具调用 diff 降级 + 按 agent 归因计量"，与主项目 MCP 预算门禁互补成计量闭环）。
- 借鉴点：会话内重读 diff 化、per-project 知识图谱回喂、按 MCP client 归因的 token 计量与审计。
- 评分：4

## trace-mcp
- 定位：索引 agent 反复重读的代码库并为 agent 提供答案的 MCP 服务（"回答而不是重读"），PR 审查 token 降 72.7%。
- 技术栈：TypeScript（packages/ 多包）+ 桌面 app（GPU 图浏览器）+ MCP server；DESIGN.md 记载极致设计系统。
- 亮点：
  1. **代码库索引 + 语义服务**：把重复重读的文件/符号转为索引查询答案，182 工具/81 语言/88 框架集成（README banner 声称，72.7% 实测中位数）。
  2. **可复现基准**：preregistration 预注册 + 双盲质量评分（67% vs 65% 理解率，README 70-75）——工程严谨度标杆。
  3. DESIGN.md 明确"代码优先，文档与代码冲突以代码为准"的设计系统文档纪律（DESIGN.md 1-15）。
- 对主项目价值：扩展方向参考（主项目 codegraph/graft 图谱已类似；trace-mcp 的"重读→索引答案"范式与量化基准方法可借鉴到主项目上下文优化）。
- 借鉴点：重读检测 + 索引答案、预注册基准方法论、索引服务与桌面图浏览器。
- 评分：3

## x64dbg-mcp-server
- 定位：x64dbg 调试器的原生 MCP 插件（agentic 逆向），Streamable HTTP + SSE 双传输。
- 技术栈：Zig 零依赖单二进制，跨编译 x32/x64。
- 亮点：
  1. **双传输**：Streamable HTTP + SSE 双支持，兼容新旧 MCP client（README Features + Usage 节 70-90），是"升级 Streamable HTTP 同时兼容 SSE"的直接落地范例。
  2. **Bearer 强制鉴权**：首启自动生成 token，每请求必验（README Features）。
  3. 84 MCP 工具 + 22 事件回调 + 配置对话框热重启（README Features）。
- 对主项目价值：直接借鉴（主项目 MCP POST /v1/mcp JSON-RPC 升级 Streamable HTTP 可对照其"双传输兼容 + Bearer 鉴权 + 事件回调"；自动 token 生成是主项目缺的）。
- 借鉴点：Streamable HTTP + SSE 双传输兼容、自动生成 Bearer token 鉴权、MCP 事件回调（对应主项目 SSE 事件流）。
- 评分：4

---

## 本组汇总：Top3 最值得主项目借鉴项

**🥇 #1 smart-mcp-proxy__mcpproxy-go — retrieve_tools 渐进式工具暴露 + 意图分级安全护栏（直接借鉴，评分 5）**
主项目 MCP 五工具升级 Streamable HTTP 的头号参照：BM25 检索式 retrieve_tools + 按需 describe_tool（internal/index/bleve.go、/mcp/call 路由模式）、read/write/destructive 三意图注解校验、新工具自动隔离审批、tools preflight 门禁。解决"外部 client（Claude Desktop/Cursor）接入 + 工具多占上下文 + 工具调用安全"三个当前关注点；其 activity 审计与主项目 SSE 审计可直接互补。

**🥈 #2 nexus-llm-router — 同栈（Python/FastAPI/httpx）可插拔路由 + 全套网关护栏（直接借鉴，评分 5）**
与主项目完全同技术栈，Observe→Decide→Act 生命周期 + 5 种可插拔策略（vs 主项目 MAB-EWMA 单策略）；适配器 ProviderResponse 归一契约（含多段 content 全量拼接的坑）是主项目 5 家图像上游抽象的直接对照；幂等存储、注入网关、虚拟 key 预算、租户限流、成本审计日志是主项目安全/预算门禁的现成扩展。

**🥉 #3 new-api / Wei-Shaw__sub2api — 渠道加权随机 + token 级计费 + 多账号粘性路由（直接借鉴，评分 5）**
new-api 的渠道加权随机+失败自动重试+用户级模型限流+OIDC 多登录源+缓存计费，sub2api 的 token 级计费+内置支付+Composite Groups 多供应商路由+每账号并发限流——共同构成主项目号池/预算门禁升级为"真计费/限流/路由"的完整路线图。另 ai-gateway 的 memory→redis 共享状态可插拔切换与 9router 的 RTK tool 输出压缩为有效补充。

（补充：x64dbg-mcp-server 提供"Streamable HTTP+SSE 双传输 + 自动 Bearer token"的最小落地范例；token-optimizer-mcp / casbin-gateway 提供工具调用降级与 MCP server 矩阵管理的工程范式。）
