# v20.3.8 发行说明 — 管理台 DAG 列表 explain 缺口修复

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🐛 真实缺口修复（L3 管理台 explain E2E 发现）

**问题**：管理台 /admin/agent 的 RunCard 用 `GET /v1/agent/dag?limit=`（列表端点）渲染节点，
此前 explain 只附加在详情端点（`GET /v1/agent/dag/{id}`）→ 列表数据节点无 explain → UI 教学化释义无法展示。

**修复**：列表端点每 run 节点同样 `_attach_explain`（与详情一致），
管理台节点详情面板的「教学化释义」区块真实可显示。

## ✅ 验证
- 后端 agent_dag_routes + agent_explain 19 passed（无回归）
- 生产列表端点节点 explain present=True（部署后验证）
- 管理台 /admin/agent 点击节点 → explain 区块展示（E2E 复验）

## 📋 文件清单
- api/routes/agent_dag.py（dag_list 附加 explain）
- 版本全链 bump 20.3.8
