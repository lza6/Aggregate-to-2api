# Feature Specification: v20 平台化重构（提供商瘦身 + 首页在线使用 + 后台体验升级）

## Problem Statement

听风AI 当前是「多提供商逆向网关 + 运维后台」形态：后台 15 个页面偏工程监控（提供商/号池/DLQ/成本/慢日志），**没有面向普通用户的在线使用入口**；同时 nanobanana（号池签到）与 fal.ai（Kasada 视频）两个上游维护成本最高、依赖脆弱。本次把产品重心从「网关运维」转向「平台化在线使用」：
1. 下线维护成本最高的两个上游（nanobanana / falai），保留 imagefree/aifreeforever 图片 + tryingopen 对话
2. 把「在线使用」放到首页：落地页直接可对话（HomeChat），管理端 `/` 即在线聊天
3. 放开 tryingopen 真实调用：agent（planner/critic/intent/memory）与聊天默认走真实 LLM，不再以「Mock 红线」束缚
4. 后台体验升级：在线使用优先、仪表盘独立、provider/号池视图只留历史可查询能力

## 已完成（v20.0.0 三个 commit，未推送）

- `102120f` refactor: 下线 nanobanana/falai（注册表/config/号池/脚本/测试）
- `49e4ae5` feat: 首页在线对话（管理端 / 聊天 + landing HomeChat）
- `a9ac59c` docs: 全链文档同步 + 版本 20.0.0 + 发行说明

## User Stories

### Story 1: 提供商瘦身（已完成，验收待确认）

作为站长，我不再维护 nanobanana 号池与 fal.ai 反自动化，只保留稳定免费上游。

**验收标准**
- [x] `registry.providers` = {imagefree, aifreeforever}，`chat_providers` = {tryingopen}
- [x] `IF_FALAI_*` / `IF_NANOBANANA_ACCOUNT_TARGET` 配置删除，env 模板同步
- [x] 号池启动不再自动补号/签到；`/v1/account-pool` 无 nanobanana 强制槽位
- [x] 孤儿脚本/测试删除；E2E 断言 nanobanana 不存在
- [ ] 全量 E2E（e2e_providers.py + e2e_v12.py）在干净环境跑通并回填

### Story 2: 首页在线使用（已完成核心，待浏览器验收）

作为普通用户，我打开落地页就能直接对话，不需要先了解提供商/API。

**验收标准**
- [x] landing hero 下方 HomeChat：模型下拉（tryingopen）+ SSE 流式回复 + 骨架/空态/错误态/重试
- [x] 管理端 `/` = ChatPlayground，`/dashboard` = 仪表盘，`/chat` 兼容
- [x] `tsc -b` 0；vitest 28/28；landing build 成功
- [ ] 浏览器真实验证：落地页对话流式渲染、模型切换、错误重试（Playwright/manual）

### Story 3: tryingopen 真实调用放开（已完成配置，待 E2E 验证）

作为 agent 使用者，我发起的规划/分类/终检/记忆巩固默认走真实 tryingopen LLM。

**验收标准**
- [x] `IF_MOCK_UPSTREAM` 默认 false；planner/critic/intent/memory 真实路径可走
- [x] 测试仍注入 Mock 保证确定性，但文档不再声称「禁止真实调」
- [ ] 真实 `/v1/chat/completions` + `/v1/agent/dag/plan` 冒烟通过（本机网络可达时）

## 剩余缺口 / 待规划（Phase 4 Plan 详述）

- G1: 后台「用户视角」体验：当前首页即在线聊天已落地，但账号/配额/历史会话/分享等「用户产品」层未规划
- G2: 真实 E2E 全量：e2e_providers.py 更新后未跑；e2e_v12.py 38 段未回归
- G3: 视频真实上游：falai 下线后待另选（已从计划书 P0-3 改为开放项）
- G4: homechat 浏览器级验收（流式/错误/移动端）未自动化

## Non-Functional Requirements

- 生产稳定：下线不破坏 imagefree 生图主链路；号池数据保留可查询
- 兼容：`/chat` 旧路径不 404；`IF_TRYINGOPEN_*` 配置保留
- 可观测：/v1/providers 不再暴露下线提供商；release notes 记录验证证据
- 文档一致：README/PRD/deploy 不再把 nanobanana/falai 当当前上游

## Success Metrics

- provider 清单收敛为 2 图 + 1 对话
- 落地页/管理端首页可直接对话（真实浏览器可达）
- 后端定向 pytest 26 文件全绿 + ruff 0；email_pool 重负载单独重跑
- 3 个 v20 commit 推送 main + GitHub Release v20.0.0

## Out of Scope

- 付费套餐/支付（参考 SaaS 平台已有，本仓库不引入）
- 用户注册登录体系（保持匿名/公益 API Key 模式）
- 视频新上游接入（另行 spec）
