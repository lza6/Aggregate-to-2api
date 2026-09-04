# 新功能接入 SOP（v7.7 沉淀）

> 适用：往听风AI 网关新增任意功能（新端点/新页面/新配置/新脚本）。
> 前置阅读：`.claude/skills/imagefree-workflow/SKILL.md` + `new-provider-sop.md`。

## 工作流（强制先思考后编码）

1. **Spec-Kit 规范**（`.specify/specs/NNN-<feature>/`）：spec.md（FR/AC）→ plan.md（架构+依赖）→ tasks.md（节点+验收）。
2. **先查勿重跑**：读 `docs/verification-log.md` 的「验证过勿重跑」区，避免重复审计既有设计。
3. **先查 graft 图谱**：`graft ask "<task>"` / `graft callers <sym>` 定位代码，再回退 grep/read。

## 新端点 6 步

### 1. 路由（api/routes/<domain>.py）
- `@router.get/post("/v1/<domain>/<action>")`，写操作加 `check_admin_key(request, scope="admin-<action>")`。
- 返回走 `error_response`/`JSONResponse`，错误码用 `ErrorCodes.<CATEGORY>.<NNN>`（见 api/errors.py）。
- **验收**：新增 `tests/test_<domain>.py` 覆盖 200/400/401/403/422 路径。

### 2. 鉴权边界
- 只读端点公开（/v1/stats、/v1/models、/v1/healthz）；写操作独立 `IF_ADMIN_KEYS` 池。
- 聊天端点 v7.7.1 公益开放（仅 per-IP 频控），生图公益开放。
- **验收**：`tests/test_auth_ip.py` + `tests/test_chat_auth.py` 全绿。

### 3. 数据层（api/db/）
- 新表走 `aiosqlite` + 连接池；列名白名单；值 `?` 参数化；0.2s 批量写合并。
- 索引/唯一约束在 `db/core.py` 的 `_ensure_indexes` 加。
- **验收**：`tests/test_db_*.py` + `tests/test_async_sync_contamination.py`（AST 扫描）。

### 4. 后台任务
- fire-and-forget 用 `from api.background import spawn; spawn(coro, name="...")`（持强引用，防 GC）。
- 同步 I/O（DNS/urllib/file）用 `asyncio.to_thread` 下放。
- **验收**：`spawn` 返回的 task 在 `pending_count()` 可见，异常必 log.exception。

### 5. 前端（frontend/src/）
- 类型放 `api/<domain>.ts`，请求走 `apiFetch`（自带超时/错误规范化/取消）。
- 写操作 `adminHeaders()`；错误经 `ApiError` 抛出，UI 走 `ErrorRetry`/toast。
- 防重复提交：`disabled={loading}`；危险操作 `confirm()`；空态/错误态/骨架屏三态覆盖。
- 无障碍：input `aria-label`；装饰 emoji `aria-hidden`；`:focus-visible`；触控 ≥44px。
- **验收**：`cd frontend && npm run build && npm run test` + `node e2e-smoke.cjs` + `node resp-audit.cjs`。

### 6. 文档 + CI + 发版
- `README.md` 端点表加行；`docs/SOP.md` 排查表加症状；`deploy/.env.example` 加新 `IF_*`。
- `ci.yml` 若新增 py 依赖或 lint 规则，同步 `ruff check api/ tests/ scripts/`。
- 版本 bump 全 8 处；`verification-log` 追加；tag push 触发 Deploy；生产 E2E。

## 验收清单（每次必过）

- [ ] 后端 `pytest -m "not integration and not chaos and not slow"` 全绿（或仅预存 flaky）
- [ ] 集成 `pytest tests/integration/ -m "integration"` + `pytest -m "chaos"` 分轮全绿
- [ ] 前端 `npm run build`（tsc 0 error）+ `npm run test`（vitest）全绿
- [ ] E2E `node e2e-smoke.cjs`（22 断言）+ `node resp-audit.cjs`（20 断言）全绿
- [ ] 版本一致性 `TestFrontendVersionConsistency` 3/3
- [ ] ruff `check api/ tests/ scripts/` 0 error
- [ ] 文档与实际一致（README 步骤可跑通、SOP 命令有效）

## 红线（常驻）

- 付费 API 零真实调用（Mock/fixture 验证）
- 密钥 `IF_*` 环境变量，日志脱敏
- 同步 I/O 下放线程池
- 不可变优先；组件内联 `<style>` 迁 CSS Modules（Phase 2）
- 提交格式 `<type>: <description>`，归属全局禁用
