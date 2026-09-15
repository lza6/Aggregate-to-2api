# v15.0.0 发行说明

> 发布时间：2026-09-15 | 基于 v14.0.0（`44eb3bc`）| intent embedding 多原型语义增强 + CAPTCHA 统一 solved 协议

## 主题：让意图分类"更懂中文关键词"，让两条 CF 求解通道"一个协议对外"

### 新增

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **intent embedding 多原型 + 关键词加权**（v15-A） | `api/agent/intent.py` 新增 `_EMBED_PROTO_EXTRAS`（6 场景各 2-4 个中文关键词/短语，如 image→["图片","插画","绘画","壁纸"], video→["视频","短片","动画"], chat→["聊天","回复","写"], ecommerce→["商品","主图","店铺"], ppt→["演示","幻灯片"], image_edit→["修图","编辑图片"]）运行时经 `compute_embedding` 生成原型向量与单原型合并取最高 cosine；`_EMBED_KEYWORD_BONUS=0.15` 子串命中加权（置信度封顶 1.0）；`_EMBED_PHRASE_CACHE` 模块级缓存免重复计算（异常降级 None 不崩）；`_EMBED_PROTO_META` 补 `image_edit` 条目 | 复用 `IF_INTENT_EMBED_THRESHOLD` / `IF_AGENT_INTENT_CLASSIFIER` |
| **CAPTCHA 统一 solved 协议**（v15-B） | 新建 `api/captcha/protocol.py`：`@dataclass(frozen=True) CaptchaResult`（token/cookies/user_agent/elapsed_ms/solver + `ok` 属性）；`TURNSTILE_SOLVER`/`CF_CLEARANCE_SOLVER` 常量；`from_turnstile()`/`from_cf_clearance()` 双工厂；`api/turnstile_client.py` 增 `solve_turnstile_result() -> CaptchaResult`（原 `solve_turnstile` 保持 tuple 返回向后兼容）；`api/cf_clearance_solver.py` 增 `solve_result()`（原 `solve` 保持 dict 返回） | — |

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `pytest -m "not integration and not chaos and not slow"` | **2127 tests / 0 failures（autoregister 预存 flaky 单跑绿）/ 0 error / 1 skipped** |
| v15 新用例 | `test_agent_intent_embed_v15.py`(10) + `test_captcha_protocol.py`(12) | 全绿 |
| 集成+混沌 | `pytest tests/integration/ + tests/chaos/`（mock cf_solver） | **54 passed / 0 failed** |
| ruff | `ruff check api/ tests/ scripts/` | 0 error（isort/SIM 修复） |
| 真实 E2E | `python scripts/e2e_v12.py`（全程 Mock） | **14/14 PASS** |
| 前端 | vitest **255 passed** + build/tsc 0 + 契约 20/20 | 全绿 |
| 版本 | 14.0.0 → 15.0.0 全链 + dist 重建 | 契约绿 |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，零真实付费上游调用。

### 升级说明

- 无新增环境变量（复用既有 IF_INTENT_EMBED_THRESHOLD / IF_AGENT_INTENT_CLASSIFIER）。
- `solve_turnstile` 返回 tuple、`CfClearanceSolver.solve` 返回 dict 保持不变（向后兼容）；新调用方可统一用 `CaptchaResult`。

### 遗留（下轮候选）

- GitHub Release 页面（需 PAT；tag 已推远程）
- `autoregister_loop 时序 flaky`：cerebrum 已知预存（代理池每日限额时序），本轮确认与 v15 无关（未触碰 account_pool/proxy_pool）