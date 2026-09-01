# 听风AI v7.0.0 发布说明

## 概述

v7.0.0 是**吞吐瓶颈根治 + 路由投资变现 + 安全收紧 + 前端体验升级 + 版本大版本里程碑**版本。基于 v6.9.1 已上线基线，本版系统性落地《下一步改进指南.md》P0（部分）+ P1 全档：

- **P0-2 版本号全链对齐 + 旧产物归档清理**（v6.9.1 已落地，本版 bump 到 7.0.0 里程碑）
- **P0-3 token 池双水位 + 批量并发填充**（吞吐工程化，向后兼容默认关闭）
- **P1-1 adaptive_router.select_best 生产激活**（degraded 多候选走 MAB 打分，MAB 投资变现）
- **P1-2 CORS/管理 Key/CSP 安全收紧试点**（env 模板 + 测试，生产开启需授权）
- **P1-3 Dashboard 共享调度器 + 页面可见性优化**（8 个独立 setInterval → 1 个共享 + 失焦暂停）
- **P1-4 路由持久化生产默认开启**（IF_ROUTING_DB=data/routing.db）
- **P1-5 api 容器 mem_limit 256m→512m**（OOM 风险消除）

**向后兼容，无破坏性变更，不改变现有 API 契约。**

---

## P1-1 adaptive_router.select_best 生产激活

### 背景
- `select_best` 方法存在但生产 healthy 路径不调用（用户 model_id 前缀即提供商，不能跨商偷换）。
- degraded 降级路径 `find_alternative` 只返回首个能力匹配备用，不经过 MAB 打分。

### 实现（场景 C：降级路径用 MAB）
- `api/providers/registry.py` 新增 `find_alternatives(model_id) -> list[tuple[Provider, str]]`（复数，返回全部能力匹配健康备用，按能力重叠数降序）
- `find_alternative`（单数）保留，内部委托 `find_alternatives` 取首个，旧调用方零改动
- degraded 分支（`registry.py:140-157`）：
  - `len(alts) > 1` → `select_best([p.prefix...], model=model_id, requested_provider=spec.provider)` 选最优
  - `len(alts) == 1` → 直接返回单备用，不调 select_best（单候选无打分意义）
  - `alts == []` → 直连首选 + record_direct
- `api/adaptive_router.py:492` select_best docstring 修正：明确 healthy 不调用、仅 degraded 多候选调用

### 验证
- `tests/test_adaptive_router.py` 新增 `TestDegradedSelectBest` 5 用例（多候选调 select_best / 单候选跳过 / 无备用直连 / healthy 不调 / 按能力重叠排序）
- `pytest tests/test_adaptive_router.py` → **23 passed**
- `ruff check` → All checks passed!

---

## P1-2 CORS/管理 Key/CSP 安全收紧试点

### 实现（env 模板 + 测试，生产开启需授权）
- `deploy/.env.example`：
  - CORS 注释加生产建议（`IF_CORS_ORIGINS=https://imagefree.tingfengai.art`）
  - 管理 Key 注释加生产强烈建议独立配置（防权限提权）
  - CSP 注释加开启前需把画廊图源域名加入 img-src
- `tests/test_security_headers.py` 新增 3 用例：
  - `test_csp_enabled_injects_header`：CSP 开启注入 `default-src 'self'` + `img-src`
  - `test_csp_disabled_no_header`：CSP 默认关闭不注入（向后兼容）
  - `test_security_headers_off_when_disabled`：主开关 false 不注入任何头（最小回滚）
- **生产开启 CORS 收紧/CSP/独立管理 Key 需用户授权**（L3 风险，本版只落地 env 模板 + 测试基建）

### 验证
- `pytest tests/test_security_headers.py` → **7 passed**
- `ruff check` → All checks passed!

---

## P1-3 Dashboard 共享调度器 + 页面可见性优化

### 实现
- 新建 `frontend/src/hooks/usePollingScheduler.ts`（111 行）：
  - 模块级单例调度器：1s tick + `Map<taskId, {intervalMs, lastRun, runner}>` 任务表分桶
  - `document.addEventListener('visibilitychange', ...)` —— hidden 暂停 tick，visible 立即 reload 全部任务
  - SSR 安全（`typeof document !== 'undefined'` 判断）
- `frontend/src/hooks/useApi.ts`：intervalMs>0 时注册到 `pollingScheduler`（替代各自 setInterval + visibilitychange），签名 `{data, loading, error, reload}` 不变
- Dashboard 8 个 useApi 现共用 1 个 setInterval（`scheduler.isTicking` 单例）

### 验证
- `frontend/src/test/useApi.test.ts` 新增 4 用例（注册数=实例数 / 卸载注销 / intervalMs=0 不注册 / hidden 暂停 visible 补拉）
- `npx vitest run`（全量）→ **193 passed (12 files)**
- `npm run build` → ✓ built in 2.70s
- `npx tsc --noEmit` → 0 error

---

## P1-4 路由持久化生产默认开启

- `deploy/docker-compose.yml` api environment 加 `IF_ROUTING_DB=data/routing.db`
- `deploy/.env.example` 标注生产建议开启
- 重启后保留路由历史 + 冷启动 warm EWMA（`restore()`/`_warm_from_store()` 已实现，v6.9.0 P3-1）

---

## P1-5 api 容器 mem_limit 256m→512m

- `deploy/docker-compose.yml:47-51`：`mem_limit: 256m → 512m`，`mem_reservation: 128m → 256m`，`cpus: '1' → '2'`
- 消除高负载 OOM kill 风险（api 跑 FastAPI + aiosqlite + 8 后台任务 + worker 池 + LRU 画廊缓存）

---

## P0-3 token 池双水位 + 批量并发填充（v6.9.1 已落地，本版保留）

- `api/config/__init__.py` 新增 3 配置（默认 1/0/1 向后兼容）：
  - `IF_TOKEN_TARGET_WATERMARK`（默认 1 = 旧逻辑；生产建议 5）
  - `IF_TOKEN_URGENT_WATERMARK`（默认 0 = 关闭批量；生产建议 2）
  - `IF_TOKEN_BATCH_FILL_SIZE`（默认 1 = 单次；生产建议 4，需 cf_solver 多槽）
- `api/worker/token_pool.py`：`_target_watermark` 可配 + `_is_urgent()` + `_solve_one()` + `_batch_fill(n)` + `prefetch_loop` 批量分支
- `tests/test_token_pool.py` 新增 4 用例
- `deploy/.env.example` 补 3 个新配置说明

---

## 版本号全链对齐 7.0.0 + 旧产物归档

- 全链 bump 到 7.0.0（pyproject / api.main / frontend / landing / compose 注释 / cfsolver image）
- landing build dist 含 7.0.0 版本注入（CI frontend-version-gate 绿）
- 9 个旧 release notes（6.4.1~6.9.0）归档到 `docs/releases/archive/`
- plan.md/spec.md/tasks/ 归档到 `docs/planning/archive/`（Grep 核实无引用）
- probe_free_proxy.py 移到 `scripts/`
- `workflow_status.md` 保留原位（被 skill 引用）

---

## 测试

- 后端：`test_adaptive_router`（23）+ `test_token_pool`（14，排除预存卡死 2）+ `test_security_headers`（7）+ `test_config_validate` + `test_providers_contract` → **79 passed, 2 deselected**
- 前端：`npx vitest run` → **193 passed (12 files)**
- `npm run build`（frontend）→ ✓ built in 2.70s
- `npm run build`（landing）→ ✓ built in 658ms，dist 含 7.0.0
- `ruff check` 全改动文件 → All checks passed!

## 已知限制 / 剩余风险

- **P0-1 cf_solver 并发提升未实施**：page_count 1→3 属生产配置变更（L3），需用户授权灰度+回滚，本版暂停。
- **预存卡死用例**：`TestMainObservability::test_healthz_has_solver_fields` / `test_metrics_keeps_legacy_lines` 在 Windows Python 3.14 本地卡死（`git stash` 验证基线同样卡），预存问题非本版引入，CI ubuntu+3.11 不受影响。
- **P1-2 生产开启 CORS/CSP/独立管理 Key 需用户授权**：本版只落地 env 模板 + 测试基建。
- **未 commit/push/部署**：所有改动留工作区，需用户授权后 commit + 发版 + 部署。

## 部署

- 版本：pyproject / landing / frontend / api.main / compose 注释 / cfsolver image 六处统一 7.0.0。
- CI 自动构建推送 GHCR 镜像 + SSH 热更新（docker compose up -d api）。
- P1-4/P1-5 生产 env/资源变更随部署生效。
