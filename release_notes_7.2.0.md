# 听风AI v7.2.0 发布说明

## 概述

v7.2.0 是**可观测性 + 安全加固 + 剩余风险清零**版本。基于 v7.1.0 已上线基线，本版系统性落地《下一步改进指南.md》P3 全档（P3-2~P3-8）+ 解决 v7.1.0 遗留的全部剩余风险（P2-3 sqlite3 迁移 aiosqlite + api.ts 拆分）：

- **P3-2 OTel tail-based 采样 + SSE 指标看板**（错误请求 100% + 正常 10% 采样 + Dashboard SSE 卡片）
- **P3-3 全局 threading.Lock 改 per-IP 分片锁**（高 RPS 串行瓶颈消除）
- **P3-4 final_suite 本地覆盖率门禁 0→70**（与 CI 对齐）
- **P3-5 ruff 既有 412 errors 治理**（自动 fix + E701 手动多行，全量 0 error）
- **P3-6 ?api_key= 日志脱敏 + /v1/logs 鉴权**（安全收紧）
- **P3-7 landing 多语言（中/英）+ 隐私声明/DPA 页**
- **P3-8 提供商接入指南**（docs/PROVIDER_INTEGRATION_GUIDE.md）
- **P2-3 account_pool/email_pool sqlite3→aiosqlite 迁移**（消除事件循环阻塞隐患，解决 v7.1.0 遗留风险）
- **api.ts 857 行→barrel 拆分**（解决 v7.1.0 遗留路径歧义，index.ts 10 行 + 6 子文件）

**向后兼容，无破坏性变更，不改变现有 API 契约。**

---

## P3-2 OTel tail-based 采样 + SSE 指标看板

### 实现
- `api/telemetry.py`：新增 `TailBasedErrorSampler`（错误请求 status>=500/error=true → 100% 采样；正常请求 → `TraceIdRatioBased` 按比例）
- `api/config/__init__.py`：新增 `OTEL_SAMPLE_RATE`(默认 0.1)、`OTEL_ERROR_SAMPLE_RATE`(默认 1.0)
- `api/sse_stats.py`（新建）：`SseStats` 采集器（事件总量/按类型分桶/补偿率/取消率/任务数/每任务平均）
- `api/sse_events.py`：publish/retry/subscription/cancellation 调 sse_stats 计数（失败静默不破主链路）
- `api/routes/admin.py`：新增 `/v1/sse/stats` 端点（admin key 鉴权）
- `frontend/src/pages/Dashboard.tsx`：新增"SSE 事件流指标"卡片（6 指标格 + 按类型 chip + 15s 轮询）

### 验证
- `tests/test_otel_sampling.py`（新建）8 用例 → **8 passed**
- ruff + 前端 tsc/vitest/build 全绿

---

## P3-3 全局 threading.Lock 改 per-IP 分片锁

### 实现
- `api/request_guard.py`：全局 `_lock` 拆为：
  - `_cache_lock`：保护 `_BLOCKLIST_CACHE` + `_LAST_CACHE_SYNC`（共享状态）
  - `_ip_locks_guard` + `_ip_locks[ip]`：per-IP 分片锁，保护该 IP 滑窗/令牌桶/违规计数
- 全局过期键清理从每请求扫全表改为 `len>10000` 时降频扫一次（`_cache_lock` 保护跨 IP）
- **行为等价**：per-IP 滑窗逻辑不变，不同 IP 并行（原全局锁串行），同 IP 仍串行

### 验证
- `tests/test_request_guard_layers.py` 新增 per-IP 分片锁隔离测试 → **54 passed**

---

## P3-4 final_suite 本地覆盖率门禁

- `scripts/final_suite.py`：`--cov-fail-under=0` → `--cov-fail-under=70`（与 CI 一致）

---

## P3-5 ruff 既有 errors 治理

- `ruff check --fix` 自动修复 F401（unused import）+ E401（multiple imports）
- `tests/test_worker_hard_timeout.py` E701 手动多行（10 处 `try: await db.close()` 单行改多行）
- `api/telemetry.py` 删除未用 `ALWAYS_OFF`/`ALWAYS_ON` import
- `api/email_pool.py` 删除未用 `sqlite3`/`threading` import（P2-3 迁移后）
- **全量 ruff：All checks passed!**（从 412 errors → 0）

---

## P3-6 ?api_key= 日志脱敏 + /v1/logs 鉴权

### 实现
- `api/auth.py`：`?api_key=` query 传 Key 记 warning（提示弱安全通道）+ 新增 `mask_key()` 脱敏工具
- `api/context.py`：访问日志只记 path（不含 query），防 `?api_key=xxx` 落入 log_buffer 历史
- `api/routes/admin.py`：`/v1/logs` + `/v1/logs/ws` 加 `check_admin_key` 鉴权（开放模式向后兼容）

### 验证
- `tests/test_logs_admin_auth.py`（新建）6 用例 → **6 passed**

---

## P3-7 landing 多语言 + 隐私声明/DPA

### 实现
- `landing/src/composables/useI18n.js`（新建，282 行）：轻量 i18n（`ref(locale)` + zh/en 字典），URL `?lang=` > localStorage > 浏览器语言 > 默认 zh，不引 vue-i18n
- `landing/src/components/Privacy.vue`（新建）：中/英双语隐私声明/DPA（6 节），hash 路由 `#/privacy`
- `landing/src/App.vue`（重写）：i18n 接入 + hash 路由 + 语言切换按钮 + footer 隐私链接
- 7 个 Section 组件全部 i18n 接入（硬编码文案抽到 `t(key)`）

### 验证
- `cd landing && npm run build` → ✓ built in 801ms
- dist 含多语言文案 + privacy 路由

---

## P3-8 提供商接入指南

- `docs/PROVIDER_INTEGRATION_GUIDE.md`（新建，327 行）：Provider 抽象/必需方法/健康检查/credits/路由注册/降级 select_best MAB/契约测试/IF_ 配置/imagefree vs nanobanana 对比/接入 Checklist

---

## P2-3 account_pool/email_pool sqlite3→aiosqlite（解决 v7.1.0 遗留风险）

### 实现
- `api/account_pool.py`：sqlite3+threading.Lock → aiosqlite+asyncio.Lock，所有 DB 方法改 async，删除 to_thread 包装
- `api/email_pool.py`：同上，9 个 Source 类迁移
- `api/registerer.py` + `api/providers/nanobanana.py`：调用链 async 化（await account_pool.xxx）
- `tests/test_email_pool.py`：同步调用 `pool.record()`/`registered_providers()`/`stats()` 改 `await`（P2-3 后这些方法已 async）
- `tests/test_email_pool.py`：`pool._conn.execute` 同步访问改 `async with pool._lock: await conn.execute`

### 验证
- `test_email_pool` **22 passed**（50s，aiosqlite 慢于同步但非阻塞）
- `test_account_pool` **30 passed**
- `test_async_sync_contamination` **6 passed**（AST 契约绿，async 方法无同步 sqlite3 调用）
- `test_registerer` + `test_registerer_adaptive` **19 passed**

---

## api.ts barrel 拆分（解决 v7.1.0 遗留路径歧义）

### 实现
- `frontend/src/api.ts`（857 行）→ `frontend/src/api/` 子目录（barrel 模式，解决路径歧义）：
  - `index.ts`（10 行）：barrel 聚合 re-export
  - `core.ts`（199 行）：apiFetch/ApiError/Key 存储/authHeaders/adminHeaders
  - `providers.ts`（120 行）/ `tasks.ts`（59 行）/ `chat.ts`（111 行）/ `security.ts`（61 行）/ `misc.ts`（341 行）
- **路径歧义解决**：`./api` 唯一解析到 `api/index.ts`（Node/Vite 默认目录有 index 优先）
- **向后兼容**：33 处 `from '../api'` import 零改动

### 验证
- `npx tsc --noEmit` → 0 error
- `npx vitest run` → 193 passed (12 files)
- `npm run build` → ✓ built in 3.00s
- 各子文件 < 400 行，index.ts 10 行

---

## 测试

- 后端核心套件全绿：
  - test_otel_sampling **8** / test_logs_admin_auth **6** / test_request_guard_layers **54** / test_config_validate **20** / test_worker_hard_timeout **5** / test_worker_batch **4** / test_ip_blocklist **28** / test_security_headers **7** / test_email_pool **22** / test_account_pool **30** / test_async_sync_contamination **6** / test_registerer+adaptive **19**
- 前端：`npx vitest run` → 193 passed (12 files) + `npm run build` ✓ + `npx tsc --noEmit` 0 error
- landing build → ✓ built in 801ms
- 全量 ruff → All checks passed!（412 errors → 0）

## 已知限制 / 剩余风险

- **预存卡死用例**：`TestMainObservability::test_healthz_has_solver_fields` / `test_metrics_keeps_legacy_lines` 在 Windows Python 3.14 本地卡死（预存，非本版引入），CI ubuntu+3.11 不受影响。
- **email_pool 测试 50s**：aiosqlite 慢于同步 sqlite3（线程池开销），但非阻塞事件循环（P2-3 目标达成）。
- **未 commit/push/部署**：所有改动留工作区，需用户授权后 commit + 发版 + 部署。

## 部署

- P3-2/P3-3/P3-6/P2-3 代码改动随镜像构建生效。
- P3-4 final_suite 本地门禁（开发机用，不影响生产）。
- P3-7 landing 多语言 + privacy 随 landing dist 挂载生效。
