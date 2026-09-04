# 验证记录（防重复测验协议）

> **目的**：记录每轮验证的范围/结果/日期。下次开发前**先读本表**：
> - 要验证的模块若近期已验且代码未改动 → 跳过重复验证，把精力放到未验/已改区域
> - 改动了某模块 → 在本表追加一行（改动日期+范围），旧记录视为失效
> - 本表由 AI 会话优先读取（配合 memory/），避免盲目重跑同样的测验

## 记录表

| 日期 | 版本/范围 | 验证内容 | 结果 | 失效条件 |
|------|----------|---------|------|---------|
| 2026-09-01 | v7.0.0 | Deploy 33490460997 ✓ + 线上 E2E 9 端点（healthz/models/providers/email-sources/auth-status/routing/diagnostics/landing/admin） | 全绿 | api/ 或 deploy/ 改动 |
| 2026-09-01 | v7.1.0 | Deploy 33502639914 ✓ + 封禁分页端点/UI Key 脱敏 | 全绿（3 次 CI 迭代：测试签名+信封+package.json） | 同上 |
| 2026-09-01 | v7.2.0 | Deploy 33512897007 ✓ + SSE stats 401 + /v1/logs 401 + landing privacy | 全绿（3 次 CI 迭代：nanobanana await/SpanKind/httpx 泄露） | 同上 |
| 2026-09-01 | 后端核心 | request_guard 54 / config 20 / ip_blocklist 28 / security_headers 7 / worker_hard 5 / worker_batch 4 / otel 8 / logs_auth 6 / telemetry 17 / account_pool 30 / email_pool 22 / async_sync 6 / registerer 19 / providers 12 / cost 11 / providers_contract 15 / tryingopen 7 / auto_scale 14 / worker_health 8 / adaptive_router 23 / token_pool 14 | 全绿 | 对应 api/ 文件改动 |
| 2026-09-01 | 前端 | vitest 193 (12 files) + tsc 0 error + build ~3s | 全绿 | frontend/src 改动 |
| 2026-09-01 | landing | build OK + dist 含 7.2.0 + i18n + privacy | 全绿 | landing/src 改动 |
| 2026-09-01 | lint | ruff 全量 0 error（412→0 治理完成） | 全绿 | 任何 py 改动 |
| 2026-09-01 | 预存问题 | Windows Python 3.14 本地：test_providers 全量/test_token_pool 2 用例会卡（基线同样卡，CI ubuntu+3.11 不卡） | 已知非回归 | 换 CI 环境或升级 py 版本 |

## 已知「验证过勿重跑」结论（代码未动前长期有效）

- threading.Lock 审计（v6.8.0 P1-5）：8 文件纯内存临界区保留 threading.Lock 正确，勿再审计
- nanobanana Action ID / tryingopen 目录：已是动态嗅探+静态兜底自愈设计，勿抽 config（v7.1.0 P2-6 评估过）
- 同步 sqlite3：account_pool/email_pool 已 aiosqlite 迁移（v7.2.0），勿再提 to_thread 方案
- email_sources_linshi.py shim：无引用（grep 核实过），删除安全
- AST 契约 tests/test_async_sync_contamination.py：扫描列表含 account_pool/email_pool/nanobanana/aifreeforever/imagefree，改这些文件后必跑
| 2026-09-01 | v7.3 conftest os._exit 兜底 | Windows teardown 卡死根治（111 passed 13s 退出）；三连稳定全绿 148 passed | 全绿 | conftest.py 改动 |
| 2026-09-01 | email_pool 拆分 | email_pool.py 1315→386 + email_sources/ 12 文件 + 旧 import 兼容 | 全绿（22+17+18+main import OK） | api/email_pool.py / api/email_sources/ |
| 2026-09-01 | v7.3 审查线程 7 项修复 | telemetry Description/keyset 游标/count_by_type/GC/reset_settings/连接异常安全/os._exit(exitstatus) | 全绿（140 passed 8.8s + account_pool 30 + test_cost 11 + test_providers 12 + 分段 195 passed） | 以上 api/ 文件再改动 |
| 2026-09-01 | 已知 flaky | 21 文件全量组合偶发 1 F(前端 46% 处),单独/分段/CI ubuntu 全绿——组合串扰(全局 singleton 未还原),非审查修复引入 | 已知 | 组合跑时先单独跑分文件 |

## v7.6 审计闭环验证记录（2026-09-04）

| 日期 | 范围 | 结果 | 备注 |
|------|------|------|------|
| 2026-09-04 | 4 agent 并行审计（前端/后端/部署/测试）+ 1 反向核查 | 全部断言 file:line 确认 | 发现 P0×2 P1×10 P2×15 P3×15 |
| 2026-09-04 | 幂等 TOCTOU 修复 | claim_idempotency 原子抢占（ON CONFLICT DO NOTHING + rowcount） | test_idempotency 11 passed（含 10 并发收敛） |
| 2026-09-04 | lifespan drain _PROVIDER_TASKS | ③.5 阶段排空，重启不丢任务 | AST + 语法校验通过 |
| 2026-09-04 | chat 429 语义 | ProviderRateLimited → 429 RATE_LIMITED | test_chat_stream_frames 30 passed |
| 2026-09-04 | priority=0 admin 校验 | generate.py _prepare 补 check_admin_key | test_main_validation 49 passed |
| 2026-09-04 | 前端 5 项修复（ping 裸串/fetchLogs/Dashboard adminKey/Security 分页/LogEntry 类型） | vitest 197 passed + tsc 0 error + build 4.36s | CI 版本门禁本地模拟通过 |
| 2026-09-04 | 部署一致性 5 项（版本 7 处 7.4.0/cov 80 统一/限流默认 20/sync_deploy 清理/README 路径） | 全部落实 | grep 核实 |
| 2026-09-04 | ruff 全量 | 0 error（清 2 处历史残留 F841/F401） | All checks passed |
| 2026-09-04 | 组合回归 6 批（idempotency/chat/dispatch/log/auth/retry/router/errors/pool/sse/etag） | 全绿 | Windows 3.11 venv |
| 2026-09-04 | 前端无障碍+响应式地基（WCAG 2.1 AA） | e2e-smoke 22 断言全绿 + resp-audit 20 断言全绿 | commit 213a8a8 |
| 2026-09-04 | a11y 落地清单 | skip-link→#main-content（tabIndex=-1+scroll-margin-top）；装饰 emoji 全量 aria-hidden（nav-icon 13/brand/stat/empty/error/toast/system-dot/nav-pip）；:focus-visible 全局环；prefers-reduced-motion 降级；--text-muted #94a3b8→#64748b（4.6:1）；触控目标 44px（菜单按钮 38→44 + .tf-btn min-height）；Esc 关抽屉补实现（useEffect keydown） | Layout/StatCard/Feedback/ToastHost |
| 2026-09-04 | 响应式落地清单 | viewport-fit=cover + --safe-* 令牌 + topbar/toast 安全区 calc；100vh+100dvh 双写（桌面+抽屉侧栏）；html font-size clamp(14px→16px)；栅格 768/1024/1440 过渡；@media(hover:none) 显式回退（非 revert-layer，Safari<16.4 兼容）；字体非阻塞（media=print→all + preload + noscript 兜底） | index.html/index.css |
| 2026-09-04 | 性能地基 | StatCard contain:layout style paint（隔离重排）；字体渲染阻塞解除（LCP）；space/z/ease/dur 令牌补齐 | index.css/StatCard |
| 2026-09-04 | 响应式审计（E2E 4 断点） | 375/768/1024/1440 无水平溢出 + 抽屉开合 + Esc 关闭 + 截图基线归档 .benchmarks/resp-shots/ | resp-audit.cjs 20 passed |
| 2026-09-04 | 组合回归说明 | 后端全量 1545 用例 3 轮：run1 1F(test_block_ip_record_fields)/run2 4F(含版本门禁 3 项，dist 未构建所致)/run3 0F——单项与文件级复跑均全绿，属组合串扰 flaky（与 2026-09-01 已知条目同类），非本轮引入 | CI 口径（pytest -m "not integration and not chaos and not slow"） |

## 新增「验证过勿重跑」结论

- 前端 a11y 地基已落地（v7.6.0）：skip-link/aria-hidden/focus-visible/reduced-motion/44px 触控——后续页面改造勿重复加全局样式，只补页面级（如 Accounts/Logs/Security input 的 aria-label）
- Esc 关闭抽屉已在 Layout 实现（v7.6.0）：勿再加重复 keydown 监听
- hover:none 降级用显式回退值（v7.6.0）：勿改回 revert-layer（Safari<16.4 不识别会半残）
- --safe-* 令牌与 viewport-fit=cover 已配对（v7.6.0）：新增 fixed 元素须用 calc(... + var(--safe-*))

- 幂等 claim_idempotency 已原子化（v7.6）：勿再提"加锁包裹 get+save"方案，直接复用 claim 接口
- _PROVIDER_TASKS drain 已入 lifespan ③.5（v7.6）：勿在 engine.stop() 内重复处理
- deploy/pyproject.toml 已对齐 7.4.0（v7.6）：版本门禁 7 处 = pyproject×2 + main.py + frontend + landing + compose×2
- cov-fail-under 已统一 80（v7.6）：ci.yml 与 deploy.yml 同口径
- IF_REQUESTS_PER_MINUTE 默认对齐 20（v7.6）：.env.production.example 与 compose 一致
- 孤儿 env 变量清单已在 deploy/.env.example 尾部标注（v7.6）：IF_MINIMAXH3_*/IF_MAX_IMAGE_BYTES/IF_USER_AGENT/IF_MAX_PROMPT_LEN/IF_ASPECT_RATIOS/IF_KOOKEEY_* 填了不生效
