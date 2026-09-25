# v20.2.1 发行说明

> 发布时间：2026-09-26 ｜ 基于 v20.2.0（`c7ceed2`）｜ 主题：生产化审计修复（索引/内存/缓存）

## 变更（Spec 008 生产化终局审计第一批）

### 性能与数据正确性（S2 SQL 审计 P1 修复）
- **索引优化**：requests `(status, finished_at)` / `(status, created_at)`、chat_usage `(provider, model)`、accounts `(provider, status, credits, updated_at)` 增量 DDL
- **修复坏索引 bug**：`requests(status, model)` 引用不存在列，曾致新库 `init_schema` 失败、依赖 DB 初始化的测试全部 ERROR——已移除并验证
- **内存泄漏**：`engine._process` 的 row=None/cancelled 早退路径补 `_enqueued_at.pop`（防无界增长）
- **缓存加载**：`load_cache_snapshot` 改 SQL 侧 `WHERE cached_at+ttl>now` 过滤（防全表加载内存膨胀）

### 架构演进方案（ADR，方案级不实施）
- `adr/architecture-evolution.md`：LB/Redis/CDN/DB 复制/消息队列/限流/熔断/健康检查 8 项分阶段方案
- 建议立即落地：nginx 静态缓存头 / 模型目录缓存 / Litestream 异地备份

## 验证记录
- 定向测试：gallery_crud 8/8、worker_engine_compat 13/13、admin_export 5/5、main_validation 43/43 全绿
- ruff 0；SQL 注入审计 P0=0（拼接均参数化/白名单）
- 契约核验：91 路由全部可用或明确降级（gallery/duplicates 503=向量搜索未启用设计如此；logs/ws 404=WS 端点 HTTP 探测误报）
- 部署同步：服务器 git pull → 本 commit，openapi version 20.2.0

## 部署
- 生产 20.204.27.154：git pull + restart（标准流程）
