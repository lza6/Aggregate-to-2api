# Implementation Tasks: 007 v20 平台化重构（提供商瘦身 + 首页在线使用）

> 格式：`- [x| ] T### [优先级] [USx] 描述 文件路径`（US1=提供商瘦身 / US2=首页在线使用 / US3=tryingopen 真实调用）。
> Setup 已由 v20 三 commit 完成；Core/Integration/Polish/Verification 为剩余回填（G1/G2/G3/G4）。

## Phase Setup（已完成，v20.0.0 已推送已发版）

- [x] T001 [P0] [US1] 下线 nanobanana/falai 提供商模块与注册表 `api/providers/registry.py`
- [x] T002 [P0] [US1] 删除 IF_FALAI_* / IF_NANOBANANA_ACCOUNT_TARGET 配置与 env 模板 `api/config/` `.env.example` `deploy/.env.example`
- [x] T003 [P0] [US1] 号池停用自动补号/每日签到循环；/v1/account-pool 移除 nanobanana 强制槽位 `api/worker.py` `api/routes/account_pool.py`
- [x] T004 [P0] [US2] 落地页 HomeChat（SSE 流式/骨架/空错态/重试/键盘/移动端） `landing/src/components/HomeChat.vue`
- [x] T005 [P0] [US2] 管理端 / = ChatPlayground、/dashboard = 仪表盘、/chat 兼容 `frontend/src/`
- [x] T006 [P0] [US3] 放开 tryingopen 真实调用（IF_MOCK_UPSTREAM 默认 false） + 文档 + 版本 bump 20.0.0 + Release `api/config/` `docs/`

## Phase Core（G2 全量 E2E 回填，P0）

- [ ] T007 [P0] [US1] 干净环境跑 `scripts/e2e_providers.py`（nanobanana/falai 不存在断言 + tryingopen 对话冒烟 + 号池看板）并回填 PASS 证据 `scripts/e2e_providers.py`
- [ ] T008 [P0] [US2] 干净环境跑 `scripts/e2e_v12.py` 38 段（mock solver + e2e DB 清理 + openapi version==20.0.0） `scripts/e2e_v12.py`
- [x] T009 [P0] [US3] 线上真实 /v1/chat/completions + /v1/agent/dag/plan 冒烟（mock=False 真实 tryingopen 路径） `api/` `scripts/`
- [x] T010 [P0] [US1] 定向 pytest 24 文件全绿 + ruff 0 + compat 13/13 `tests/`（email_pool 本机重负载 290s 超时，CI Linux 为完整口径）
- [x] T011 [P0] [US2] 前端收尾：tsc -b 0 + vitest 35/35 + landing build 成功 `frontend/` `landing/`
- [x] T012 [P0] [US1] 版本门禁核对：openapi==20.2.0 + e2e_v12 断言 20.x + registry=[imagefree,aifreeforever]+[tryingopen] `scripts/`

## Phase Integration（G4 浏览器验收 + 线上复询，P1）

- [ ] T013 [P1] [US2] Playwright 落地页 HomeChat：SSE 流式渲染 + 模型切换 + 错误→重试 + 375/768 断点无横滚 `frontend/e2e/` 或 `scripts/`
- [ ] T014 [P1] [US2] Playwright 管理端：/ 聊天、/dashboard、/chat 兼容 + 明暗截图归档 `frontend/e2e/`
- [x] T015 [P1] [US3] 线上复询：Anthropic /v1/messages 200（503 为上游瞬时抖动非回归） `docs/verification-log.md`

## Phase Polish（G1 用户产品层，可选 P2）

- [ ] T016 [P2] [US2] 会话历史持久化评审（localStorage vs DB 表），保持匿名 Key 模式 `landing|frontend` + DB
- [ ] T017 [P2] [US2] X-RateLimit-* 响应头 → UI「剩余次数」气泡 `frontend/src/`
- [ ] T018 [P2] [US2] 对话导出（Markdown / 截图） `landing/src/` `frontend/src/`
- [ ] T019 [P2] [US2] G1 能力落地配最小 vitest/Playwright，不引入付费/登录体系 `tests/` `frontend/e2e/`

## Phase Verification（收尾台账）

- [ ] T020 [P0] [US1] 全量验证回填 docs/verification-log.md（v20 行：E2E n/n + 线上探针 + 复询结论） `docs/verification-log.md`
- [ ] T021 [P0] [US2] release notes 20.0.0 补「全量 E2E n/n」证据 + tasks 全部 [x] 后归档 007 目录 `docs/releases/release_notes_20.0.0.md`

## Notes

- 可写边界：仅 `.specify/specs/007-v20-platform-refactor/`；其余仓库文件只读验收；不 git add/commit。
- 无新 Release 授权：G2/G4 全部 [x] 前不 bump 版本。
- G3（视频新上游）另行 spec 立项，不进本 tasks 编号。
- 拒绝伪闭环：每个 E2E 任务需附真实 stdout/断言证据，禁止「跑过=完成」。