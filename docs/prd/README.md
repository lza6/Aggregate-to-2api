# 听风AI(imagefree-2ai)产品需求文档与技术文档套件

> 版本:v7.2.0(代码标注,演进中) · 最后更新:2026-09-03 · 全部简体中文撰写
> 文档与代码实现一一对应,所有断言可由 `api/` 源码与 `deploy/docker-compose.yml` 验证。

## 文档结构

| 编号 | 文件 | 内容 |
|------|------|------|
| 01 | [产品概述](./01-product-overview.md) | 简介、问题陈述、目标、范围、术语表 |
| 02 | [功能需求](./02-functional-requirements.md) | 图像生成/对话/号池/代理池/可观测性等功能需求清单 |
| 03 | [非功能需求](./03-non-functional-requirements.md) | 性能、可用性、安全、可维护性、合规等非功能指标 |
| 04 | [用户故事](./04-user-stories.md) | 典型用户旅程与使用场景 |
| 05 | [架构概览](./05-architecture-overview.md) | 系统架构图、分层、核心组件、数据流 |
| 06 | [技术规格](./06-technical-specifications.md) | 技术栈、配置体系、数据模型、状态机 |
| 07 | [API 与接口](./07-api-reference.md) | 全部端点契约、请求/响应、错误码 |
| 08 | [安全与合规](./08-security-compliance.md) | 鉴权、限流、安全头、数据保护、红线 |
| 09 | [部署与运维](./09-deployment-operations.md) | Docker 编排、环境变量、监控、备份、SOP |

## 项目定位

**听风AI(imagefree-2ai)** 是一个公益运行的**多提供商 AI 图像/视频/对话生成开放网关**。它通过逆向号池、Cloudflare Turnstile 自动求解、邮箱池自动注册、代理池轮换等工程化手段,把多个免费/积分制上游(imagefree.net、aifreeforever、nanobanana-pro、fal.ai、tryingopen)聚合为统一 OpenAI/Anthropic 兼容接口,对外提供免费、开放、高并发生成服务。

- **代码入口**:`api/main.py`(FastAPI 应用组装,`app = FastAPI(version="7.2.0")`)
- **配置入口**:`api/config/__init__.py`(pydantic-settings,IF_ 前缀环境变量)
- **部署入口**:`deploy/docker-compose.yml`(cfsolver + api 双服务)
- **公网地址**:`https://imagefree.tingfengai.art`(腾讯云东京 + Caddy 自动 HTTPS)
- **管理面板**:`/admin`(React + TypeScript SPA)
- **落地页**:`/`(Vue3 SPA)

## 阅读对象

- **站长/运维**:从 01 → 09 顺序阅读,重点看 03(非功能指标)、08(安全)、09(部署运维)
- **接入方/调用者**:重点看 07(API 与接口),配合 02(功能需求)了解能力边界
- **开发者/贡献者**:重点看 05(架构)、06(技术规格)、07(API),配合源码 `api/` 理解实现
- **产品/评审**:从 01 → 04 顺序阅读,了解产品定位与用户价值

## 约定

- 所有代码标识符、路径、命令、环境变量、错误码保留英文(如 `POST /v1/generate`、`IF_WORKERS`、`AUTH.001`)
- 版本号以 `api/main.py` 的 `version="7.2.0"` 与 `pyproject.toml` 的 `version = "7.2.0"` 为准
- 性能指标以 `docs/architecture-evolution.md` 与 `deploy/README.deploy.md` 记录的实测值为准(50 并发 ≈270 RPS、单 token 求解 ≈5s)
- 文档遵循"证据优先":未验证项标注"待验证",不宣称"无 bug"或"可上线"
