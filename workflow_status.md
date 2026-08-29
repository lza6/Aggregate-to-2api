# 主控台账 · 听风AI 闭环任务（v6.5.1 每账号消耗积分 + Vue3 公开首页 + 在线生成）

> 分支约束：**仅 main，禁止新建分支**。生产部署/推送/发版均已获用户授权。
> 更新策略：只在节点状态发生实质变化时更新。

## 任务契约（用户原始诉求，本轮聚焦）
1. 公开首页（/ 现为单文件 docs.html）迁到 **Vue3**，不用单 HTML，去掉「公开页无鉴权出图生成器」；
2. 号池看板：显示「注册在哪个阶段 + 每阶段耗时」「累计签到/累计获得积分/存活天数」（前端同步 + 后端补注册阶段/耗时接口）；
3. 内网私有地址**原始 IP 打码/不显示**，防恶意；
4. Token M/B/K、总量主卡、401/403 不再过 CF、私网归类（已落地，回归保留）；
5. 真实 E2E/验收/审计 + 部署上线 + 推送 main + 发版 release/tag。

## 验收标准表
| ID | 标准 | 证据 | 状态 |
|----|------|------|------|
| V1 | 公开首页为 Vue3 应用（非单 html），`/` 由 Vite Vue 构建产物提供 | landing/build exit0 + TestClient / 返回 SPA shell + 源码无 docs.html 挂 / | ✅ 已实现 |
| V2 | 公开首页不暴露无鉴权出图生成器 | landing 仅状态展示+引导 /admin /docs，无生成表单 | ✅ 已实现 |
| V3 | 号池显示注册阶段 + 每阶段耗时 | /v1/account-pool.live_registration{stage_label,stage_durations} + Accounts.tsx 渲染 | ✅ 已实现 |
| V4 | 号池明细含累计签到/累计获得积分/存活天数 | /v1/account-pool item{checkin_total,credits_earned_total,age_days} + Accounts.tsx 列 | ✅ 已实现 |
| V5 | 私网/回环 IP 原始地址打码，仅显示「内网」/「本机」 | task_to_public 内网→client_ip=None；单测验证 | ✅ 已实现 |
| V6 | Token M/B/K、总用量主卡、401/403 零 CF、私网归类回归 | 单测 + 线上探针 | ✅ 已验证 |
| V7 | Vue3 前端 tsc/build/真实浏览器 E2E 通过 | landing build exit0 + playwright 6/0；frontend tsc 0 + smoke 12/0 | ✅ 已验证 |
| V8 | 部署更新到线上 | docker 健康 + / 换新 | ⏳ 待执行 |
| V9 | 推送 main + 创建 release/tag | git tag v6.5.1 + GitHub Release | ⏳ 待执行 |

## 任务图
```
[后端:私网IP打码] ─┐
[后端:注册阶段/耗时] ─┼─> [React号池画像列] ─> [Vue3公开首页构建] ─> E2E/审查 ─> 部署 ─> 推送+发版
[Vue3:去公开生成器] ─┘
```

## 阻塞项
- 号池「全部账号签到」：dead 号（cookie 失效无密码/续期失败）客观不可签，真实监督范围 = ok/active；剩余为补号能力上限，非缺陷。

## 最近更新
- 2026-08-29 **v6.5.1 每账号消耗积分闭环**：nanobanana 生成成功按上游 encodeImageCost 扣减账号积分并累计 credits_used_total/images_used/last_used_at；号池明细新增「累计消耗积分/出图次数」列；后端单测 19p + 前端 E2E 6/0；线上 imagefree-api:6.5.1 healthy。
- 2026-08-29 **盘账**：docs.html 零散视觉已修；4 个真缺口（注册阶段/耗时接口、私网裸 IP、React 号池画像列、公开页无鉴权生成器）已完整落地。
