# 听风AI v6.6.0 发布说明

## 号池补满速率监控（P3-4）
- `/v1/account-pool` 新增顶层 `growth` 画像：**今日新增 / 日均新增（7 天） / 距目标还差 / 预计达标天数**。
- `account_pool.growth_stats()`：按 `created_at` 窗口统计 24h/7d 新增与日均，`eta_days = gap / daily_rate`，速率为 0 时返回 `None`（前端显示「—」）。
- React `Accounts.tsx` 新增「📈 号池补满速率」卡片：今日新增、日均新增、距目标还差、预计达标；`eta_days > 30` 时提示调小 `IF_REGISTER_COOLDOWN` 或补代理池；移动端两列栅格。
- 说明：`REGISTER_COOLDOWN=90s` → 约 960/天 → 1 万目标约 10 天；按负载动态调 `IF_REGISTER_COOLDOWN` 可提速（运维即可，本轮提供观测）。

## P3-3 多实例横向扩展评估（只评估不实施）
- **结论：不值得横向扩。** 单实例未饱和（线上 CPU 5%、队列恒 0），真正的吞吐瓶颈是生成通道（Turnstile 求解串行 4.78s/个 + 上游限流），而非 API 入队能力。
- 证据（线上探针 + 本机可复现基准）：单实例 API 通用层实测 **749.59 req/s**（P50=0.36ms / P95=0.54ms），线上峰值 ≈0.12 req/s，有 6000+ 倍裕量；真实出图仅 ~0.84 img/s。
- 多实例扩的是 API 空载，**不增加出图吞吐**（cfsolver 单点）；切 Redis/持久化队列仅为多实例共享队列所需，当前无收益。
- 详细报告：`docs/reports/v6.6.0-scale-evaluation.md`；后续只有当真实出图率逼近 ~0.84 img/s（≈7.3 万张/天）才重新评估。

## 安全加固（P0 first_key 泄露修复）
- `/v1/chat/auth/status` 匿名仅返回脱敏 `key_mask`+`auth_enabled`；携带管理面有效 Key 才附完整 key 供「一键复制」。
- `/v1/meta` 不再返回完整 API Key，仅返回脱敏前缀与鉴权开关。

## 可观测性闭环（Section 16 / 本轮新增）
- **错误码聚合**：新增 `api/error_tracker.py` 线程安全 P0-P1 错误码计数；`/v1/errors/aggregates` 展示 AUTH.001/RATE.001/PROV.001/SYS.001 分布；`/metrics` 增 `imagefree_errors_by_code` 指标；`handlers` 三个异常处理器统一落点。
- **告警扩充**：`alerting.py` 新增 3 条规则 —— 单提供商连续失败 ≥10 次（warning）、IP 批量封禁/限流 ≥20（critical）、AUTH.001 近窗口激增（warning）；`bg_tasks` 评估上下文补齐 `max_consecutive_failures / blocked_ip_count / auth_error_count`。
- **任务全链路日志**：新增 `/v1/tasks/{id}/logs` 聚合「内存日志（按 task_id 过滤）+ 慢日志画像 + per-task SSE 事件回放 + DB 任务终态」，支持一个任务 ID 看全链路（P3）；`sse_events.TaskEventHub.get_task_events()` 供只读回放。

## 验证
- 后端单测：`TestAccountPoolGrowth`(3) + 原 account_pool 19p 全绿；集成 `test_account_growth` 通过。
- 本轮新增 `test_observability_closed_loop.py`(13) 覆盖错误聚合/日志串联/告警规则；security+observability 合计 **59p**。
- 前端 tsc 0 + build exit0；`e2e_full.py` **32/32 PASS**；`e2e_v66_verification.py` **17/17 PASS**（含 SSE 终态、号池 growth/cost_summary、SPA 单源挂载）。
- 版本：pyproject / main.py / frontend / landing / uv.lock / docker-compose 统一 6.6.0。

> 部署：`imagefree-api:6.6.0` / `imagefree-cfsolver:6.6.0`（docker compose 重建）。
