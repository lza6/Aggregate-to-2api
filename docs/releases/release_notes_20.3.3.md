# v20.3.3 发行说明 — 教学化 explain 接线 + 假功能注释修正

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🎓 DAG 教学化释义真接线（P2 审计闭环）

- **explain_templates 从「有测试未接线」→ 真闭环**：`GET /v1/agent/dag/{run_id}` 每节点附加 `explain` 字段
  （what/why/io 大白话：任务入口/大模型/终检/工具/记忆/检索/图像/人机 8 类节点）
- 开关 `IF_AGENT_EXPLAIN_ENABLED=1`（缺省开），0=关闭零行为变化
- 向后兼容：新增字段不破坏现有契约；失败静默不崩主链路
- 用途：门户 Agent 卡/管理台可展示「为什么这样规划」教学化解释

## 📝 假功能注释修正（P2 审计）

| 文件 | 修正前（误导） | 修正后（事实） |
|------|--------------|--------------|
| video_provider.py | 「IF_MOCK_UPSTREAM=1 → Mock；真实路径后置」 | 「视频恒 Mock（falai 已下线/上游未接入），开关无效」 |
| generate.py _guard | 「必须携带有效 API Key」 | 「公益开放无 Key 可调（v7.7.1 起），IF_API_KEYS 可选启用」 |

## ✅ 验证
- 后端 agent_dag/agent_explain/gallery 27 passed
- 本地 _attach_explain 验证：scene/llm/critic 节点全部附加 explain
- 生产 DAG 详情 E2E（部署后验证 explain 字段真实返回）

## 📋 文件清单
- api/routes/agent_dag.py（explain 接线 + _attach_explain）
- api/providers/video_provider.py、api/routes/generate.py（注释修正）
- 版本全链 bump 20.3.3
