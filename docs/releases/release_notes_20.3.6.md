# v20.3.6 发行说明 — 管理台 explain 消费 + 恢复演练自动化

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🎓 管理台 explain 消费闭环（J1）

- 门户 v20.3.4 已消费 explain，本轮**管理台 /admin Agent 页闭环**：
  - DagGraph 节点 `<title>` tooltip 优先用后端 `node.explain`（fallback 硬编码 NODE_HINT）
  - DagTrace 详情面板新增「教学化释义」区块（这步为什么/做什么，完整 what/why/io）
  - `DagNodePublic` 类型补 `explain?: string | null`

## 🛡️ 备份恢复演练自动化（J2）

- `scripts/restore_drill.py`（非破坏性恢复演练，区别于 restore_db.py 覆盖恢复）：
  - 最新备份 → 临时目录 → PRAGMA integrity_check + requests 行数验证 → 清理
  - cron 每周日 04:00 自动演练（imagefree/dag_runs/queue）
- 服务器实测：imagefree（requests=20）+ dag_runs 全部 integrity=ok

## ✅ 验证
- frontend build 全绿（类型 + DagGraph/DagTrace 编译通过）
- 恢复演练服务器实测 2/2 通过（自动化验证备份可恢复）
- 生产 /admin Agent 页 E2E（部署后验证 explain 展示）

## 📋 文件清单
- frontend/src/api/agent.ts、frontend/src/components/DagGraph.tsx（explain 消费）
- scripts/restore_drill.py（恢复演练脚本）
- 版本全链 bump 20.3.6
