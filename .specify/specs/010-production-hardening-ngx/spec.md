# Feature Specification: 010 生产加固（nginx 缓存/压缩 + 高并发探针 + 契约防坑）

## Problem Statement

v20.3.1 已闭环（图生图 TLS/日志脱敏/模型缓存/PPT 开关）。用户点名架构关注项：
LB/Caching/CDN/DB Replication/Sharding/MQ/Rate Limiting/Circuit Breaker/Health/Observability，
并要求避免重复已做项（verification-log 记录为准）。

审计发现**真实未做缺口**：
1. nginx 无静态缓存头（/assets 每次回源）→ CDN/缓存性能缺口
2. gzip_types 未配置（JS/CSS 未压缩传输）
3. 高并发极限施压未做（用户点名「极限施压与防穿透」）

## 现状（verification-log 已闭环，不重做）
- 图生图 TLS 修复（R2 SNI）✅
- /v1/logs 脱敏 ✅
- /v1/models 60s 缓存 ✅
- PPT 开关 + meta 探测 ✅
- Agent 真实 LLM E2E ✅
- MCP generate_image 真实透传 ✅

## User Stories

### US1: nginx 静态资源加速（P0）
作为站长，静态资源（JS/CSS/图片）应被 CDN/浏览器缓存 + gzip 压缩：
- /assets/ 下 hash 文件 Cache-Control: public, max-age=31536000, immutable
- index.html no-cache（防旧 hash chunk）
- gzip_types 补全（text/css/application/javascript/json/svg）

### US2: 高并发极限施压探针（P1）
作为站长，知道系统在多少并发下会崩：
- 压测 /v1/healthz + /v1/gallery（只读）不同并发
- 记录瓶颈：CPU/内存/延迟/错误率
- 产出压测报告

### US3: 契约防坑审计（P1）
作为调用方，API 文档与真实行为一致：
- OpenAPI /docs 与前端调用契约核对
- 错误码/限流头/缺省值核对

## Success Metrics
- nginx 静态资源响应含 Cache-Control immutable + gzip Content-Encoding
- 压测报告记录瓶颈 + 建议
- 契约核对表（无隐藏不一致）

## Out of Scope
- DB Replication/Sharding/MQ（单机 2C/4G 现实，标注建议）
- 已闭环项重做
