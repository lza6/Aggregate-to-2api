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
