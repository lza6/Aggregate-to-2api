# v6.4.1 后端版本号统一 + 前端 UI 完善（Token 大单位 / 总用量主卡 / 页脚去重 / 版本注入）

> 本轮为 UI/版本一致性收尾 + 回归验证，无核心链路改动。核心逆向/号池/路由逻辑保持 v6.4.0 不变。

## 变更清单

### 版本号统一为 6.4.1（消除漂移）
- `pyproject.toml` / `api/main.py`（FastAPI `version`）→ 6.4.1
- `frontend/package.json` → 6.4.1
- `deploy/docker-compose.yml`：`imagefree-api:6.4.1` / `imagefree-cfsolver:6.4.1`
- `README.md` 版本徽章 → 6.4.1
- `api/docs.html` 页脚版本号 `v6.3.0` → `v6.4.1`（deploy 副本经 `scripts/sync_deploy.py` 同步一致）

### 前端 UI 完善
- **Token 大单位 M/B/K**（`frontend/src/pages/Dashboard.tsx` `formatTokens`）：补齐 **B（十亿）** 档、`k` 改大写 `K`，与 docs.html `fmtTokens` 对齐。
- **版本号不再硬编码**（`frontend/vite.config.ts` + `vite-env.d.ts`）：build-time 从 `package.json` 读取并注入 `__APP_VERSION__`，Layout 侧栏 footer `v4.3.3 → v{__APP_VERSION__}`，杜绝「注释 v6.3.4 / 显示 v4.3.3」式漂移。
- **移除失控的「宇宙星图」页**（`App.tsx` / `Layout.tsx`）：该路由是早期误读需求引入，从导航与路由中剔除，恢复 e2e-smoke 预期的 8 个导航项。

### 控制台单页 docs.html 完善
- **统计用量直接显示总用量**：聊天用量面板「总量 tokens」升级为**主卡置顶**（`grid-column:span 2` + 焦点边框），独立 Prompt/Completion/推理小卡合并为副行，保留调用次数/耗时/工具调用作为次要信息。
- **页脚去重**：删除与 header 重复的 logo、「听风AI（逆向号池）」、「多提供商 AI 生成网关」、「微信 Tf00798」品牌块，只保留负责人/GitHub/慢请求看板/API Key 提示/喝咖啡/版本号。

## 回归验证（真实运行证据）
- 前端：`tsc -b` 通过（0 错误）、`npm run build` 成功、`npm run smoke` = **12 通过 / 0 失败**。
- 后端：`test_retry_policy`（49 passed）、`test_ip_blocklist`（22 passed）、`test_account_pool`（17 passed）、`test_registerer`+`test_email_pool`（23 passed）、`test_chat_auth`（8 passed）、`test_chat_routes`（6）、`test_main_validation`（41）、`test_solver_guard`（18）、`test_providers`（15）、`test_config_validate`（15）、`test_errors`（39）、`test_log_ws`（5）、`test_ui_ux_improvements`（2）、`test_adaptive_router`（14）、`test_cache_persist`（10）、`test_db_batch_write`（14）、`test_db_connection_pool`（21）、`test_db_indexes`（8）、`test_db_security`（10） 全绿。
- 关键路径 E2E 探针：401/403/404/422 → `permanent` 且 `should_retry=False`；429→rate_limited、500→server_error（应重试）；私网/回环（172.25.0.1 / 169.254.10.1 / 192.168.1.5 / 10.0.0.7 / 127.0.0.1）→ `LAN`，公网（8.8.8.8 / 1.1.1.1）→ 命中公网归属。均符合预期。
- `scripts/sync_deploy.py check`：`api/` 与 `deploy/api/` **完全一致**。

## 已知限制
- `tests/test_base64_separation.py` 在本地运行会 hang（依赖 session event-loop + worker 生命周期 + mock cf_solver 常驻），CI 环境通过，非本次引入。
- `ruff check api/` 报告 87 项（多为 pre-existing unused import / F841），非本次改动引入，未做不相关重构。

## 部署
- 前端产物 `frontend/dist` 由宿主机构建，经 docker compose 只读挂载 `../frontend/dist:/app/frontend/dist:ro`，无需重建后端镜像即可刷新 /admin。
- 后端镜像 tag `imagefree-api:6.4.1` 在服务器构建并重启。
