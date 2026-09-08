# Memory — 单行条目

> 每次重要行动后追加一行（日期 + 动作 + 证据）。只记事实与证据，不记私有推理。

- 2026-09-05 v8.0.0 闭环 P0 架构治理（7 大文件拆分）+ P1 剩余（storage 接线/cf_solver 联邦/号池 FSM 自愈），commit dbd91fb + tag v8.0.0 + Release id 383275142
- 2026-09-05 重建 .wolf 协议（OPENWOLF.md/cerebrum.md/anatomy.md/memory.md）——git 历史无此文件，按 CLAUDE.md 重写最小版
- 2026-09-05 用户批准 agent 化批次 LLM 真实付费调用（无预算上限），启动 P1-A1~A7 落地
- 2026-09-06 v8.5.0 闭环：P0 拆分收尾（config 1178→769/account_pool 1111→75/db.core 985→371/engine 833→738）+ P1 agent E2E（10+8用例+4 Prometheus Counter）+ 运营层（litestream/UptimeRobot/Grafana/compose 3 profile/cf多节点）+ P2 前端登顶（Skeleton/CommandPalette/虚拟列表/乐观更新/landing LCP<1.5s/a11y 0 critical）+ P3 向量检索（sqlite-vec+SimHash）/成本预测（predict_budget_burn）。commit accda34 + tag v8.5.0 + Release。全量单测全绿，ruff/mypy 0 error
- 2026-09-06 P2-F1 flaky 根治：test_account_growth 加最终一致性轮询（40次×0.2s timeout 8s）消除 CI 1/37 404 时序
- 2026-09-06 anatomy.md 已更新：account_pool mixin 拆分/db.core 拆分/engine 拆分/storage 热路径/agent/vector/deploy grafana+litestream+docs 条目
- 2026-09-06 stage-mtpswcm8: 产出《2026-09-06-stage-mtpswcm8-权威基线档案.md》(计划书/)，收敛管线10环节为v8.5.0真实缺口表(G1 mypy strict 2模块→P0 / G2 .benchmarks 42项→P1 / G3 sw.js缺→P2 / G4 agent DAG缺→P3 + 2项⏸L3)，已落地~85%待办勿重做，运行时验证未跑(权限约束)，未触碰源码未commit

2026-09-06 stage-mtpswcm8: 产出《2026-09-06-stage-mtpswcm8-权威基线档案.md》(计划书/)，收敛管线10环节为v8.5.0真实缺口表(G1 mypy strict 2模块→P0 / G2 .benchmarks 42项→P1 / G3 sw.js缺→P2 / G4 agent DAG缺→P3 + 2项⏸L3)，已落地~85- 2026-09-07 v9.0.0 闭环：G4 基础 DAG 编排真实落地（api/agent/dag.py 引擎 Kahn 拓扑+并行扇出真并发+fail_fast 传播+指数退避重试；planner.py Mock 优先+LLM 降级；routes/agent_dag{,.py,_store,_exec}；POST/GET /v1/agent/dag/run|plan|{id}）。56 用例全绿 + 覆盖率 89.5% + 真实 HTTP E2E（uvicorn:8102+mock solver:8002，plan→run→succeeded/bogus 422/cycle 422/404/扇出成功/metrics agent_* 启动即注册）。commit 788c210 + tag v9.0.0 + push origin main。深化层 6.1-a~f（多模态/RAG/自反思/记忆/条件分支/人机协作）+ MCP 6.2 待办。版本 8 处 + JSON-LD + 2 dist 全 9.0.0 一致。踩坑：api.routes.agent_dag_store 包级属性被 _common re-export 遮蔽（用 .dag_run_store 实例）；planner LLM 路径先取真 registry 单例免 bootstrap 破坏 Mock；DAG 并行 skip 判定改依赖终态实时判定。

- 2026-09-09 v10.0.0 flaky 根治 4 项：① tests/test_redis_adapter.py `_run_restoring` 取 loop 容错（无 loop→None）；② tests/conftest.py 模块级早设 IF_DB_FILE 临时库（防 memory/ip_blocklist 写真实 data/imagefree.db）；③ tests/test_token_pool.py autouse 重置 solver_guard（防集成 circuit_breaker 残留 OPEN 电路致 acquire None）；④ api/cache.py set ttl<=0 用 now-1 哨兵（防 deadline==now 同一 tick 不过期）。加 tests/integration/test_dag_integration.py 补 pytestmark=integration 并发改造为 app_with_mocks（防单测口径误收集 + TestClient 双 app teardown 污染）。全量单测 1915 passed + 集成 49 passed + ruff 0 + vitest 233 + build 全绿，真实 E2E（plan→run→轮询→重启持久化→tool 回路→metrics）通过。
