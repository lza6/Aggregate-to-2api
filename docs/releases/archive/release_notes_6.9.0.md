# 听风AI v6.9.0 发布说明

## 概述

v6.9.0 是**生产级终审 + 全链路质量闭环**版本。基于 v6.8.1 已上线基线，本版系统性落地 P0/P1/P2/P3 四档问题共 20 余项，覆盖：单测污染闭环、CI 防漂移、async 阻塞检测、config 与 env 对齐、worker 终态唯一化、前端统一错误处理、错误边界、画廊签名刷新、虚拟滚动、慢日志面板、成本告警、安全头、路由可观测，全部经独立 Critic 审查 + 真实浏览器 E2E 验证。**向后兼容，无破坏性变更，不改变现有 API 契约。**

## 后端

### P0（阻塞修复）
- **P0-1 单测跨文件单例污染清零**：`test_providers` 12 个 `AttributeError` 根因（registry 旧实例无 engine）由 `monkeypatch.setattr(..., raising=False)` 兜底；3 个真 FAILED（chat 用量记录/metrics/UI 断言）逐一修复。全量 1200+ 用例 ERROR=0。
- **P0-2 landing 版本注入防漂移**：CI 新增 `frontend-version-gate` 强制构建 landing + 跑版本一致性契约；deploy job 构建后断言 dist 含源码版本，漂移即阻断上线。
- **P0-3 async 内同步 sqlite3 零污染**：新增 AST 静态契约 + 运行时行为回归测试（`test_async_sync_contamination.py`），account_pool/email_pool/nanobanana 全部 `asyncio.to_thread` 包裹，事件循环不被文件锁阻塞。

### P1（高优先）
- **P1-1 config 重复声明 + env 漂移**：删 `IF_USD_PER_CREDIT`/`IF_COST_BUDGET_USD` 重复声明；config 字段 158 / env.example 158 **双向 0 漂移**；删孤儿 `IF_MINIMAXH3_ACCOUNT_TARGET` 等死变量；4 个 `IF_TRYINGOPEN_*` 迁入 config 模型。
- **P1-2 settings_json 暴露 security**：`SecuritySettings.to_env()` 输出 env 风格大写键（`IP_WHITELIST`/`TRUSTED_PROXIES`/`AUTO_BLOCK_*`），/v1/meta 运维可读。
- **P1-3 worker 批量终态唯一化**：`_process` 改受控返回码（completed/error/None），done/异常分支先 `db.get` 查终态不覆盖；单 worker 硬超时路径补终态护栏（C1）。
- **P1-4 前端统一错误处理**：`apiFetch<T>` + `ApiError`（status/code/message），20 个函数薄封装，统一超时/取消。
- **P1-5 前端错误边界**：`ErrorBoundary` 根 + 嵌套，单页崩溃不白屏，上报 `FE.BOUNDARY`。

### P2/P3
- **P3-3 安全头**：`SecurityHeadersMiddleware` 注入 X-Content-Type-Options/X-Frame-Options/Referrer-Policy/HSTS；双开关 `IF_SECURITY_HEADERS_ENABLED`（默认 true）/`IF_CSP_ENABLED`（默认 false），默认零破坏。
- **P3-1 路由可观测/可恢复**：`RoutingRecordStore` 独立 sqlite 持久化（`IF_ROUTING_DB`），`restore()`/`_warm_from_store()` 冷启动 EWMA warm，`/v1/routing/records?from_ts=` 历史查询。
- **P1-3 热路径 R1**：路由持久化写经 `asyncio.to_thread` 线程池，不阻塞事件循环。

## 前端

- **api.ts**：`apiFetch` 统一错误 + `ApiError` + 超时/取消 + 200 空 body 容错。
- **useApi**：查询防抖（debounceMs）+ AbortController 取消 + 响应序号竞态防护（后发先至丢弃）。
- **ErrorBoundary**：根 + 嵌套错误边界。
- **Slow.tsx**：慢请求画像 React 面板（queue/wait_token/solve/upstream/retry/submit/poll 七段）。
- **Gallery.tsx**：exp 解析 + 到期前 5s 重签 + `<img onError>` 静默重拉（C2 修复：单坏图不再误触密码重置）。
- **useVirtualList**：Account/Logs 虚拟滚动（无第三方依赖）。
- **Costs.tsx**：超支预警横幅 + 累积 vs 预算瀑布图。
- **ProxyPoolGeo.tsx**：国家 emoji 分布 + 延迟分档健康热力图。
- **Layout/Dashboard**：`/slow` 侧栏 + 慢请求 StatCard。
- **Accounts.tsx**：修复 hook 顺序致 React #310（真实 E2E 发现）。

## 测试

- 后端新增：`test_async_sync_contamination` / `test_worker_batch` / `test_security_headers` / `test_config_validate` 扩展。
- 前端新增：`Gallery.test` / `ProxyPoolGeo.test` / `ErrorBoundary.render.test` / `Slow.test` / `api.test` / `useApi.test`。
- **全量后端单测**：1200+ 用例 EXIT=0，无 `Event loop is closed`、无 `PytestUnhandledThreadExceptionWarning`。
- **前端**：175 tests 全绿 + `npm run build` 通过。
- **真实 E2E**（Playwright 浏览器点击）：`e2e-smoke` 13/13 全绿（首屏/画廊/懒加载路由/DLQ/Toast/无 JS 错误）。
- **独立 Critic**：C1（硬超时覆盖终态）/C2（Gallery 坏图误触密码）/R1/R2/S1-S3 全部修复 + 复验。

## CI 加固

- `ci.yml`：新增 `frontend-version-gate`（构建 landing + 版本契约）。
- `deploy.yml`：build 后断言 dist 版本一致，漂移退出 1 阻断上线。

## 已知限制 / 剩余风险

- `test_worker_hard_timeout` 依赖真实 asyncio 时序，Windows 下 teardown 需 `db.close()`（已修复）；全量在干净环境复跑绿。
- `IF_ROUTING_DB` 默认空（关闭持久化）；生产如需开启设 `IF_ROUTING_DB=data/routing.db`。
- `IF_CSP_ENABLED` 默认 false，生产开启前需确认画廊图源域名加入 `img-src`。
- 生产 CORS 建议收紧为固定域名（见 env.example 说明），当前默认 `*` 向后兼容。

## 部署

- 版本：pyproject / landing / frontend / api.main 四处统一 6.9.0。
- CI 自动构建推送 GHCR 镜像 + SSH 热更新（docker compose up -d api）。
