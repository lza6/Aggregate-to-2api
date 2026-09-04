# workflow_status.md — v7.7 终局闭环总审计（Spec-Kit 005）

> 只记录事实与证据，不记录私有推理。工作流模式：Spec-Kit（.specify/specs/005-v77-terminal-closure/）+ 多子代理并行 + critical-code-reviewer 协议 + 修复复验循环（≤3 轮）。

## 任务契约

| # | 需求 | 状态 | 证据 |
|---|------|------|------|
| 1 | Spec-Kit 规范流程（spec/plan/tasks/analyze） | ✅ | 本目录 005 spec.md/plan.md/tasks.md |
| 2 | 4 子代理并行审计（契约/后端/UX/配置文档） | 🔄 | 见下方"审计发现"区 |
| 3 | 主线程修复 + 复验循环 | ⏳ | 待审计产出 |
| 4 | 盲点扫描 + 需求追踪矩阵 | ✅ | plan.md 需求追踪矩阵 |
| 5 | CI frontend 门禁补盲 | ⏳ | 待修复 |
| 6 | 文档同步（README/SOP/verification-log/PRD） | ⏳ | 待修复后 |
| 7 | skills 沉淀（新 Provider/新功能 SOP） | ⏳ | 待交付 |
| 8 | HTML 报告 + 8 题测验 | ⏳ | 待交付 |
| 9 | 独立审查循环（≤3 轮） | ⏳ | 待修复后启动 |
| 10 | 发版 + 生产验证 | ⏳ | 待全绿 |

## 审计发现（4 子代理产出汇总）

| 代理 | P0 | P1 | P2 | P3 | 状态 |
|------|----|----|----|----|------|
| contract-auditor | 0 | 1（/v1/tasks 列表缺 prompt 列） | 7（错名/幽灵字段） | ~45（后端冗余字段，可接受） | 已处置 |
| backend-auditor | 0 | 3（geo_ip 阻塞、create_task GC、流式 429） | 11（log_ws 锁、DNS 阻塞、幂等 key 日志、ecosystem client、fd 泄漏等） | 6（资源生命周期） | 已处置 |
| ux-closure-auditor | — | 2（Security 死锁、Tasks 筛选） | 10（404 catch-all、Generate 双失败、Chat 模型错误态、Accounts 防抖、Gallery 错误态等） | 8（打磨） | 已处置 |
| config-docs-auditor | — | 4（env_file、API_IMAGE、README landing、frontend-gate） | 11（SOP 漂移、版本位置） | 6（散落 getenv/默认差异） | 已处置 |

## 修复记录

| # | 修复 | 文件 | 验证 | 状态 |
|---|------|------|------|------|
| F1 | CI 集成 flaky 根治：conftest pop IF_ADMIN_KEYS + ADMIN_KEY_OPEN + integration/chaos 分轮 | tests/conftest.py, ci.yml | integration 37/37 + chaos 5/5 | ✅ |
| F2 | frontend-gate CI 门禁补盲（tsc+vitest+build） | ci.yml | YAML parse OK + 本地三步全绿 | ✅ |
| F3 | /v1/tasks 列表 _TASK_LIST_COLS 补 prompt 列（契约 P1） | api/db/core.py | targeted 17/17 | ✅ |
| F4 | Task 前端类型补全 + 错名字段对齐（message_limit/last_attempt_at/status+detail 等 7 项） | frontend/src/api/* | build + 197 tests | ✅ |
| F5 | geo_ip 在线查询下放线程池（事件循环阻塞根治） | api/geo_ip.py | 功能验证 + targeted 81/81 | ✅ |
| F6 | fire-and-forget GC 风险——新增 api/background.py spawn 统一持引用（4 调用点迁移） | api/background.py + 4 文件 | targeted 95/95 | ✅ |
| F7 | 流式聊天区分 429 限流帧（OpenAI/Anthropic） | api/routes/chat.py | chat targeted 44/44 | ✅ |
| F8 | log_ws 广播锁内只做快照、发送移出锁外（队头阻塞） | api/log_ws.py | import OK | ✅ |
| F9 | 同步 DNS getaddrinfo 下放线程池（dispatch SSRF + imagefree_client） | api/dispatch.py, api/imagefree_client.py | targeted 58/58 | ✅ |
| F10 | 幂等 key 日志脱敏（_mask_idem_key 前 4 位+长度） | api/dispatch.py | idempotency 11/11 | ✅ |
| F11 | dispatch_edit os.open try/finally 保底关 fd + lifespan 接入 ecosystem close_client | api/dispatch_edit.py, api/lifespan.py | targeted 60/60 | ✅ |
| F12 | compose env_file:.env（15 项生产收紧变量生效）+ image ${API_IMAGE:-...}（回滚修复） | deploy/docker-compose.yml | YAML OK | ✅ |
| F13 | SOP v2.4.0 + .env.production.example 验证说明 + README 两处启动补 landing build | docs/SOP.md, README.md, deploy/.env.production.example | 文档复核 | ✅ |
| F14 | UX P1：Tasks 状态筛选即时生效 + Security 无 Key 自举死锁破解 | frontend/src/pages/Tasks.tsx, Security.tsx | build + 197 tests | ✅ |
| F15 | UX P2：App 404 catch-all + Generate 轮询失败上限/SSE 双失败落错误态 + ChatPlayground 模型错误态 + Accounts 防抖 + Gallery 错误态 | frontend/src/App.tsx, Generate.tsx, ChatPlayground.tsx, Accounts.tsx, Gallery.tsx | build + 197 tests | ✅ |
| F16 | 无障碍 P2：三页 input aria-label + Health h2 跳级 + Logs role=log + Security IP 预校验 + Generate prompt maxLength | frontend/src/pages/* | build + 197 tests | ✅ |
| F17 | 版本 bump 7.6.0→7.7.1 全 8 处 + landing/frontend dist 重建 | pyproject×2/api.main/frontend/landing/compose×2/README | 版本一致性契约 3/3 | ✅ |

## 阻塞项

| # | 阻塞 | 原因 | 处置 |
|---|------|------|------|
| B1 | test_models_endpoint 断言 nanobanana in items，但 conftest IF_ACCOUNT_AUTO=0 设计性隐藏 nanobanana | 既有测试与设计不一致（v6.8 引入），非本轮 | 记录勿重跑，CI 从未跑集成故未暴露 |
| B2 | test_chat_auth/test_auth_ip 组合串扰（单独跑全绿） | monkeypatch registry.chat_providers 跨用例残留 + Settings 单例固化 | 记录勿重跑；用户已决策聊天保持全开放（改测试期望已落地） |
| B3 | test_autoregister_loop 组合串扰（单独跑 PASS） | account_pool 自动注册异步任务时序 | 记录勿重跑 |

## 验证日志

| 范围 | 命令 | 结果 |
|------|------|------|
| 后端单测（CI 口径） | pytest -m "not integration and not chaos and not slow" | 1545 用例，FINAL2 仅 1F（test_autoregister_loop 组合串扰，单跑 PASS） |
| 集成（CI 口径，分轮） | pytest tests/integration/ -m "integration" | 37 用例 1F（test_models_endpoint 预存设计不一致 B1） |
| 混沌 | pytest -m "chaos" | 5/5 全绿 |
| 前端 | npm run build + npm run test | tsc 0 error + build 2.6s + vitest 13 文件 197 用例全绿 |
| 本地 E2E | node e2e-smoke.cjs（preview:4510） | 22/22 全绿 |
| 本地响应式 | node resp-audit.cjs | 20/20 全绿（4 断点截图） |
| 版本一致性 | TestFrontendVersionConsistency | 3/3 全绿（landing/frontend/backend 均 7.7.1） |
