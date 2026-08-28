# 主控台账 · 听风AI 闭环任务

> 分支约束：**仅 main，禁止新建分支**。生产部署/推送/发版均已获用户授权。
> 更新策略：只在节点状态发生实质变化时更新。

## 任务契约（用户原始诉求）
1. 完整落地闭环剩余任务，真实 E2E 测验 / 验收 / 审计
2. 部署更新到线上
3. 提交推送到仓库，创建发行版（release/tag）
4. 仅 main 分支

## 验收标准表
| ID | 标准 | 证据 | 状态 |
|----|------|------|------|
| A1 | 前端 UI「统计用量显示总用量」已落地 | docs.html cu-total 主卡 + Dashboard chat 卡 | ✅ 已实现 |
| A2 | 前端 footer/版本号去重（不再显示过期 v4.3.3） | Layout.tsx 注入 __APP_VERSION__；dist 无 4.3.3 | ✅ 已验证 |
| A3 | 聊天用量 Token 以 M/B/K 显示 | fmtTokens/formatTokens 含 B 档、K 大写 | ✅ 已验证 |
| A4 | 号池「所有可签到账号完成签到」监督生效 | account_pool 单测 17 passed | ⏳ 后台审计中 |
| A5 | 401/403 不再重试浪费 CF（回归） | retry_policy 单测 49 passed | ✅ 已验证 |
| A6 | 前端 e2e-smoke 通过 | `npm run smoke` 12/0 | ✅ 已验证 |
| A7 | 后端 pytest 通过 | 定向单测全 pass（base64_separation 为既有 hang） | ⏳ 后台审计中 |
| A8 | 前端生产构建通过 | `tsc -b && vite build` exit 0 | ✅ 已验证 |
| A9 | 部署更新到线上 | 待执行 | ⏳ |
| A10 | 推送 main + 创建 release/tag | 待执行 | ⏳ |

## 任务图
```
[Audit-Frontend] ─┐
[Audit-Backend ] ─┼─> 修复(串行, main) ─> 验证(构建/单测/冒烟) ─> 审计报告 ─> 部署 ─> 推送+发版
[Audit-E2E    ] ─┘
```

## 阻塞项
- base64_separation.py 测试在本地 hang（沿用 session event-loop+worker 生命周期，需 mock cf_solver 常驻 + 全量 collect；CI 环境通过），非本次引入缺陷。

## 最近更新
- 2026-08-28 22:00 **全部闭环完成**：提交 `b1a61d2` 已推送 main；tag `v6.4.1` 已推送；release 创建成功；线上部署完成（api:6.4.1 healthy、cfsolver:6.4.1 healthy、/admin dist 已换新、docs 页脚 v6.4.1）；真实 E2E 打点：无key/错key 均 401 且零 CF 浪费。
