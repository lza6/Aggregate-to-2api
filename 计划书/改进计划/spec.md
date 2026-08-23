# v3.1.0 终局交付契约（Spec）

## 问题与背景

听风AI 已在 https://imagefree.tingfengai.art 公益运行。本轮要把可观测性、运维闭环、合规捐赠、以及生产级数据一致性缺陷一次交付到可发布状态。

## 用户与调用方

- 公益调用方：`POST /v1/generate` / `async` / `edit`
- 运维：`/v1/diagnostics`、`/v1/slow`、Dashboard Worker 健康卡
- 捐赠用户：首页「请我喝咖啡」+ `/v1/honor`

## 目标

S-1~S-11、S-13~S-15 真实落地；核心生成链路不再卡 pending；文档与 deploy 同步；GitHub Release 存在。

## 非目标

- Redis/Kafka/CDN/分片（v4+ 容量主题，无当前证据不引入）
- 管理面鉴权默认开启（破坏零鉴权公益部署）
- 真实付费上游出图（默认 0 额度消耗）

## 验收

- 单元层关键文件绿且进程能退出
- 集成 txt2img / async flow 绿
- `python scripts/sync_deploy.py check` 零 diff
- README / workflow_status / 计划书 与真实行为一致
