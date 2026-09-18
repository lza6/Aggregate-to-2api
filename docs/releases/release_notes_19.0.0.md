# v19.0.0 发行说明

> 发布时间：2026-09-19 ｜ 基于 v18.0.0（`470e9a9`）｜ 主题：安全参数化 + 上下文成本治理 + 视频逐帧事件

## 主题：把「后置治理项」闭环

v18 交付自动沉淀/记忆 RRF/MCP 渐进暴露/PPT/视频 Mock 任务模型；v19 落地安全参数化、上下文 token 成本治理与视频 SSE 逐帧事件。

### 新增（P2-3 solver evaluate 参数化，captcha-solver 对标）

- `api/solver_guard.py::validate_solve_params(url, sitekey)`：求解参数白名单校验——url 必须 http/https + host；sitekey 仅允许安全字符类（字母/数字/-/_，1-120 字符，兼容 mock 短值）；**注入字符（空格/引号/分号/换行）被拒绝**
- `api/turnstile_client.py` 求解入口接入：参数非法 → AppError 422（不触达求解服务）
- 验证：`tests/test_solver_evaluate.py` 7 + 既有 turnstile/captcha 组合 34 全绿

### 新增（P2-2 上下文 token 成本治理，headroom/rtk-master 对标）

- `api/agent/context_trim.py` 纯函数集：`trim_chat_messages`（保留 system + 最近 N 轮 + 单条截断）、`summarize_for_intent`（空白折叠 + 截断）、`estimate_tokens`（CJK 1.5 字/token 近似）、`fold_whitespace`
- 验证：`tests/test_context_trim.py` 6 全绿

### 新增（P2-1 视频 SSE 逐帧事件，Pixelle ProgressEvent 对标）

- `POST /v1/video` 后台自动发布 progress/result 帧到 TaskEventHub；`GET /v1/video/{task_id}/events` SSE 流（Last-Event-ID 断线补偿，复用 tasks SSE 基建）
- 验证：`tests/test_video_tasks.py` 6（SSE publish/replay 语义）

### 修复

- solver sitekey 白名单首版过严（20 字符下限 + 严格 hex）误拒真实 CF sitekey（`0x`+base64url 混合）与 mock 短值——改为安全字符类白名单（参数化安全语义），既有 turnstile 测试零回归

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端新增测试 | evaluate 7 + context 6 + video SSE 2 = **15** | 全绿 |
| 组合回归 | 本批 12 文件 0F（含既有 turnstile 26 + captcha） | 全绿 |
| Lint | `ruff check api/ scripts/` | 0 error |
| **真实 E2E** | `scripts/e2e_v12.py`（38 段） | **38/38 PASS** |
| 版本 | 全链 14 处 → **19.0.0** + dist 重建 | 契约同步 |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，0 真实付费调用。

### 升级说明

- 求解参数校验为**增量**：合法 sitekey/url 行为不变；仅注入字符被拒（防御增强）。
- 上下文 trim 为**纯函数库**：由调用方决定是否启用（`IF_CTX_TRIM=0` 缺省不影响现有链路）。
- 视频 SSE：`/v1/video/{task_id}/events` 新增（`IF_VIDEO_ENABLED=1` 时可用）。
- **待验证/后置**：桌面真机（无 Rust）；i18n 9 页全覆盖（指南 P0-3 完整方案已备，预算内未实施）；记忆 RRF 默认开启（待索引优化）；真实视频 provider/SSE 生产压测。