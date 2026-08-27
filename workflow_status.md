# workflow_status.md — 项目对标审计与渐进改造工作流

> 更新日期：2026-08-27 · 当前阶段：Phase A（项目识别与对标分析）· 目标：识别主项目现状 + 参考项目筛选 + 差距分析 + 路线图

---

## Task Contract

| 项 | 内容 |
|------|--------|
| **原始目标** | 对主项目 imagefree-2ai 进行多代理项目识别、对标审计与渐进改造分析，参考可参考的项目/ 下的三个候选项目 |
| **当前阶段** | Phase A — 分析完成，等待实施授权 |
| **当前授权** | 仅读取和分析，不允许修改源代码 |
| **成功标准** | Phase A 九部分报告完整输出，workflow_status.md 更新，停在实施审批门 |
| **停止条件** | 用户确认实施范围前不得进入 Phase B |

---

## Task Graph

| ID | Agent/Owner | Goal | Dependencies | Deliverable | Validation | Status |
|----|-------------|------|--------------|-------------|------------|--------|
| A1 | 总协调 Agent | 仓库规则检查 + 工作区状态 | 无 | 识别摘要 | 文件存在 | ✅ DONE |
| A2 | 总协调 Agent | 主项目结构识别 | A1 | 项目识别结论 | 证据链完整 | ✅ DONE |
| A3 | 总协调 Agent | 参考项目递归发现 + 筛选 | A1 | 候选清单 + 评分 | 每个项目有证据 | ✅ DONE |
| A4 | 总协调 Agent | 主项目现状评估 | A2 | 现状总结 | 证据支撑 | ✅ DONE |
| A5 | 总协调 Agent | 参考亮点提炼 | A3 | 亮点清单 | 按项目列出 | ✅ DONE |
| A6 | 总协调 Agent | 差距分析 | A4 + A5 | 差距矩阵 | 各维度覆盖 | ✅ DONE |
| A7 | 总协调 Agent | 可迁移性分类 | A6 | 三分类清单 | 每项有原因 | ✅ DONE |
| A8 | 总协调 Agent | 优先级路线图 | A7 | 路线图 | 按 P0/P1/P2 | ✅ DONE |
| A9 | 总协调 Agent | 全栈实施方案 | A8 | 方案 | 各层覆盖 | ✅ DONE |
| **Gate** | 用户 | 确认实施范围 | A9 | 授权 | 审批 | ⏳ PENDING |

---

## Project Inventory

### 主项目识别摘要

| 项目属性 | 实际值 |
|---------|--------|
| **项目类型** | 生产级 AI API 网关（生图 + 文本对话） |
| **架构形态** | 单体 FastAPI 后端 + React SPA 前端 |
| **语言** | Python 3.11+（后端）、TypeScript/React 19（前端） |
| **主要框架** | FastAPI, httpx, aiosqlite, pydantic-settings, React 19, Vite |
| **包管理** | pip (requirements.txt), npm (frontend/) |
| **构建方式** | uvicorn 直接运行 / Docker Compose |
| **路由结构** | `api/routes/` 下 6 个路由域（health, tasks, generate, admin, chat） |
| **核心业务流** | 文生图/图生图: 验证 → 入队 → Worker 池 → 提供商路由 → 结果返回 |
| | 文本对话: 鉴权 → 代理轮换 → TryingOpen 上游 → 流式/非流式返回 |
| **API 协议** | 自定义 `/v1/generate` + OpenAI `/v1/chat/completions` + Anthropic `/v1/messages` |
| **数据层** | SQLite (WAL), 多个 DB 文件（任务、账号、邮箱、代理、使用量） |
| **配置管理** | `api/config/` 包（14 个子模块 + pydantic-settings），所有环境变量 IF_ 前缀 |
| **日志** | 内存环形缓冲区 log_buffer + 磁盘日志 + WebSocket 实时日志 |
| **可观测性** | Prometheus /metrics, OTel 分布式追踪, 健康检查, 诊断端点 |
| **测试** | 60 个测试文件, pytest + pytest-asyncio, 含集成/混沌/性能测试 |
| **CI/CD** | GitHub Actions: test + lint(ruff) + Docker build + sync_deploy check |
| **部署** | Docker Compose（cfsolver + api）+ 本地直接启动 |
| **中间件** | CORS, Turnstile 求解, 代理池, 号池, 邮箱池, 自动注册器, SSE 事件流 |

### 参考项目候选清单

| 项目 | 类型 | 技术栈 | 功能定位 | 业务相似度 | 架构参考价值 | 工程成熟度 | 可迁移性 | 总分 | 结论 |
|------|------|--------|---------|-----------|------------|-----------|---------|------|------|
| **cloudflare_temp_email** | Cloudflare Workers 全栈 | TypeScript/Hono, Vue 3, Rust WASM, D1 | 临时邮箱服务 | 4 — 邮箱池与主项目直接相关 | 5 — Worker 架构、邮件解析、Agent 友好设计 | 5 — 生产级（2k+ star） | 3 — 技术栈不同需适配 | 4.3 | **高价值参考** |
| **ohmycaptcha** | FastAPI 自托管验证码服务 | FastAPI, Playwright, SGLang | 19种验证码自动求解 | 5 — Turnstile 求解与主项目直接相关 | 4 — 任务管理、求解器架构 | 4 — 结构清晰、文档完整 | 4 — 同为 FastAPI Python | 4.3 | **高价值参考** |
| **free-vpn-anti-rkn** | 静态页面 + GitHub Actions | HTML, GitHub Actions | VPN 配置聚合 | 1 — 与主项目功能无关 | 0 — 纯静态页面无架构参考 | 2 — 简单的自动化脚本 | 0 — 不适用 | 0.8 | **不建议参考** |
| 代理订阅池.txt | 文本文件 | — | 代理订阅说明 | 1 — 代理相关但只是说明 | 0 | 0 | 0 | 0.3 | **无效/无关目录** |
| CloudFlare说明.txt | 文本文件 | — | 用户笔记 | 0 | 0 | 0 | 0 | 0.0 | **无效/无关目录** |

### 排除目录及原因

- `free-vpn-anti-rkn` — VPN 订阅列表，与主项目 AI 网关功能无关
- `代理订阅池.txt` — 纯文本说明，无代码参考价值
- `CloudFlare说明.txt` — 用户笔记，非项目

### 高价值参考项目

1. **ohmycaptcha** (评分 4.3/5)
   - 选择原因：同为 FastAPI 项目，Turnstile 求解能力与主项目直接相关，架构清晰（任务管理 + 求解器注册 + 异步轮询），19 种验证码类型覆盖
   - 借鉴方向：求解器注册模式、Playwright 的 Turnstile 交互方式、多模态模型在验证码识别中的应用

2. **cloudflare_temp_email** (评分 4.3/5)
   - 选择原因：邮箱池与主项目直接相关（自动注册需收验证码），Rust WASM 邮件解析性能极佳，Agent 友好设计模式值得借鉴
   - 借鉴方向：Rust WASM 在邮件解析中的应用（可复用思路）、邮箱源优先级管理、AI 邮件识别（验证码提取）

---

## 决策摘要

### 任务复杂度评估

| 维度 | 评估 |
|------|------|
| **复杂度** | **标准** — 主项目已有完整 workflow_status.md 和下一步改进指南，参考项目清晰，不需要从头探索 |
| **判断理由** | 主项目 v5.1.0 已是生产级网关，工程成熟度高；两个高价值参考项目与主项目现有功能高度相关（邮箱池 + Turnstile 求解），不存在颠覆性架构差异 |
| **当前目标** | 完成 Phase A 九部分报告，停在实施审批门 |
| **已知约束** | 分析阶段不修改源代码；不覆盖用户已有改动 |
| **关键未知项** | 用户对路线图的优先级偏好；未来是否计划将 ohmycaptcha 作为替换/补充 cf_solver 引入 |
| **最脆弱的隐藏假设** | 假设 cloudflare_temp_email 的 Rust WASM 邮件解析可以通过重新实现或绑定方式迁移到 Python 生态 |
| **预计工作流** | 单 Agent 串行调查（因依赖关系清晰，参考项目仅 3 个且 2 个高价值 + 1 个无关） |
| **主要验证方式** | 文件证据、代码引用检查、命令输出 |
| **当前阻塞项** | 无 |

---

## Evidence Ledger

| Claim | Evidence | Type | Confidence |
|-------|----------|------|------------|
| 主项目版本号已统一为 5.1.0 | `api/main.py:34`, `pyproject.toml:4`, `frontend/package.json:4`, `deploy/docker-compose.yml:3` | DIRECT | 4/5 |
| playwright-core 已添加到 frontend/package.json | `git diff -- frontend/package.json` | DIRECT | 5/5 |
| `test_priority_queue.py` 的 `client_ip` 桩已修复 | `git diff -- tests/test_priority_queue.py` | DIRECT | 5/5 |
| minimaxh3/kookeey 死代码已不存在 | `grep -rln "minimaxh3\|kookeey" api/ deploy/ scripts/` 无命中 | DIRECT | 5/5 |
| pyproject.toml 缺少 `slow` marker | `grep -n "slow" pyproject.toml` 无命中 | DIRECT | 5/5 |
| start.ps1 缺少 `deploy/cf_solver` 路径 | `start.ps1` 候选路径 vs `deploy/cf_solver` 存在 | DIRECT | 5/5 |
| ohmycaptcha 使用 Playwright 实现 Turnstile 求解 | `可参考的项目/ohmycaptcha/src/services/turnstile.py` | DIRECT | 5/5 |
| cloudflare_temp_email 使用 Rust WASM 解析邮件 | `CLAUDE.md` 描述 `mail-parser-wasm/` | DIRECT | 5/5 |
| 主项目邮箱池已有 7 个邮件源 | `api/email_pool.py` 头部注释 | DIRECT | 5/5 |
| 主项目已有测试 9 个失败（P0-4 部分修复） | `plan/下一步改进指南.md` 附录 | INFERENCE | 4/5 — 需运行验证 |
| 主项目已有完整 chat 网关 | `api/routes/chat.py`, `api/providers/tryingopen.py`, `api/chat_usage.py` | DIRECT | 5/5 |

---

## Decisions and Assumptions

### 已确认事实

1. 主项目 v5.1.0 是一个功能完整的生产级 AI 网关，生图 + 文本对话双链路均已闭环
2. 版本号已从 4 处不一致统一为 5.1.0（P0-1 已部分修复）
3. playwright-core 已添加到前端依赖（P0-2 已部分修复）
4. test_priority_queue.py 的桩已修复（P0-4 已部分修复）
5. minimaxh3/kookeey 死代码已清理（P1-1 已完成）
6. 参考项目 ohmycaptcha 和 cloudflare_temp_email 有高价值参考点

### 当前假设

1. 用户已确认 `plan/下一步改进指南.md` 中的分析结论
2. 用户未对路线图优先级做出新的指示
3. Python 生态中可以通过绑定或重新实现来利用 Rust WASM 邮件解析的思路

### 借鉴定夺（2026-08-27 二次核对，修正初版高估）

| 借鉴方向 | 来源 | 定夺 | 证据 |
|---------|------|------|------|
| Playwright Turnstile 交互 | ohmycaptcha | ❌ 主项目已有 | cf_solver 用 Boterdrop-Solver + Camoufox，能力更强（/turnstile + /clearance + /aws-token） |
| 求解器注册模式 | ohmycaptcha | ⚠️ 真实缺口但 YAGNI | 主项目仅 1 种求解器，抽象化无收益；未来接多种求解器再考虑 |
| 邮箱源优先级管理 | cloudflare_temp_email | ❌ 主项目已有 | email_pool.py 已有 priority/score/cooldown 7 源体系，设计等价 |
| AI 验证码/链接提取 | cloudflare_temp_email | ✅ 唯一真实缺口，可落地 | registerer.py 仅正则提取（6位数字 / 固定 verify-email 路径），AI 兜底可提升成功率 |

**落地缺口**：`api/mail_extract.py` 新增 AI 兜底提取，默认开关关闭（IF_MAIL_AI_EXTRACT=0），正则失败才降级 AI；适配主项目 TryingOpen 模型通道；失败严格返回 None 不阻塞注册。

### 架构决策（Phase A 阶段，非实施）

1. 主项目当前架构不应被推翻重写，应渐进改造
2. 参考项目的设计思想应适配到主项目的 Python + FastAPI 生态
3. 唯一真实借鉴缺口 = AI 邮件验证码/链接提取（默认关闭）

---

## Risks and Blockers

| 风险 | 等级 | 触发条件 | 影响范围 | 缓解方式 | 是否需要用户确认 |
|------|------|---------|---------|---------|----------------|
| 测试基线仍有 9 个失败 | HIGH | 从 `下一步改进指南.md` 推断 | 回归门禁失灵 | P0-4 已开始修复，需验证完成 | 需确认修复优先级 |
| start.ps1 找不到 cf_solver | MEDIUM | 干净环境启动 | 一键启动失败 | P0-3 修复计划已制定 | 低 |
| 僵尸 pytest 进程持 SQLite 锁 | MEDIUM | 运行全量测试 | 测试执行慢/阻塞 | 用户确认后清理 | 需确认 |
| 当前无阻塞项 | 无 | — | — | — | — |

---

## Implementation Batches

当前无实施批次（Phase A 未授权修改代码）。

---

## Validation Matrix

| Requirement | Validation Method | Actual Command/Action | Result | Evidence |
|-------------|-------------------|----------------------|--------|----------|
| 主项目版本号检查 | 读取文件 | `grep -n version` 4 文件 | 一致 5.1.0 | 文件内容 |
| 参考项目扫描 | 递归目录检查 | `Get-ChildItem` | 3 个项目 + 2 文本文件 | 目录列表 |
| 参考项目分类 | 按评分维度打分 | 文件内容分析 | 2 高价值 + 1 无关 + 2 无效 | 评分表 |
| 未提交改动检查 | git diff | `git status`, `git diff --stat` | 仅 graft 缓存 + 部分 P0 修复 | diff 输出 |
| 死代码检查 | grep 搜索 | `grep -rln "minimaxh3\|kookeey"` | 0 命中 | 命令输出 |

---

## Review Findings

Phase A 阶段无代码审查（无代码修改）。

---

## Next Gate

**下一步动作**：等待用户确认 Phase A 报告中的实施范围。

**是否需要用户批准**：是。具体需要批准的决策：
1. P0 修复批次（P0-1 已部分完成，P0-2/3/4 需要完成）
2. P1 清理批次（P1-1 已完成，P1-2 需确认）
3. P2 工程化批次（前端测试、CI markers、契约审计）
4. P3 产品化批次（按需）

**每个批次的大致影响范围**：见下文 Phase A 报告第 8 节「实施授权状态」。