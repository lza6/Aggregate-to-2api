---
name: prompt-refine
description: 用户意图模糊时用 tryingopen 上游 LLM 把裸 prompt 细化为 provider+style+size 结构化参数
---

## 触发条件

- 用户 prompt 长度 <10 字符 或含"随便/看着办/好看就行"等模糊词
- intent_classifier 标注 confidence <0.6 的模糊意图
- 用户未指定 aspect_ratio 且 prompt 含"横屏/竖屏/方图"隐含意图时

## 执行流程

1. 接收原始 prompt + 对话历史（最近 3 轮）
2. 调用 tryingopen 上游 LLM（chat_collect），系统提示词约束输出 JSON：
   ```json
   {"refined_prompt": "...", "style": "...", "aspect_ratio": "16:9", "resolution": "1K"}
   ```
3. 校验 JSON schema（refined_prompt 非空，aspect_ratio 在 ASPECT_RATIOS 白名单）
4. 失败回退：原始 prompt + 默认 aspect_ratio=1:1

## 反模式

- prompt 已含明确 aspect_ratio/size 时不调用（避免覆盖用户显式选择）
- 付费上游（fal.ai）不调用此 skill（付费 API 红线：真实预算=0 时禁 LLM 细化）
- 流式 chat 端点不调用（只对 generate 端点的非流式请求触发）

## 依赖

- tryingopen 上游 LLM（免费，无付费红线冲突）
- intent_classifier 的 confidence 信号（P1-A2 接线后可用）
