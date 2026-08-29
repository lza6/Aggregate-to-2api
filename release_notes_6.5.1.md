# 听风AI v6.5.1 发布说明

## 每账号出图消耗积分（号池明细透明化）
- `nanobanana.generate` 成功后按上游 `encodeImageCost` 扣减该账号积分，并累计「消耗积分 / 出图次数 / 最近出图时间」画像。
- 逆向自 nanobanana js `CREDITS_PER_IMAGE` 常量：pro 1K=4/4K=14，nano-2 1K=5/2K=8/4K=12，lite 1K=3，gpt-image-2 1K=6/2K=10/4K=14，seedream-pro 1K=7/2K=14，grok fast=5/quality=6/edit=5，z-image=2，默认 4。
- `account_pool.consume_credits()`：`credits=MAX(0, credits-amount)` + `credits_used_total/images_used/last_used_at` 累计落库（新增 3 列，自动迁移）。
- `/v1/account-pool` 明细新增 `credits_used_total / images_used / last_used_at`。
- React `Accounts.tsx` 新增列：累计消耗积分、出图次数；版本 6.5.1。

## 验证
- 后端单测：`test_consume_credits_updates_usage_profile`（扣减/下限/非法 no-op）+ `test_image_credit_cost_mapping`（9 档成本映射）全绿；account_pool 19p。
- 前端 tsc 0 + build exit0；线上真实浏览器：号池「累计消耗积分/出图次数」列 + 在线生成模型下拉(33 档) 6/0。
- 部署：`imagefree-api:6.5.1` / `imagefree-cfsolver:6.5.1` healthy；sync_deploy 一致。
