---
name: image-quality-check
description: 图像生成交付前的质量自检——尺寸/比例/水印/重复图检测，供 critic 终检 Agent 调用
---

## 触发条件

- 图像生成任务完成、返回 asset_url 前
- 用户请求含"主图/详情页/电商"等高质量要求关键词时强制触发
- 普通生图可选触发（IF_CRITIC_AGENT_ENABLED=1）

## 检查项

1. **尺寸/比例**：返回图实际尺寸与请求 aspect_ratio 一致（容差 ±2px）
2. **水印检测**：扫描右下角 100x100 区域是否含水印（公益上游常见）
3. **重复图**：与近 10 张同 prompt 产出做 pHash 比对，相似度 >0.95 标记重复
4. **内容安全**：返回图经 tryingopen 上游 vision 模型过审（可选，IF_CRITIC_VISION_ENABLED=1）

## 失败处理

- 尺寸/比例不符 → 标记 quality_issue，返回 asset 但附 warning
- 水印检测命中 → 标记 watermark_detected，触发上游重生成（最多 2 次）
- 重复图 → 标记 duplicate，降级到备用 provider 重试
- 内容安全不通过 → 拒绝返回，记 DLQ

## 反模式（何时不该调用）

- 图生图（img2img）互斥租约期内不调用（避免与 edit_lease 冲突）
- 用户明确标注"快速出图不求质量"时不调用
- 测试 IF_MOCK_UPSTREAM=1 模式下只走尺寸/比例检查，跳过 vision 过审
