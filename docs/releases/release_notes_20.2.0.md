# v20.2.0 发行说明

> 发布时间：2026-09-26 ｜ 基于 v20.1.0（`f4081c8`）｜ 主题：代理池高并发（单 IP 忙 → 代理换出口）

## 问题

imagefree 免费层对**同一出口 IP 同时只能有 1 个生成任务**。并发提交第 2 个任务时，
上游返回 **HTTP 200 + JSON error**（`You already have a free image task in progress`），
而非 429 状态码。原 `generate_with_429_proxy_fallback` 只认 `"429"` 字符串 → 该错误
直接走永久失败 + DLQ，代理池（1400+ 免费代理）完全没被用上，高并发被单 IP 卡死。

## 修复

- 新增 `_is_upstream_ip_busy()`：识别 `free/editing task in progress` 类错误 =
  当前出口 IP 忙 = 429 等价
- `generate_with_429_proxy_fallback` 入口判定 + fallback 内部 rate_limited 判定同步接入
  → 触发代理池换出口 → 同 IP 重新解 Turnstile token → 走代理提交
- 新增单测：in-progress 识别（5 断言）+ fallback 触发路径（mock 代理池/求解，断言换 IP 重试）
  `test_worker_engine_compat.py` **13/13 全绿**；ruff 0

## 真机 E2E（20.204.27.154 线上，2026-09-26）

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 并发 4 个 imagefree 文生图 | 3 error（DLQ）+ 1 成功 | **4/4 completed，全部真实出图** |
| 代理池 | total=0（未开 IF_FREE_PROXY） | **1404 个免费代理**（已启用） |
| 单任务 | 单 IP 串行 | 多 IP 并发（429/IP 忙 → 代理换出口） |

## 变更

- systemd 部署补 `IF_FREE_PROXY=1` + `IF_FREE_PROXY_REFRESH_MIN=10`（当前跑在 20.204.27.154）
- 版本全链 20.0.0 → 20.2.0（14 文件，React/Node 依赖约束不受影响）
- `scripts/e2e_v12.py` 版本断言 19.0.0 → 20.0.0（上一 commit 已含，随本版发布）

## 验证记录

- `test_worker_engine_compat.py` 13/13（含新增 2 测试）
- ruff check `api/` `tests/` → 0
- 服务器健康：livez ok / solver ok / 代理池 1404
- 真机并发 4/4 completed（见上表）
