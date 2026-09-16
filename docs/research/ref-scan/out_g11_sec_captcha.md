# g11_sec_captcha 组扫描报告（安全工程 + 验证码类，26 目录）

> 只读分析。主项目「听风AI」关注：①验证码求解/防自动化检测工程实践；②安全工程（限流/鉴权/防注入/防爬）；③agent 化中的安全护栏。

---

## AI-Pentest
- 定位：HackingArticles 整理的"用 LLM/MCP 做渗透测试"文章链接合集（AD/无线/Recon/利用），非可运行代码。
- 技术栈：Markdown 指南（无代码）
- 亮点：无实质代码实现，仅索引了 MCP 形态的攻防工具（BloodHound MCP、Aircrack MCP 等）的用法文章。
- 对主项目价值：无价值
- 借鉴点：无（仅可当安全 MCP 工具生态的线索目录）
- 评分：1

## AI2PentestTool
- 定位：AI Agent 驱动的一键渗透工具安装器，智能生成安装计划并可故障自恢复。
- 技术栈：Python + OpenAI API + rich CLI
- 亮点：
  1. 「AI 计划 → 内置预定义计划 → 备份命令 → 手动指引」四层降级漏斗（`ai_agent.py` `get_install_plan`）。
  2. AI 调用失败自动重试 3 次×2s，并按错误类型（SSL/DNS）分类恢复（`ai_agent.py`）。
  3. 全部操作落盘日志（无 AI 时也能稳定工作）。
- 对主项目价值：局部借鉴（容错降级思想可移植到 solver_guard 的求解失败降级链）
- 借鉴点：多级计划降级 + 错误分类重试模式
- 评分：3

## AutoPentestX
- 定位：传统 Python 自动化渗透流水线：扫描→漏洞→CVE→风险→利用→PDF 报告。
- 技术栈：Python + SQLite + 模块化（`modules/`）
- 亮点：
  1. 风险引擎按 CVSS + 加权因子（exploitable 2.0/public_exploit 1.5/network_accessible 1.3）聚合评分（`modules/risk_engine.py`）。
  2. `safe_mode` 贯穿；exploit 数据携带 `safe` 标记，非安全利用默认跳过（`modules/exploit_engine.py`）。
- 对主项目价值：扩展方向参考（风险聚合模型可用于审计评分维度）
- 借鉴点：CVSS→风险等级 + 加权因子的量化口径
- 评分：2.5

## CyberStrike
- 定位：开源 offensive-security AI agent（npm 包，13+ 专项 agent、7600+ skills、176+ MCP 工具）。
- 技术栈：TypeScript + Bun monorepo（`packages/cyberstrike/`）
- 亮点：
  1. **PermissionNext 规则引擎**：`allow|deny|ask` 动作 + 通配符 pattern（支持 `~`/`$HOME` 展开）组成 Ruleset，Ruleset 可 `merge` 叠加（agent 基础规则 + 场景规则），`packages/cyberstrike/src/permission/next.ts`。
  2. **按 agent 角色默认收紧权限**：如通用 research agent 直接 deny `todoread/todowrite/report_vulnerability/triage_vulnerability` 等越权工具（`agent/agent.ts` fromConfig defaults）。
  3. PermissionRequest 带 always 数组 + 存储持久化（session.sql PermissionTable），决策过程可审计。
- 对主项目价值：直接借鉴（agent 权限规则引擎正是主项目 agent 安全护栏缺的一环）
- 借鉴点：allow/deny/ask 规则集 + 通配符 + 按角色默认收紧 + 规则合并
- 评分：4.5

## Pentest-Swarm-AI
- 定位：Go 实现的"真实 swarm"渗透测试框架——多 agent 通过共享黑板（stigmergic blackboard）协作，非顺序管线。
- 技术栈：Go + Postgres/memory 双后端 + Claude/Ollama
- 亮点：
  1. **黑板接口抽象**：`Board` 接口（Write/Query/Subscribe/Cursor）+ Memory/Postgres 实现可切换；Subscribe + `CommitCursor` 提供 at-least-once→exactly-once 消费；finding 带虫胶 `Pheromone` 衰减权重做信号排序（`internal/swarm/blackboard/board.go`）。
  2. **MINJA 内存注入防御**（`injection_test.go` 固化）：按 type 查询隔离 + MinPheromone 阈值过滤 + pheromone clamp 防伪造高权重 + agent 名身份由 provenance 层校验——正是 agent 共享记忆被投毒的标准防御清单。
  3. **双级预算门禁**：campaign 级 Budget（hours+tokens）与 per-agent `AgentBudget`（单 agent 跑飞不烧全营，warnAtTokens 软阈值）`board.go`。
  4. **executor 安全护栏**（`internal/agent/exploit/executor.go`）：scope 校验硬停 + 可执行文件 allowlist（拦截 bash/sh -c/python -c 解释器桥接 RCE）+ destructive tokens deny-list（rm/DROP/TRUNCATE/kill/chmod）+ 引号感知 parseCommand 拒绝未加引号的 `|><&;$()` 元字符 + 120s 超时 + 执行前注册 cleanup 命令。
  5. **scope 强制审计**：`scope.ValidateAndLog` 每次工具调用强制结构化日志（violation→WARN 含目标与允许范围；成功→DEBUG 证明确查过），杜绝静默吞错。
  6. compliance 模块把 finding 映射 PCI/SOC2/ISO27001/NIST（诚实纪律：只"提供证据 toward"，不断言合规）。
- 对主项目价值：直接借鉴（黑板协调 + 内存注入防御 + 双级预算 + executor 护栏与主项目 DAG 编排/预算门禁/request_guard 高度互补）
- 借鉴点：memory-injection 防御（query-by-type/pheromone/provenance）、per-agent token 预算、命令引号解析安全、强制审计日志
- 评分：5

## VulnClaw
- 定位：AI 驱动的渗透测试 CLI Agent，模型主导求解循环 + 证据记忆 + 反幻觉闸门（中国团队，中文友好）。
- 技术栈：Python + OpenAI 兼容 + MCP
- 亮点：
  1. **AgentState 证据记忆**：工具结果原文完整入 evidence，context 只注入高信号预览，`evidence_search/evidence_view` 按需回查——解决长上下文被证据灌爆的问题（`agent/agent_state.py`、`correction_layer.py`）。
  2. **证据级反幻觉闸门**：声称的 flag/结论必须与真实工具输出逐字符匹配才采信，杜绝编造胜利。
  3. **ExecutionGate 内容寻址批准**（`agent/exec_gate.py`）：危险工具每次请求按 SHA-256 全文哈希一对一批准，无会话级 allow、无前缀通配、无 grant token；inflight hash 去重防重放；bidi/零宽/控制字符转义后再展示防终端注入。模式 ask/auto_review/full_access 三档。
  4. **轻量纠偏层**：不搞重规划器，只记录重复调用/失败降级/耗时/新发现信号让模型下轮自纠（stall guard 抑制空转）。
- 对主项目价值：直接借鉴（critic 自反思 + 记忆巩固 + 审批持久化 + 防重放批准）
- 借鉴点：证据进出上下文的分层、内容寻址一次性批准、bidi 显示转义、轻量纠偏信号
- 评分：5

## autopentest-go
- 定位：agentic 安全工作区，桌面(Wails)+CLI(Cobra) 双端、单一 tool-using LLM 运行时。
- 技术栈：Go 1.26 + Wails + Vite(TypeScript 前端) + SQLite
- 亮点：
  1. **权限模式矩阵**：External modes（acceptEdits/bypassPermissions/default/dontAsk/plan）+ behavior（allow/deny/ask）+ 规则来源分层（userSettings/projectSettings/localSettings/flag/policy/cliArg/command/session）可区分优先级与继承（`internal/types/permissions.go`、`sdk` 对齐的 PermissionUpdate 判别联合）。
  2. **bash 工具护栏**：`isDestructive` 标记 + 统一 `CheckPermissions` 入口、禁止后台执行、stderr 重定向 `/dev/null` 检测（防吞错误）、超时控制（`internal/tools/bash_tool.go`）。
  3. **记忆三 scope 分级可视**（session/global/project）+ **落库前全链路脱敏**（text/thinking/toolInput/JSON/图片 URL 全部走 `RedactSensitiveText`，脱敏破坏 JSON 结构时保守失败不回退）`internal/memory/*.go`。
  4. evidence capture → store → 向量检索（qdrant/sqlite 双后端）闭环。
- 对主项目价值：直接借鉴（权限模式矩阵 + 落库前脱敏 + 证据闭环，主项目桌面三件套/v15 工具护栏可直接对齐）
- 借鉴点：permission 来源分层与模式聚合、storage 前脱敏、bash 危险重定向检测
- 评分：4.5

## awesome-ai-security
- 定位：AI 安全资源精选清单（OWASP LLM/Agentic Top10、MCP 安全、Red teaming 训练场等链接）。
- 技术栈：Markdown 链接索引
- 亮点：目录组织规范；覆盖 OWASP LLM Top10 / Agentic AI Top10 / MCP 安全 cheatsheet 等防御侧社区资源。
- 对主项目价值：扩展方向参考（可当主项目安全外围清单的目录）
- 借鉴点：无代码；对 agent 威胁模型查漏有索引价值
- 评分：1.5

## claude-code-security-review-main
- 定位：Anthropic 官方 Claude Code security-review GitHub Action——PR 变更的语义安全审查。
- 技术栈：Python + Claude API + GitHub Actions
- 亮点：
  1. **diff-aware**：只扫 PR 改动文件；按 commit 缓存去重。
  2. **误报过滤两段式**（`claudecode/findings_filter.py`）：`HardExclusionRules` 硬规则（DoS/rate-limit/资源类 regex 预编译）先排除 → Claude 二次语义判定 + 置信度打分 → 只保留高信号 finding；可配置自定义过滤指令。
  3. findings-count / results-file 结构化输出对接 CI。
- 对主项目价值：局部借鉴（审计链路的误报过滤管线 — 硬规则+语义二判）
- 借鉴点：硬规则预过滤 + LLM 二判 + 置信度的三层漏斗
- 评分：3

## codex-security
- 定位：OpenAI Codex Security —— 定义安全策略并扫描/验证/修复漏洞的 CLI + TypeScript SDK + findings 服务。
- 技术栈：Node 22 + TS + Python（原生校验器）+ Docker compose + SQLite
- 亮点：
  1. **策略生成**：`codex-security policy` 从仓库/组件生成 SECURITY.md 草案并放置仓外，架构/威胁模型文档也停留在 checkout 外（不污染仓库、防敏感泄露）。
  2. **去重评审结构化抽象**（`sdk/typescript/src/deduplication/codex-review.ts`）：`CodexReview` 带 stage/model/effort/schema(→`z.object(...).strict()`)+validate，重试/失败分类/可恢复，天然抗 LLM 输出抖动。
  3. findings 服务 + sqlite-store + embeddings 去重（`src/server/`）。
- 对主项目价值：局部借鉴（发现去重 + 严格 schema 约束的 LLM 评审包装）
- 借鉴点：LLM 评审输出用严格 schema 校验并分级重试；findings 服务化
- 评分：3.5

## cybersentinel-ai
- 定位：本地 Docker 化 agentic 安全平台——真执行 nmap/nuclei/sqlmap 等 33 工具并 AI 分析，Neo4j 知识图 + ChromaDB RAG + ELK。
- 技术栈：FastAPI + Ollama/Claude/GPT/OpenRouter + Docker + Neo4j + ChromaDB
- 亮点：
  1. **代码级硬护栏**（`backend/app/core/guardrails.py`）：正则级 jailbreak/系统提示词提取/数据外泄/多轮升级检测，分 BLOCK（直接拒绝进 LLM）与 warn 两档，明确"非 system prompt，模型无法绕过"。
  2. **LLM intent 路由**（`core/intent.py`）：意图识别强制只输出 JSON 工具选择（可用工具闭集 + target 参数抽取），聊天与执行分离。
  3. `test_guardrails.py`/`test_intent.py`/`test_security_regressions.py` 把护栏当回归测试维护。
- 对主项目价值：直接借鉴（LLM 前正则护栏 + 闭集工具路由，主项目 chat 端点/agent 输入检测可套用）
- 借鉴点：输入侧正则硬闸（BLOCK vs warn）+ LLM 只允许闭集工具 + 护栏测试
- 评分：3.5

## exploitgym
- 定位：UC Berkeley 大规模 exploit 评测基准（真实 CVE 场景，V8/Linux kernel/用户态）。
- 技术栈：Python + Docker + squid + gdb/socat
- 亮点：
  1. **双层网络防火墙设计**（`docs/firewall.md`）：run proxy（allowlist 仅放 LLM API 域）+ install proxy（allow-all 仅安装期用），容器挂在无默认路由的内网，即便程序忽略 HTTP_PROXY 直连也出不去——隔离到网络层而非仅环境变量。
  2. **controller 启动时生成 secrets**（token salt/flag seed/API key），仓库零硬编码密钥（`docs/eval.md#controller-secrets`）。
  3. 评测=追 flag + controller 双端同值校验，mock 也可验证。
- 对主项目价值：扩展方向参考（cf_solver 多节点隔离部署/密钥托管可借鉴无硬编码 secret 的启动期生成模型）
- 借鉴点：网络层出站隔离（无默认路由 + allowlist 代理）、启动期生成 secret
- 评分：4

## sunblaze-ucb__exploitgym
- 定位：同上 exploitgym 的镜像副本（同 README/结构）。
- 技术栈：同 exploitgym
- 亮点：与 exploitgym 内容一致（重复收录），无新增信息。
- 对主项目价值：无价值（去重：与 exploitgym 相同）
- 借鉴点：无
- 评分：—（重复项，按 2.5 计）

## hackingtool
- 定位：AI 引导的一体化授权测试工具箱，215 工具 × 21 分类，自然语言→正确工具+命令。
- 技术栈：Python + catalog(YAML 工具注册表) + OpenAI/Ollama
- 亮点：
  1. **闭集防编造**（`src/hackingtool/ai_recommend.py`）：模型只允许返回 closed `TAXONOMY` 内的 tag，不在集内一律丢弃；tag→工具由 catalog 解析，模型无法凭空造出工具；无模型时退化为 stdlib 关键词匹配器。
  2. AI 生成命令一律标记 "⚠ AI-generated — unverified. Confirm with --help"（`core.py:273`），未经验证不执行。
  3. `/goal` 逐步计划 + `/find` 工具发现 + tmux 后台窗，工程化完善。
- 对主项目价值：直接借鉴（模型输出闭集校验 + 无模型降级 + 未验证标记——正好补主项目 hint/工具生成的幻觉面）
- 借鉴点：闭集 taxonomy 校验、stdlib 降级、生成命令 unverified 标注
- 评分：3.5

## pentest-harness
- 定位：开源暗色主题 AI 渗透测试工作台，全插件架构（Cordis），所有层可配置替换。
- 技术栈：TypeScript + Cordis 插件系统 + pnpm monorepo
- 亮点：
  1. **凭证 seam 设计**（`packages/credentials/`）：`CredentialRef`（POSIX 环境变量名引用）+ `CredentialKey`（`<scope>/<id>` 插件作用域键，payload 对 seam 完全不透明，防跨插件误读）；授权流程的 Notice 永不带 secret（`authorization/types.ts` 注释明写）。
  2. **guard 包**：`repeat-tool-reminder` + `timeout-policy`，专门防 agent 重复调工具/超时失控。
  3. context 永不死：token 计量 + 自动压缩 + 工具结果裁剪（`packages/compaction/`）。
- 对主项目价值：局部借鉴（凭证环境变量引用 + 权限提示不落日志；可改进主项目 mask_key/Key 存储）
- 借鉴点：credentials 用固定环境变量引用而非存储明文、重复工具提醒 guard
- 评分：4

## pentestcode
- 定位：终端自主渗透 agent（opencode 硬 fork，剥离编码编辑专注 offensive），单条指令→整条攻击链。
- 技术栈：TypeScript + Bun + effect（函数式 TS）+ SQLite
- 亮点：
  1. **engagement 状态机**（`packages/core/src/engagement/context.ts`）：phase/mode + compact JSON 摘要注入 `<pentest-engagement>` 块，结构化又省 token；状态持久化到 store 可 `/status` 查询。
  2. **scope-matcher 纯函数**（`scope-matcher.ts`）：IPv4/IPv6/CIDR 精确匹配（bigint 处理 v6），零依赖可单测。
  3. task-graph + reflection（反思）编排；每步 evidence chain 记录。
- 对主项目价值：局部借鉴（engagement 压缩注入格式 + scope 匹配纯函数）
- 借鉴点：结构化上下文压缩注入、IPv6/CIDR 纯函数匹配器
- 评分：3.5

## pentestkit
- 定位：多 agent 上下文累积渗透框架（Claude Agent SDK），orchestrator 驱动专家团队，XBOW 104/104 满分。
- 技术栈：Python 3.14 + Claude Agent SDK + kimi-k3
- 亮点：
  1. **ScopeGuard 单一出口**（`pentestkit/guardrails.py`）：deny_hosts fnmatch + CIDR + auto-subdomain zone 推导；连 CLI 参数都被 token 扫描抓越界主机（`_TOKEN_RE` 抠 URL/IP/域名），`_SCRIPT_BINARIES` 把 python3/node 这类"参数即脚本"的二进制排除在解析外。
  2. **verifier 证据闸门**（`pipeline/verifier.py`）：候选 finding 必须真实复现利用；要求"证明机制 AND 证明影响"，必做对照组（blind 用 OAST 出带宽证明），必排除补偿控制（compensating control），4 轴验证 real/triggerable/impactful/general + 证据阶梯 suspected→impact_proven；强调"持有操作员认证会话时 200≠证明"。
  3. **scorer**（`pipeline/scorer.py`）：CVSS 基向量必须从已验证证据推导，"看门狗风格审慎"，不得按标题 worst-case 打分。
- 对主项目价值：直接借鉴（critic 反幻觉按"证明机制+排除补偿控制+对照组/OAST"升级，评分必须扎根证据）
- 借鉴点：单一出口 scope guard + CLI 参数 token 扫描、verifier 4 轴验证与证据阶梯
- 评分：4.5

## CaptchaFoxChallengeSolver
- 定位：纯 Python 协议复现 CaptchaFox 挑战请求链路（config + SHA-256 PoW + body 加密）。
- 技术栈：Python + curl_cffi + loguru + 扣 JS（payload_crypt）
- 亮点：
  1. **PoW 设计**：`/captcha/{site_key}/config` 下发 `h`（服务器 nonce 派生）与 `m`（目标 + 前导零位数）→ 客户端 SHA-256 找 nonce（`src/main.py proof_of_work`）——理解上游"算力门禁"如何做反爬。
  2. 完整请求头指纹（sec-ch-ua/platform/fetch-dest）+ x-pulse 埋点。
- 对主项目价值：扩展方向参考（了解 PoW 型反自动化检测的机制，可用于理解 cf_solver 需要打过的对抗面）
- 借鉴点：PoW 前导零难度参数化机制（防御视角）
- 评分：2.5

## CloudFlareInvisibleSolver
- 定位：纯代码反解 Cloudflare Invisible 验证码的 payload（不依赖浏览器）。
- 技术栈：Python（zlib + 自定义 base64 + xorshift32 密钥流 + FNV1a + 码表）
- 亮点：
  1. 完整呈现"自定义 base64 字母表 + 逐字节 XorShift 密钥流 + FNV1a 种子"的混淆流水线（`decode_p.py`），码表需随 js 文件变化。
- 对主项目价值：扩展方向参考（理解 CF 侧 payload 混淆复杂度，间接说明浏览器方案/solver 联邦的必要性）
- 借鉴点：无直接可抄；仅对抗面认知
- 评分：2

## captcha
- 定位：Laravel 验证码契约库，统一 11 家 provider（Turnstile/hCaptcha/reCAPTCHA 各版本/自托管算术）。
- 技术栈：PHP 8.4 + Laravel 13 + phpunit
- 亮点：
  1. **port 契约 fail-closed**（`src/Contracts/CaptchaAdapter.php`）：任何传输错误/非 2xx/解析失败一律 failed，绝不 throw（throw 把上游故障变成 500）、绝不假 success（解析失败变"敞开大门"）；arch 测试禁止 adapter 内调 config()/request()/app()（强制构造注入，保证凭据来源可替换）。
  2. **SiteVerifyAdapter 抽象**（`Adapters/Concerns/SiteVerifyAdapter.php`）：turnstile/hCaptcha/reCAPTCHA 共用"POST token 到 siteverify"+同套字段映射，`verify()` final 结构性兜底吞异常——厂商差异收敛一处。
  3. **VerifyCaptcha 增值检查层**：供应商验证只回答"token 是真的"，此层补 replay/时效/hostname/action/score 检查，把"真 token"升级为"本次提交合理"（同一 sitekey 其它表单/其它 origin/一小时前/并行双用/0.1 分全部拦截）。
- 对主项目价值：直接借鉴（主项目 providers 抽象 + unified solved 协议 + fail-closed 正是同类思路，此库给出结构性落法）
- 借鉴点：adapter 契约 fail-closed、共享 transport 抽象、vendor 验证之上叠加通用反滥用检查
- 评分：4

## captcha-solver
- 定位：本地自托管验证码求解 HTTP sidecar（CloakBrowser 反检测 Chromium），11 类挑战原生浏览器求解。
- 技术栈：FastAPI + cloakbrowser(Playwright 系) + ONNX + cv2
- 亮点：
  1. **统一 solved 判定真源**（`server.py _is_solved`）：一站式判断全部 solver 输出（token/cf_clearance/verify_success/success），`solved` 字段与监控日志同源——与主项目 solver_guard 的"统一 solved 协议"异曲同工。
  2. **SSRF 防护**：`_assert_public_url` 拒绝非 http(s)、GETADDRINFO 解析后逐个 IP 校验 private/loopback/link-local/reserved/multicast，并主动注释 DNS-rebinding TOCTOU 残留风险（`SOLVER_ALLOW_PRIVATE` 显式放行）；`_validate_urls` 递归校验 url/verify_url/page_url/post_fetch[]。
  3. **参数化注入防护**：所有调用方值以 `page.evaluate(args)` 参数送达，从不插值进 JS 源码（`common/browser.py _FETCH_JS`），sitekey 同理（`turnstile/solve.py _WIDGET_INJECT_JS`）。
  4. **同会话 verify 保 token 窗口**：route-intercept 求解→同一浏览器会话内 POST verify（keep origin/cookies，贴合 300s 单次有效窗）；verify 响应体不入日志（防 JWT 泄露）。
  5. **cf_clearance 绑定与回放契约**（`cloudflare/solve.py`）：明确 cookie 绑定 IP+JA3/TLS+UA，返回完整 UA/proxy 并附警告，提示同 IP+UA+一致 TLS 栈回放；interstitial 两种变体（Managed Turnstile iframe / JS challenge 自动解）单代码路径 + DOM 标记轮询判完成。
  6. **人味化点击**：B-spline 路径 + overshoot（`turnstile/solve.py` 注释明确 page 级 mouse vs frame.click 的机器人指纹差异）。
  7. 按类型 asyncio.Lock + per-request proxy + ring buffer 监控 + 双 URL（公开域 Bearer/Caddy 层强制、本地免鉴权）。
- 对主项目价值：直接借鉴（与主项目 solver_guard 几乎同构：统一 solved 协议、SSRF 防护、参数化防注入、token 窗口内验证、clearance 绑定回放警告）
- 借鉴点：`_is_solved` 单一真源、SSRF getaddrinfo+逐 IP 校验、evaluate 参数化禁插值、同会话 verify、cookie 绑定回放契约
- 评分：5

## captcha-solver1
- 定位：captcha-solver 的 fork，追加 flow2api 集成 provider。
- 技术栈：同 captcha-solver（FastAPI + cloakbrowser）+ `private_waguri/`(flow2api_provider + injected_recaptcha)
- 亮点：
  1. 在 sidecar 之上加了 `private_waguri/flow2api_provider.py`（注入 IX Browser 视图的 reCAPTCHA Enterprise provider）与配套测试（`tests/test_flow2api_provider.py`），示范"求解服务外挂特定平台 provider"的扩展方式。
- 对主项目价值：局部借鉴（provider 插件化：主项目 providers/registry 可参考其"sidecar 外挂 provider"模式）
- 借鉴点：独立 provider 模块 + 独立测试集的插件扩展路径
- 评分：3.5

## cf-turnstile-token
- 定位：CLI 客户端，经 Peak API 获取 Turnstile token（无浏览器依赖，供 CI/QA 脚本化）。
- 技术栈：Python 单文件 + urllib
- 亮点：
  1. **站点 sitekey 自动抽取**：`data-sitekey`/`sitekey:`/`render:` 多形态正则（`cf_turnstile_token.py _SITEKEY_RE`）。
  2. 重试退避 + 结构化输出（纯 token / JSON）+ proxy-aware + action/cdata 透传。
- 对主项目价值：局部借鉴（作为求解服务的**客户端侧**模板：抽取→提交→重试→结构化返回，可作主项目集成测试的 fake 客户端）
- 借鉴点：sitekey 多形态抽取、脚本化客户端重试与结构化输出
- 评分：3

## hcaptcha
- 定位：API Evangelist 对 hCaptcha 的第三方公开 API 简介（OpenAPI/rate-limits/security 文档镜像）。
- 技术栈：OpenAPI + YAML（无运行代码）
- 亮点：
  1. `rate-limits/hcaptcha-rate-limits.yml` 与 `security/hcaptcha-domain-security.yml` 把官方限流/安全条目梳理成结构化配置，可对照防爬设计。
- 对主项目价值：扩展方向参考（限流条目可对照主项目 request_guard 的滑窗/令牌桶参数）
- 借鉴点：官方限流条目结构化（对照用）
- 评分：1.5

## hcaptcha-hsj-reverse
- 定位：逆向 hCaptcha hsj.js 的 AES 密钥调度（README 自标 OUTDATED，旧接口失效）。
- 技术栈：Python + pycryptodome + xxhash + msgpack + jsbeautifier
- 亮点：
  1. 演示"hook 密钥调度 + 从内存缓冲 dump 密钥"的逆向手法（`keyfetcher.py`），`algorithm.py` 汇集 AES-GCM/编码/哈希工具。
- 对主项目价值：无价值（已失效；纯逆向研究，且主项目走合法 solver 无需复刻）
- 借鉴点：无
- 评分：1

## ohmycaptcha
- 定位：自托管 YesCaptcha 兼容求解服务（19 任务类型，createTask/getTaskResult 异步语义）。
- 技术栈：FastAPI + Playwright + OpenAI 兼容模型（本地 SGLang/vLLM）+ Render/HF 部署
- 亮点：
  1. **任务异步模型**（`src/services/task_manager.py`）：内存 TaskManager，Solver Protocol 注册表按类型注册求解器，createTask 返回 uuid + 后台 asyncio 处理，状态 PROCESSING/READY/FAILED，10min TTL 惰性清理；多求解器=策略注入式扩展。
  2. **双模型后端**（`core/config.py`）：cloud 多模态(远程 OpenCompatible) 做音频等重型 + local 自托管做高吞吐图像识别，环境驱动可互换。
  3. 19 任务类型 3 分组（浏览器类/图像类/分类类）+ `client_key` 鉴权（`routes.py _check_client_key`）+ 浏览器 stealth 注入（`navigator.webdriver` 等 4 项 + turnstile.getResponse 双通道取 token）。
- 对主项目价值：直接借鉴（异步任务注册表 + 多求解器策略注入 + 结果轮询 API，主项目任务/审计/SSE 可对齐其 createTask/getTaskResult 语义）
- 借鉴点：Solver Protocol 注册表、10min TTL 清理、双模型(重型/高通量)分流
- 评分：4

---

# 本组汇总：Top3 最值得主项目借鉴项

1. **captcha-solver（评分 5）— 求解服务工程化的标准答案**
   与主项目 `solver_guard` 几乎同构：`_is_solved` 单一成功真源（统一 solved 协议）、`_assert_public_url` getaddrinfo+逐 IP 的 SSRF 防护（含 DNS-rebinding TOCTOU 注释与显式 `SOLVER_ALLOW_PRIVATE` 放行）、全部调用方值走 `page.evaluate` 参数化永不插值 JS（防注入）、token 300s 单次窗口内**同浏览器会话** verify、cf_clearance 绑定 IP+JA3+TLS+UA 并回传 UA/proxy 的回放契约警告。主项目可直接对照补齐这几条：SSRF 逐 IP 校验、参数化 evaluate、clearance 绑定回放元数据。

2. **Pentest-Swarm-AI（评分 5）— 多 agent 协调与护栏的完整范式**
   黑板 Board 接口 + Subscribe/Cursor 精确一次消费；**MINJA 内存注入防御四条**（query-by-type 隔离 / MinPheromone 过滤 / pheromone clamp / provenance 身份校验）正是 shared-memory agent 被投毒的标准防御清单；campaign 级 + per-agent 双级 token 预算（防单个 agent 烧穿全营）；executor 四重护栏（scope 硬停 + 可执行文件 allowlist 拦截解释器桥接 + destructive deny-list + 引号感知 parseCommand 拒绝未引号元字符）；`scope.ValidateAndLog` 强制每次工具调用落审计日志。主项目 DAG 编排/预算门禁/request_guard/agent 安全护栏可直接移植。

3. **VulnClaw（评分 5）— 证据记忆与反幻觉、一次性审批的门禁细节**
   AgentState 证据记忆（原文全保留 + context 只注入高信号预览 + 按需回查）解决长上下文灌爆；证据级反幻觉闸门（flag 必须逐字符出现在真实工具输出）；ExecutionGate 内容寻址（SHA-256 全文哈希一对一批准、无会话级 allow、无前缀通配、无 grant token、inflight hash 防重放）+ bidi/零宽/控制字符转义防终端注入；轻量纠偏层（记录重复调用/失败/耗时信号让模型下轮自纠，配 stall guard 抑制空转）。主项目 critic 自反思、记忆巩固（.wolf）、审批持久化（v13 已落地）可与这套门禁细节做最后几公里对齐。