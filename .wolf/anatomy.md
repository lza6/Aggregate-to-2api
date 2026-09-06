# Anatomy — 文件索引

> 新会话在读取任何源文件前查阅本表。优先用本表描述 + graft 图谱定位，再回退 Read。
> 创建/删除/重命名文件后必须更新本表。

## 顶层

- `api/main.py` — 应用组装入口（<300 行，挂载路由/中间件/前端/生命周期），版本号在此
- `api/lifespan.py` — 9+阶段优雅关闭，P1-1 Redis storage 装配/⑨.5 关闭
- `api/meta.py` — 单例持有者（db/engine/registry/gallery_cache 等）
- `api/config/` — 配置包，`get_settings()` + `reset_settings()` 测试钩子；分组：base/cache/db/edit/http/observability/pool/provider/queue/security/solver/settings/presets
- `api/auth.py` — 聊天端点固定 Key 鉴权（IF_API_KEYS）+ 管理面独立 Key（IF_ADMIN_KEYS）+ `mask_key()`
- `api/request_guard.py` — per-IP 分片锁限流 + XFF 防伪造 + 黑名单 + P1-1 `set/get_storage_adapter`

## 路由 routes/

- `routes/generate.py` — 生图主链路 guard+prepare→入库→入队
- `routes/chat.py` — 聊天端点（tools 仅转发，无本地执行回路，P1-A 待补）
- `routes/tasks.py` — 任务查询/SSE
- `routes/health.py` — livez/healthz/readyz 三级
- `routes/security.py` — 安全头/封禁查询
- `routes/ecosystem.py` — 生态页
- `routes/admin/` — 管理面包（query.py 24 只读 + write.py 3 DLQ 写 + _common.py 共享 router）

## 引擎 worker/

- `worker/engine.py` — 引擎主循环（拆分后 738 行，扩缩容/DLQ 已迁出）
- `worker/queue.py` — CountedPriorityQueue/QueueFull/_WorkerHandle
- `worker/dlq.py` — 死信队列 build_dlq_message/push_dlq_on_exhaust（从 engine.py 拆出）
- `worker/generator.py` — generate_once/generate_once_b3/generate_with_429_proxy_fallback
- `worker/scaler.py` — 多维扩缩容评分（从 engine.py 拆出，P0-F4）
- `worker/token_pool.py` — Turnstile token 预取池

## 提供商 providers/

- `providers/base.py` — Provider/ChatProvider 抽象基类 + ModelSpec（meta 含 system_prompt_template/skills 等键）
- `providers/registry.py` — Registry（register/register_chat）+ startup_all/shutdown_all
- `providers/imagefree.py` / `aifreeforever.py` / `nanobanana.py` / `falai.py` — 各上游
- `providers/tryingopen/` — 聊天 provider 包（__init__ 主类 + _helpers 辅助）
- `providers/action_sniffer.py` — 动作嗅探

## 号池/邮箱池

- `account_pool/` — 号池包（mixin 拆分：_base/_constants/borrow/store/signin/stats/engine + pool.py 兼容垫片；`_pkg_attr()` 运行时读包命名空间保 monkeypatch 契约；fsm/scoring 独立）
- `registerer/` — 注册器包（types/utils/flow/cf_solve/email_verify，`_mock_register()` 运行时解析）
- `email_pool.py` + `email_sources/` — 邮箱池 + 7 临时邮箱源

## 数据层 db/

- `db/core.py` — 连接池/批量写/WAL checkpoint（拆分后 371 行，业务方法迁 queries.py 的 DBQueriesMixin）
- `db/migrations.py` — P0-3 DDL 下沉（init_schema：requests/idempotency/dlq/cache_store/chat_usage + 兼容补列）
- `db/queries.py` — DBQueriesMixin（DB 业务方法）+ QueueDB + task_to_public（DB 继承 DBQueriesMixin）

## 路由引擎/求解器/存储

- `adaptive_router.py` — MAB-EWMA 路由引擎（Score=成功率/log10时延×负载惩罚 + 熔断）
- `solver_guard.py` — SolverGuard 多节点联邦 + 熔断 + IdleTimeout
- `cf_clearance_solver.py` — CF clearance 求解
- `turnstile_client.py` — Turnstile token 求解客户端
- `storage/` — 存储适配层（base 抽象 + local sqlite/memory + redis_adapter + factory；P0-S1 request_guard 热路径已接 adapter.rate_limiter，降级内存桶）
- `agent/` — agent 子系统（intent LLM 分类/critic LLM 审查/guard 风险分级/memory 记忆巩固 L0-L3/routes /v1/agent/* 端点；chat_collect 走 tryingopen 免费上游，IF_MOCK_UPSTREAM=1 才 Mock）
- `vector/` — 向量检索（P3-D1，store+embed，sqlite-vec 或 pHash 降级，GET /v1/gallery/similar，IF_VECTOR_SEARCH_ENABLED 缺省关）
- `deploy/grafana/` — Grafana 仪表盘 + provisioning（P1-O4，imagefree-overview + slo-budget）
- `deploy/litestream.yml` — litestream 异地秒级备份（P1-O1，R2/S3 占位凭证）
- `deploy/prometheus.yml` — Prometheus 抓取配置（P1-O5 obs profile）
- `deploy/docs/` — monitoring.md（UptimeRobot P1-O2）+ litestream-restore.md（恢复 SOP）+ cloudflare-cdn.md（P1-O3，L3 待拍板）

## 提示词/可观测性

- `prompts/` — 提示词系统（base.md 宪法 + templates/ 三模板 + loader + __init__ compose_system_text；meta.skills 占位待 P1-A1 填充）
- `audit.py` — 审计（trace_id 透传可 grep 串联）
- `telemetry.py` — OTel tail 采样（错误 100%+正常 10%）
- `alerting.py` — 内置告警引擎+冷却+webhook
- `slow_log.py` + `sse_stats.py` — 慢日志/SSE 指标
- `log_buffer.py`/`log_ws.py`/`disk_logger.py` — 日志三件套（环形缓冲+WS 推送+14 天落盘）

## 前端

- `frontend/src/pages/` — 13 页（Dashboard/Tasks/Generate/ChatPlayground/Accounts/Providers/Health/Logs/Security/Slow/DLQ/Costs/Ecosystem）
- `landing/` — Vue3 公开落地页

## P1-A 新增（agent 化跃迁，v8.1.0）

- `api/skills/` — skills 四件套体系（SKILL.md + scripts/ + references/ + assets/，frontmatter 可发现性）
- `api/agent/` — intent.py（意图分类）+ memory.py（L0-L3 记忆）+ guard.py（PreToolUse 硬门禁）+（critic 在 skills/critic.py）
- `api/skills/critic.py` — 独立终检 Agent
- `api/captcha/` — 统一 solver 抽象层（M12，可选）

---

*更新日期：2026-09-05*
