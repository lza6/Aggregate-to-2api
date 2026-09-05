---
name: critic-review
description: 独立终检 Agent——视频/图任务完成前用干净上下文调 LLM 审查质量，与 adaptive_router 评分解耦
---

## 触发条件

- 视频生成任务完成、返回 asset 前（强制）
- 图像生成"主图/详情页/电商"场景（强制）
- 普通生图可选（IF_CRITIC_AGENT_ENABLED=1 控制）
- 自演化闭环（P2-A2）的 fitness 评分阶段

## 独立性原则（参考 video-shotcraft final-review）

- 用**干净上下文**（不复用 chat 历史的 system prompt，避免被前轮 prompt 污染）
- 独立 LLM 实例（不复用 chat 端点的 _current_meta，用专门的 critic 模板）
- 评分与 adaptive_router 的 MAB-EWMA 评分**解耦**：
  - adaptive_router 评"路由层成败"（成功率/时延）
  - critic 评"交付质量"（内容/尺寸/水印/安全）

## 审查维度（参考 hermes-self-evolution fitness.py:18 权重）

- correctness 0.5：尺寸/比例/内容是否符合 prompt
- procedure 0.3：生成流程有无异常重试/降级
- conciseness 0.2：产物有无冗余/水印/重复
- length_penalty：超时/超 token 扣分

## 输出

```json
{
  "pass": true,
  "score": 0.87,
  "issues": ["watermark_detected"],
  "recommendation": "accept" | "regenerate" | "fallback"
}
```

## 失败处理

- pass=false + recommendation=regenerate → 触发上游重生成（最多 2 次）
- pass=false + recommendation=fallback → 降级备用 provider
- LLM 调用失败 → 降级跳过 critic，记 warn（不阻塞主链路）

## 反模式

- 不在图生图互斥租约期内调用
- 不用付费上游做 critic（用 tryingopen 免费 LLM）
- 不把 critic 评分混入 adaptive_router 的路由决策（职责分离）
