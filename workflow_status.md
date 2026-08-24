# workflow_status.md — 终局闭环总审计工作流

## 项目状态总览
- 当前版本: v4.2.1
- 最近提交: 6e952f5 (UI 精简 + 画廊 Prompt + SSE 事件钩子)
- 生产状态: imagefree.tingfengai.art 运行中 (healthz ok, workers 10)
- 生产部署: Docker Compose (cfsolver + api + Caddy)

## 任务追踪矩阵

### ✅ 已闭环（v4.0-v4.2.1）
| 任务 | 证据 | 验证 |
|------|------|------|
| MAB-EWMA 自适应路由 | api/adaptive_router.py | 14 项单元测试通过，生产 /v1/routing/records 可用 |
| SS 订阅格式 | api/geo_ip.py | 生产 curl /v1/proxy-pool/subscribe 输出 ss:// |
| 复制按钮 fallback | api/docs.html copyTextSafe() | 三级 fallback 实现 |
| main.py 拆分 (1689→72) | api/main.py + api/routes/ + 6 个新模块 | 42 路由全部注册，集成测试通过 |
| SSE 每任务事件流 | api/sse_events.py + /v1/tasks/{id}/events | 生产 curl 验证，worker 4 处 hook |
| 路由记录全覆盖 | api/dispatch.py _dispatch_generate() | imagefree 也走路由记录 |
| 导航精简 12→8 | api/docs.html | 验证无误 |
| 画廊 Prompt 复制 | api/docs.html glb-copy-prompt/fill-prompt | 按钮存在，文案正常 |

### 🔄 部分闭环（待补齐）
| 任务 | 当前状态 | 缺口 | 优先级 |
|------|---------|------|--------|
| 号池自动化注册 | 脚本存在 (batch_register.py, nanobanana_loop.py) | 生产号池 0/500 | P0 |
| SSRF 防护 | api/dispatch.py _parse_input_image() | 仅 IP 级别检查，无 URL 来源白名单 | P1 |
| API 速率限制 | api/retry_policy.py 有限流分类 | 无全局 rate limiter 中间件 | P1 |
| 前端路由记录面板 | Dashboard.tsx 底部有路由记录 | 无节点状态卡片 | P2 |
| 前端画廊复制 | docs.html 有，React Gallery.tsx 无 | 前端组件无复制按钮 | P2 |
| README.md | 498 行 | 未更新 v4.2 架构变更 | P1 |
| .env.example | 无 | 缺少环境变量模板 | P1 |
| 文档 | 各文件内嵌 docstring | 缺少独立 API 文档 | P2 |

### ❌ 未闭环
| 任务 | 原因 | 优先级 |
|------|------|--------|
| 10k 账号注入 | 需外部 cf_solver + 邮箱源 + 代理 | P0 (长期) |
| CDN 配置 | 静态资源未走 CDN | P3 |
| Rate Limiter 中间件 | 需添加 FastAPI 中间件 | P1 |
| 前端测试 | 无 React 测试 | P2 |
| 契约测试 | api/contracts.py 存在但不作为运行时校验 | P2 |

## 当前修复优先级
1. P0: 号池生产补号（启动 batch_register 后台监控）
2. P1: README.md 更新 + .env.example 创建
3. P1: 全局 Rate Limiter 中间件
4. P1: API 文档同步
5. P2: 前端 Gallery.tsx 复制按钮
6. P2: 路由面板加强
7. P3: 架构文档 + CDN + 高可用

## 依赖关系
- 号池补号依赖 cf_solver 运行、邮箱源可用、代理池可用
- 其他任务无强依赖，可并行