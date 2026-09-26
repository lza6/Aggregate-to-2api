# v20.3.1 发行说明 — 生产缺陷修复 + 终局审计 P1 闭环

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🐛 真实缺陷修复

### P0 图生图 TLS 握手失败（/v1/edit 500）
- **根因**：`_edit_client` 复用共享 H2 keep-alive 会话，空闲后上游 TLS 会话失效 → `SSLV3_ALERT_HANDSHAKE_FAILURE`
- **修复**：图生图链恒用一次性 client（每次全新 TLS 握手），upload/submit/poll 三处统一 aclose 防泄漏
- **验证**：生产真实 /v1/edit 全链路 E2E（URL 输入 → 出图）

### P0 模型目录缓存
- `/v1/models` 60s 缓存（gallery_cache），避免门户/管理台每次请求重复 bootstrap+grouped

## 🔒 终局审计 P1 闭环

| 项 | 修复 |
|----|------|
| /v1/logs + /v1/logs/ws 匿名无脱敏 | log_buffer `_redact` 统一脱敏（Bearer/api_key/token/secret/敏感 query） |
| MCP generate_image 恒 mock:// 假结果 | 真实 provider 结果 URL 透传（mock 占位 https URL 也透传） |
| .env 模板双份分裂 + 166 变量缺失 | 根 .env.example 改为权威入口；deploy 补 12 个已消费未声明变量（VECTOR/EMAIL/IMAP/LINSHI/PROMPT） |
| 门户 PPT/视频 未启用时点开 404 | /v1/meta 加 ppt_enabled/video_enabled；PortalPpt/PortalVideo 开关检测降级 |

## 🧪 测试/质量
- 后端 agent_dag_exec + dispatch_edit_branches 46 passed（改动相关）
- MCP generate_image 手动验证：真实 URL 透传
- frontend Tasks/GalleryAlbum flaky 根治（afterEach restoreAllMocks → clearAllMocks）
- landing build 全绿（44 模块）

## 📋 文件清单
- api/imagefree_client.py / api/log_buffer.py / api/mcp/tools.py
- api/routes/admin/query.py / api/routes/health.py
- .env.example / deploy/.env.example
- frontend/src/test/{Tasks,GalleryAlbum}.test.tsx
- landing/src/components/{PortalPpt,PortalVideo}.vue
- 版本全链 bump 20.3.1
