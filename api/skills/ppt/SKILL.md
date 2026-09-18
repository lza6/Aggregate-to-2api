---
name: ppt-outline-gen
description: PPT 大纲生成技能——把用户一句话需求分解为结构化演示文稿大纲（章节/要点/配图建议），供 ppt 场景 DAG 节点调用
scene: ppt
version: 1.0.0
security:
  run: isolated
  network: none
  approvals: none
inputs:
  topic: string 必填 演示主题
  audience: string 可选 默认 内部汇报
  duration_minutes: integer 可选 默认 10
  page_count: integer 可选
  style: string 可选
outputs:
  title: string 演示标题
  pages: array 大纲页列表
  assumptions: array 假设声明
---

## 什么时候使用

- 触发词：PPT、ppt、幻灯片、演示文稿、汇报大纲
- 不用于：PPT 文件的实际生成/渲染（那是本地工具链职责）、纯文档写作

## 核心原则

1. 一页一观点（One message per slide），标题即结论（Assertion-Evidence 结构）
2. 大纲先于美化：先锁叙事流（起-承-转-合），再配图
3. 每页标注配图建议（图表/示意/实拍），供下游生图节点消费

## 工作流

1. **需求解析**：主题/受众/时长 → 推导页数（10 分钟 ≈ 8-12 页）
2. **叙事流设计**：开场（钩子）→ 现状/问题 → 方案 → 证据/数据 → 行动号召
3. **逐页大纲**：页码 + 标题（结论式）+ 3-5 要点 + 配图建议 + 备注词
4. **自审**：叙事连贯 / 每页单观点 / 配图可生图化（能转成生图 Prompt）

## 失败模式

- 用户需求含具体数据但未提供 → 大纲用占位符 [DATA] 标注，不编造数字
- 受众/时长缺失 → 默认「内部汇报 / 10 分钟 / 10 页」并在交付时声明假设

## 交付格式

```json
{
  "title": "演示标题",
  "pages": [
    {"no": 1, "headline": "结论式标题", "points": ["要点1", "要点2"],
     "visual": "配图建议（可转生图 Prompt）", "notes": "演讲备注"}
  ]
}
```
