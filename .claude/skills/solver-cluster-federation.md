---
name: solver-cluster-federation
description: Cloudflare Turnstile 求解集群 Federation 与双缓冲预热池运维规范
version: 5.0.0
last_verified: 2026-08-25
---

# Solver Cluster Federation & Double-Buffering 运维规范

## 1. 架构与运行拓扑
- **配置格式**：`CF_SOLVER_URLS="http://node1:8001,http://node2:8001"`，权重通过 `SOLVER_NODE_WEIGHTS='{"http://node1:8001":2}'` 自定义。
- **负载调度**：`SolverGuard` 依据 `inflight / weight` 选择最低在途健康节点。
- **429 限流保护**：节点遇到 429 自动进入 60s 隔离期，期间由其他备选节点提供服务。
- **双缓冲池**：`_TokenPool` 维护 `active_q` 与 `standby_q`，请求极速 0ms 出队，空闲时自动切换与按需预热。

## 2. 验证命令
```bash
# 验证 Federation 负载均衡与故障转移
python -m pytest tests/test_solver_federation_e2e.py -v

# 验证 SolverGuard 状态机
python -m pytest tests/test_solver_guard.py -v

# 验证 TurnstileClient 客户端行为
python -m pytest tests/test_turnstile_client.py -v
```

## 3. 监控快照与告警指标
通过 `/healthz`、`/v1/stats` 或 Prometheus `/metrics` 监控：
- `solver_status`: `ok` / `degraded` / `circuit_open`
- `nodes`: 包含每个节点的 `inflight`、`rate_limited`、`circuit_open`、`solve_avg_seconds`
- `token_pool`: 包含 `active_size`、`standby_size`、`buffer_swaps_total`、`zero_latency_hits`
