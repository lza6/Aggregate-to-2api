# v20.0.0 发行说明

> 发布时间：2026-09-25 ｜ 基于 v19.0.0（`490185d`）｜ 主题：提供商下线（nanobanana/falai）+ 首页在线对话 + tryingopen 真实调用

## 主题：把「运维面减法」与「体验入口」一起闭环

v19 交付 solver 参数化/上下文成本治理/视频 SSE。v20 做两件事：**下线两个维护成本最高的上游**（nanobanana 号池签到、fal.ai 视频反自动化），同时把**在线使用放到首页**（落地页 HomeChat + 管理端 `/` 在线对话），并放开 agent 对 tryingopen 的真实调用。

## 变更

### 移除提供商：nanobanana（号池签到） + falai（视频）

- 删除 `api/providers/nanobanana.py`、`api/providers/falai.py`，注册表只保留图片上游 `imagefree` / `aifreeforever`，聊天固定 `tryingopen`
- 删除配置：`IF_FALAI_*`、`IF_NANOBANANA_ACCOUNT_TARGET`（`api/config/` 三处 + `.env.example`/`deploy/.env.example`）
- 号池：`account_pool` 启动不再挂自动补号/每日签到循环（`_autoregister_loop`/`_daily_checkin_loop` 保留供测试直调）；`/v1/account-pool` 不再硬编码 nanobanana 槽位
- 删除孤儿工具脚本：`batch_register_nb/batch_register/inject_accounts/live_reg_one/debug_live_register/test_real_reg*`、`e2e_v66/e2e_v67_verification`，及对应测试（`test_falai/test_registerer*`）
- E2E 脚本 `e2e_providers.py`/`e2e_full.py` 改为断言 nanobanana **不存在**，路由段换成 tryingopen 对话冒烟

### 新增：首页在线使用（对话式）

- **落地页** `landing/src/components/HomeChat.vue`：模型下拉（tryingopen）+ 消息线程 + SSE 流式回复 + 发送/加载骨架 + 空态/错误态/重试 + 键盘（Enter 发送 / Shift+Enter 换行）+ 移动端适配；挂在 hero 下方
- **管理端** `/` 改为 `ChatPlayground` 在线聊天；仪表盘挪到 `/dashboard`（`/chat` 兼容保留）；侧栏/命令面板同步
- `Privacy.vue` 移除 nanobanana/falai 数据声明

### tryingopen：agent 与对话默认真实调用

- `IF_MOCK_UPSTREAM` 默认 `false`：planner/critic/intent/memory 直接调 tryingopen 真实 LLM，异常才回退规则兜底
- 文档/测试注释从「禁止真实调 tryingopen」改为「默认真实调用；测试注入 Mock 仅为稳定断言」

## 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端定向 pytest | 26 文件逐文件（providers/registry/config/budget/account_pool/agent/integration 等） | **26/27 全绿**（`test_email_pool.py` 本机 180s 超时，重跑见下） |
| 前端 type-check | `tsc -b`（frontend） | exit 0 |
| 前端定向 vitest | CommandPalette/ProvidersSort/CostsPage/Slow/i18n | **28/28 PASS** |
| landing 构建 | `npm run build` | **prod bundle 成功** |
| registry 启动冒烟 | `python -c "bootstrap()"` | providers=[imagefree,aifreeforever] chat=[tryingopen] |

> `test_email_pool.py` 为既有重负载文件（宿主资源限制会 kill，见 v19 指南 0.2 节），与本次改动无交集，单独重跑确认中。

## 升级说明

- 线上若仍配置 `IF_FALAI_*`/`IF_NANOBANANA_ACCOUNT_TARGET`：不再生效（`extra=ignore`），可保留或删除
- 号池数据不删：`data/account_pool.db` 历史账号保留，`/v1/account-pool` 可查询
- 在线使用入口：落地页首页对话、`/admin`（`/` 聊天、`/dashboard` 仪表盘）
- **待验证/后置**：真实视频上游另选（falai 下线）；桌面真机；完整 E2E 38 段在干净环境跑通后回填
