# workflow_status.md — 终局闭环总审计与全栈交付工作流（v3.0）

> 更新日期：2026-08-27 · 当前阶段：终局深度闭环与全链路审计 · 目标：生产级高可用/高并发/多模态文本+生图统一网关

---

## 1. 任务背景与核心契约 (Mission Charter)

将 `imagefree-2ai` 全面升级为同时具备 **生产级 AI 图像生成网关** 与 **TryingOpen 匿名多模型文本对话/Agent 网关** 的统一中枢。
支持：
- 图像链路：Turnstile 自动求解 + Worker 优先级队列 + 住宅/免费代理池 + 号池自动维护。
- 对话链路：13+ 开源模型（含 GLM-5.3-Flash / Qwen3.8 / Kimi-K3 等）+ 思考链流式 + 自定义/原生工具调用 + 多模态 Vision + 20条/h/IP 限流突破（代理池动态轮换）。
- 接口兼容：OpenAI `/v1/chat/completions` + Anthropic `/v1/messages` + 全站实时用量监控与额度动态预测。
- 交互与体验：全站仪表盘深度整合 + 现代化 ChatPlayground 在线体验 + 故障自愈/熔断/降级。

---

## 2. 需求追踪矩阵 (Requirements Traceability Matrix - RTM)

| 编号 | 需求项 | 分类 | 涉及模块/文件 | 当前状态 | 验证证据 | 闭环动作 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-01** | TryingOpen 文本/对话接入与流式解析 | 核心后端 | `api/providers/tryingopen.py` | ✅ 已闭环 | `tests/test_tryingopen.py` (7/7) + 真实 E2E | 支持 17 种 SSE 事件，流式/非流式自适应 |
| **REQ-02** | 上游模型动态目录自适应抓取 | 核心后端 | `api/providers/tryingopen.py` | ✅ 已闭环 | 真实抓取 13 个模型（含 glm-5.3-flash） | 后台定时拉取 + 静态 13 模型坚固回退 |
| **REQ-03** | 工具调用模拟与原生工具提取 | 核心后端 | `api/providers/tryingopen.py` | ✅ 已闭环 | `test_tool_call_emulation` 通过 | 注入 `[TOOL CALLING MODE]` + 强容错正则与 JSON 解析 |
| **REQ-04** | 多模态图片/文件输入支持 | 核心后端 | `api/providers/tryingopen.py` | ✅ 已闭环 | `test_convert_messages_folds_system_images` | 转换为 TryingOpen parts 结构，支持 data URI/URL |
| **REQ-05** | 单 IP 20次/h 限流突破 | 基础设施 | `api/proxy_pool.py`, `free_proxy_fetcher.py` | ✅ 已闭环 | 实测抓取 300+ 注入 84 个健康代理 | 每请求轮换代理 + 429 自动阶梯冷却与重试 |
| **REQ-06** | OpenAI `/v1/chat/completions` 标准端点 | API 层 | `api/routes/chat.py` | ✅ 已闭环 | `test_chat_routes.py` 全部通过 | 流式 chunk、非流式 object、usage 记录 |
| **REQ-07** | Anthropic `/v1/messages` 兼容端点 | API 层 | `api/routes/chat.py` | ✅ 已闭环 | `test_chat_routes.py` 全部通过 | 适配 Claude Code / Continue / Cursor 直连 |
| **REQ-08** | 全站实时用量追踪与数据持久化 | 数据层 | `api/chat_usage.py`, `api/db/core.py` | ✅ 已闭环 | `chat_usage` 表与索引建立完成 | 记录 Prompt/Completion/Reasoning Tokens 及时延 |
| **REQ-09** | 仪表盘用量卡片与图表整合 | 前端 UI | `frontend/src/pages/Dashboard.tsx` | ✅ 已闭环 | TypeScript 0 错误 + 构建打包通过 | 嵌入 24h 聊天、Token、工具调用、动态剩余可用额度 |
| **REQ-10** | 在线聊天工作台 (ChatPlayground) | 前端 UI | `frontend/src/pages/ChatPlayground.tsx` | ✅ 已闭环 | 构建产出独立 Chunk | 懒加载、思考过程折叠、会话持久化、导出 Markdown |
| **REQ-11** | 生产部署资产同步与环境模板 | 工程化 | `deploy/`, `.env.example` | ✅ 已闭环 | `scripts/sync_deploy.py check` 一致 | 同步 Docker 容器编排及配置参数 |

---

## 3. 终局审计与自查缺陷修复清单 (Defect & Remediation Log)

- **[P1-01] 修复 TryingOpen 工具调用解析误选内部参数对象问题**：优化 `_last_json_object` 优先匹配外层包含 `tool_call` / `tool` 的对象，防止 arguments 覆盖。
- **[P1-02] 修复前端 BarChart `metricLabel` TS6133 未使用告警**：将参数完整注入 Tooltip 自定义渲染组件。
- **[P1-03] 修复前端 Accounts 页面分页属性类型不匹配**：扩展 `AccountPoolData` 接口声明 `items_total`, `total_pages` 等字段。
- **[P1-04] 修复免费代理抓取器单元测试初始化断言**：确保 `_client` 声明周期安全。

---

## 4. 后续自动化执行计划 (Next Steps)

1. **全面代码与架构深审 (Deep Code Review)**：核对并发安全、超时逃逸、SQL 防护与资源释放。
2. **编写端到端高并发压测与异常穿透测试**：验证极端网络与限流下的弹性。
3. **架构资产与 ADR 沉淀**：编写标准规范文档与交付 SOP。
4. **生成交互式 HTML 终结报告与理解测验**。
