---
name: account-pool-lifecycle-fsm
description: Account Pool 2.0 多源邮箱与账号生命周期状态机 (FSM) 运维及排障规范
version: 5.0.0
last_verified: 2026-08-25
---

# Account Pool 2.0 运维与排障规范

## 1. 架构拓扑与状态机 (FSM)
- **多源邮箱**：`BaseMailSource` 支持 `LinshiMailSource`、`MailTmSource`、`GuerrillaMailSource`、`CustomImapSource`、`Do22Source`、`TempMailSource`。
- **动态选源**：根据优先级、成功率（Laplace平滑）与 429 冷却动态降级切源。
- **账号生命周期**：
  `unregistered` -> `registering` -> `active` (`ok`) -> `working` -> `cooling` (`exhausted`) -> `dead` (`banned`)。
- **租约管理**：使用 `async with account_pool.lease(provider) as acc:` 安全借号与异常熔断。

## 2. 自动化验证命令
```bash
# 验证多源邮箱策略
python -m pytest tests/test_email_pool.py -v

# 验证账号 FSM 状态流转与延寿唤醒
python -m pytest tests/test_account_pool.py -v

# 验证注册 Worker 自适应分类退避
python -m pytest tests/test_registerer_adaptive.py -v
```

## 3. 监控快照与看板
- `/healthz`、`/v1/stats`、前端「号池」页：
  - 各提供商状态：`total`, `ok`, `working`, `cooling`, `dead`, `registering`, `credits`。
  - 邮箱源状态：各源故障计数、评分与冷却剩余时间。
