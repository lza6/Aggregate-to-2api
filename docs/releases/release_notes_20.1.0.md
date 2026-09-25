# v20.1.0 发行说明

> 发布时间：2026-09-26 ｜ 基于 v20.0.0（`a9ac59c`）｜ 主题：下线残留清理 + Spec Kit 007 规划

## 变更

### 清理下线残留（审计修复，-1077 行）
- 删除孤儿模块：`api/providers/action_sniffer.py`（nanobanana-pro 目标已下线）、`api/browser_pool.py`（fal.ai 专用已下线）——运行时均无调用方
- 同步删除对应测试；`/v1/account-pool` 去掉 nanobanana 硬编码空槽位（按 DB 实际 provider 汇总）
- 号池模块注释/日志去 nanobanana 化；前端签到文案与测试 fixture 换真实 provider
- PRD 01-09 版本 v7.2.0→v20.0.0、下线提供商不再作为当前上游宣传、失效配置标注

### Spec Kit 007 规划入库
- `.specify/specs/007-v20-platform-refactor/`：spec + plan + tasks（21 项）+ progress
- plan 含真机 E2E 证据、G1-G4 分阶段方案、风险回滚矩阵

## 验证记录
- 后端定向 pytest 25 文件全绿（budget_guard 280s 重跑 rc=0）
- ruff check api/ tests/ scripts/ → 0
- api 183 文件 ast 语法全 OK
- 线上复核：对话/SSE/Anthropic/agent plan/providers/models/landing/admin 均 200

## 部署
- https://imagefree.hwhcie.bond（20.204.27.154, ARM64）
- imagefree-api 8100 + cfsolver 8001（camoufox, 单次 CF ~3s）+ nginx 443
