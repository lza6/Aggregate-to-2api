# 004-final-audit-v76 Spec — 全量审计闭环（v7.6）

> 依据 spec-kit-skill 7 阶段。宪法：.specify/memory/constitution.md。
> 前置：003-final-closure（v7.3）已交付；本轮为新审计发现的增量问题闭环。

## 背景与触发
用户报两个生产 bug（实时日志 WS 坏 + AI 对话 null:[object Object]），修复 Bug1 后要求做一次终局闭环总审计。4 个并行审计 agent（前端/后端/部署/测试）产出全量问题清单，反向核查 agent 确认部署断言全部成立。

## 功能需求（FR）

- **FR-1 幂等性 TOCTOU 根治（P0）**：`db/core.py:940` `INSERT OR REPLACE` + `dispatch.py:210-245` get→create→save 两步非原子 → 同 key 并发返回不同 task_id。改 `ON CONFLICT DO NOTHING` + 检查 rowcount，单 SQL 原子化。
- **FR-2 非 imagefree 生成任务 shutdown drain（P0）**：`dispatch.py:180` `_PROVIDER_TASKS` set 在 lifespan shutdown 未 drain → 重启丢任务。lifespan 加 drain phase。
- **FR-3 WS ping/pong 契约对齐（P1）**：前端 Logs.tsx 发 `{"type":"ping"}` JSON，后端 admin.py:514 期望字面量 `ping`。改前端发裸串 + heartbeat 移到 onmessage 收 pong 后。
- **FR-4 fetchLogs 带 adminHeaders + LogEntry 类型修正（P1）**：misc.ts:73 无 adminHeaders → 401；LogEntry.ts:number 与后端 timestamp:str 不符。
- **FR-5 Dashboard adminKey 来源修正（P1）**：Dashboard.tsx:37 用 chat Key 当 admin Key 调 /v1/chat/auth/status，独立 IF_ADMIN_KEYS 时 401。
- **FR-6 Security 分页闭包修复（P1）**：Security.tsx goPage/saveKey 过期闭包，补 useEffect 响应 page 变化。
- **FR-7 聊天 429 语义保留（P1）**：chat.py _chat_collect except Exception 把 ProviderRateLimited 降级 503，补 except ProviderRateLimited → 429。
- **FR-8 priority=0 权限校验（P1）**：dispatch.py priority=0 进 admin 队列无 check_admin_key，普通用户可占 admin 队列。
- **FR-9 部署一致性修复（P1）**：deploy/pyproject.toml 6.7.0→7.2.0；ci.yml vs deploy.yml cov 80/70 统一；IF_REQUESTS_PER_MINUTE 三处默认对齐；README cf_solver 路径修正；sync_deploy no-op step 清理。
- **FR-10 测试盲区补齐（P1）**：幂等并发测试、shutdown drain 测试、WS ping 契约测试、fetchLogs 测试、chat 429 测试。
- **FR-11 文档全量同步**：verification-log 追加本轮、改进指南回写、HTML 变更报告 + 测验、workflow_status 终态。
- **FR-12 持久化验证记录**：verification-log 补「已验证勿重跑」结论，避免下轮重复审计。

## 验收标准（AC）
- AC-1 幂等并发测试：同 key 两次并发提交返回同一 task_id，无孤儿任务。
- AC-2 shutdown drain：_PROVIDER_TASKS 在 lifespan ③ 之后、⑨之前 drain，超时 5s。
- AC-3 WS ping：前端发裸串 `ping`，后端回 `pong`，heartbeat 仅在收 pong/log 后更新。
- AC-4 fetchLogs 带 adminHeaders，LogEntry.timestamp:string。
- AC-5 Dashboard 用 getStoredAdminKey。
- AC-6 Security page 变化触发 reload。
- AC-7 chat ProviderRateLimited → 429 + Retry-After 语义。
- AC-8 priority=0 需 admin key，否则 403。
- AC-9 版本 7 处一致（含 deploy/pyproject.toml）；cov 门禁统一；README 路径正确。
- AC-10 新增测试全绿。
- AC-11 文档同步 + HTML 报告 + 测验 10 题。
- AC-12 verification-log 有「勿重跑」结论段。

## 范围外
- 真实付费 API E2E（用户豁免）
- Redis/MQ/分片实际引入（公益单机，仅评估，见 docs/architecture-evolution.md）
- cf_solver page_count 生产灰度（需观察窗口）
- Dockerfile 非 root 降权（涉及 data 卷属主，列为后续部署加固项，本轮记录）
