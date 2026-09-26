# v20.3.10 发行说明 — 后端测试环境真相澄清 + 全量基线

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🔍 认知修正（重要）

**前几轮记录的「后端 pytest 环境债（EXIT=4）」实际是误判**：
- 根因：误用了不存在的测试文件名（test_auth.py 应为 test_auth_ip.py；test_fmt.py 不存在）
- pytest 对不存在路径返回 exit 4 且本环境静默无输出 → 误导为环境崩溃
- 真相：`.venv`（Python 3.11.13）pytest 一直能正常跑

## 🧪 全量测试基线（分批次实测）

- 第一批 47 文件：除 1 个预存隔离 flaky 外全绿
- 预存 flaky：test_account_pool::test_dashboard_counts_reflect_state（单独跑 PASSED，全量文件跑时跨测试污染）
  - 根因：AccountPool 内部跨 tmp_path 实例共享状态（测试隔离缺口，非本轮引入）
- 前端 vitest 全量串行 296/296 全绿（v20.3.9 已闭环）

## 📋 文件清单
- docs/verification-log.md（环境真相澄清 + 全量基线记录）
- 版本全链 bump 20.3.10
