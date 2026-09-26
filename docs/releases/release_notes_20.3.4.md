# v20.3.4 发行说明 — 教学化 explain 前端闭环 + 图生图超时降级

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🎓 教学化 explain 前端闭环（G1）

- 后端 v20.3.3 已返回节点 explain，本轮**前端 PortalAgent 消费闭环**：
  - run 成功后节点 explain（what/why/io 教学化释义）回填到计划展示
  - 节点改为可折叠 `<details>`（▸ 展开），点击查看「为什么这样规划」
  - 教学化功能从「后端就绪」→ **用户可见 UI 全链路**

## ⏱️ 图生图超时降级（G2）

- PortalGenerate 图生图轮询：
  - busy 态显示**已等待时长**（`分:秒`）
  - **15 分钟超时**自动降级提示「处理超时，请稍后到管理台查看或重新提交」（防无限等待）
- 与后端 `EDIT_TIMEOUT=600s` error 兜底一致（后端先 error，前端超时提示兜底）

## ✅ 验证
- landing build 全绿（44 模块）
- G2 前后端闭环：后端 poll_edit_status 超时→mark_finished(error)；前端 15min 超时提示
- 生产 E2E（部署后）：Agent 卡 explain 可展开 + 图生图 busy 等待时长

## 📋 文件清单
- landing/src/components/PortalAgent.vue（explain 折叠展示）
- landing/src/components/PortalGenerate.vue（等待时长 + 15min 超时）
- 版本全链 bump 20.3.4
