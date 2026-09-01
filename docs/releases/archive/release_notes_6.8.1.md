# 听风AI v6.8.1 发布说明

## 概述

v6.8.1 是 v6.8.0 上线后的**稳定收尾 + 增量增强**版本：把前序会话遗留的未提交改动（后端增强、前端成本页、测试补齐、CI 加固）整理为可追溯的分组提交，并修复 CI lint 红（ruff 版本漂移）。**无破坏性变更，全部向后兼容。**

## 后端增强

- **P2-3 告警 webhook 外发**（`alerting.py`）：企业微信/钉钉/Slack 通用 JSON POST（`msgtype/text/alerts/source` 结构），`IF_ALERT_WEBHOOK_URL` 为空时不触发任何网络请求。
- **P3-2 DB 每日分批保留巡检**（`bg_tasks.py` + `db/core.py`）：`_retention_loop` 每日本地 04:00 触发 `cleanup_batched`（5000/批 DELETE + VACUUM ANALYZE），避免大表一次性清理阻塞。
- **M6-F3 成本可视化后端**（`chat_usage.py` + `routes/admin.py`）：`/v1/cost` 返回月度趋势、按提供商/模型成本、预算燃烧率、图片积分折算。
- **任务类型编目**（`routes/tasks.py`）：任务列表透出 `task_type`（txt/img2img/txt2vid/img2vid）与 `provider`，运维排查可区分 imagefree 主路径与非 imagefree 后台直调路径。
- **worker 批量回收终态唯一化**（`worker/engine.py`）：修复 `_worker_batch_loop` 对 done/pending 分支的重复标记竞态，任务终态只落一次。
- **统一响应契约 + None 容错**（`routes/chat.py|ecosystem.py|health.py|security.py`）：错误信封 `{error:{code,message,details}}` 全覆盖，mail.tm/ecosystem 上游 None 返回优雅降级。
- **双缓冲 token 池 + 空闲回收**（`worker/token_pool.py`）：Active/Standby 双缓冲零延迟取用，per-proxy 池空闲超 TTL 自动回收。

## 前端增强

- **成本可视化页**（`pages/Costs.tsx`）：预算/燃烧率/按提供商/月度趋势四卡 + 懒加载 recharts，主包不静态携带图表依赖。
- **统一错误处理**（`api.ts`）：`fetchCost` 等新端点接入，401/422/500 结构化错误对象。
- **E2E 真实路径**（`e2e-p3.cjs`）：Playwright-core 覆盖画廊签名 URL 过期 403 + DLQ 重试点击流。

## 测试补齐

- `test_alerting_webhook.py`（5 用例）：webhook payload 结构 / 空 URL 不触发 / 格式化文本 / evaluate 调度。
- `test_db_retention.py`（9 用例）：`_seconds_until_next_0400` 边界（凌晨/午后/跨天/整点）+ `cleanup_batched` 分批复删 + 无超期 no-op。
- 既有测试适配新行为（account_pool/adaptive_router/persistent_queue/worker_auto_scale/priority_queue/request_guard_layers）。

## CI 加固

- **pytest-timeout 兜底**（`ci.yml`）：单测与集成测试均加 `--timeout=120 --timeout-method=thread`，防真实网络类用例卡死 CI。
- **ruff 版本锁定**（`ci.yml`）：CI 固定 `ruff==0.14.9` 与本地一致。根因：`pip install ruff` 拉最新 0.15.x，默认规则集变更引入 BLE001/SIM102 等 438 处噪声致 lint 红；锁定后与 `pyproject target-version=py311` 口径对齐，全绿。

## 工程清理

- `.gitignore`：忽略 `.mypy_cache/`、`.ruff_cache/`、`graft/.cache/`、`uv.lock`（可再生成产物）。
- `scripts/` + `deploy/cf_solver/`：lint 修复（E402 导入注解、f-string 无占位符、未用 import 清理）。
- 版本号统一 6.8.1（pyproject / main.py / package.json / package-lock / README / compose）。

## 验证

- 本地 `ruff check api/ scripts/ deploy/cf_solver/`（0.14.9）：All checks passed。
- 前端 `vitest`：138/138 通过；`npm run build` 成功（主包 70.9KB gzip）；`landing` build 成功。
- CI（Linux）：单测 + 集成 + 覆盖率门禁 70% + Docker 构建验证。
- 线上 E2E：healthz / meta / 首页 / /admin 真实路径。

## 剩余风险（下一轮 v7.0）

- 同步 sqlite3 混入 async（account_pool/email_pool）→ aiosqlite 迁移专项。
- 大文件拆分（email_pool/config/db.core）。
- 详见 `docs/planning/下一步改进指南.md`。
