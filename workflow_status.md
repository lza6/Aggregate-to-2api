# workflow_status.md — 终局闭环总审计工作流（v2）

> 更新日期：2026-08-24 · 当前版本：v4.2.1 · 生产：imagefree.tingfengai.art (ok)

## 三项并行的只读深度审计已完成

已启动 3 个子代理（Backend / Frontend-Security / Deploy-Docs-Tests）完成全量只读审计，结果如下。

### 审计结论汇总

| 审计 | P0 | P1 | P2 | P3 |
|------|----|----|----|----|
| 后端逻辑 | 8 | 10 | 10 | 10 |
| 前端/安全 | 4 | 10 | 7 | 1 |
| 部署/文档/测试 | 0 | 10 | 12 | 0 |
| **合计** | **12** | **30** | **29** | **11** |

## P0 阻塞问题清单（须全部修复）

### 后端（backend audit）
| # | 文件 | 问题 | 状态 |
|---|------|------|------|
| P0-1 | dispatch.py:127 | `_SSE_SUBSCRIBERS` 无锁并发读写 + QueueFull 静默吞 | 待修 |
| P0-2 | dispatch_edit.py:248-257 | **URL 图片下载后未回填 image_bytes/image_bytes_list → None 提交崩溃** | ✅ 已修 |
| P0-3 | dispatch_edit.py:152 | imagefree 图生图 task 未加入 _PROVIDER_TASKS 托盘（shutdown 无法优雅取消） | 待修 |
| P0-4 | dispatch_edit.py:267-270 | imagefree 多图静默丢弃第 2/3 张（应明确报错不支持） | 待修 |
| P0-5 | worker.py:199 | 动态水位 `0.0 * solve_time` 恒为 0 → dynamic watermark 失效 | 待修 |
| P0-6 | dispatch.py:196 | `req.priority or 2` 吞掉 admin 优先级 0 | 待修 |
| P0-7 | sse_events.py:156 | `asyncio.ensure_future` 孤儿 task 不持有引用，shutdown 丢事件 | 待修 |
| P0-8 | worker.py _finish + dispatch.py broadcast | **终态事件双重发布（publish 两遍）** | 待修 |

### 前端/安全（frontend-security audit）
| # | 位置 | 问题 | 状态 |
|---|------|------|------|
| P0-1 | deploy/.env.example + git历史 | **Kookeey 住宅代理真实凭据入库**（metric 风险，须轮换+清历史） | 待修 |
| P0-2 | docs.html:1455 | **画廊密码硬编码 `tfadmin2024` 明文** | 待修 |
| P0-3 | main.py CORS | `allow_origins=["*"]` 全开 | 待修（收敛为配置） |
| P0-4 | dispatch.py + imagefree_client.py | SSRF DNS rebinding 窗口（解析后重连主机名） | 待修 |

## P1 高优先级（择要）
- 前后端契约不对齐（api.ts 6 处字段缺失/错位、DLQ message vs detail、Tasks 无分页）
- README 版本 3.1.0→4.2.1 + 架构图/目录结构/端点表过时
- sync_deploy.py 白名单缺 9 个新模块（✅ 已修）+ contracts.py
- requirements.txt 缺 prometheus-client
- docker-compose 版本号 v2.3.0→v4.2.1、cfsolver 端口未映射 host 导致脚本无法连
- 8+ 新模块无测试（sse/dispatch/dispatch_edit/meta/handlers/bg_tasks/models/contracts）
- test_async_submit_and_poll 整组跑 fail 单独 pass（session scope 共享污染）
- CI 三处问题：-x 跑两遍、`|| true` 使 ruff 形同虚设、无 sync_deploy 校验

## 修复顺序（按影响）
1. ✅ P0-2 URL 图片下载回填（已修）
2. P0-6 admin 优先级 0 被吞 → 改为 `2 if priority is None else priority`
3. P0-8 SSE 终态双发 → _finish 去掉 publish，bcast 全权
4. P0-3 imagefree edit task 托盘
5. P0-4 imagefree 多图明确报错
6. P0-5 worker dynamic watermark
7. P0-1 _SSE_SUBSCRIBERS 加锁
8. P0-2 画廊密码：docs.html 去除硬编码 → 服务端 /v1/meta 下发
9. P0-3 CORS 收敛
10. P0-4 SSRF DNS rebinding
11. P0-1 Kookeey 凭据：占位符替换 + README 提示轮换 + git filter 清理说明
12. P1 契约/测试/README/CI 修复

## 节点验收标准
每修复一个 P0/P1，须：代码证据 + 相关测试通过 + 前端若涉及则重新 build + 部署 smoke。