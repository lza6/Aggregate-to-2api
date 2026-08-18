# 听风AI · 多提供商 AI 图像生成网关

> **逆向号池 + 自动注册 + 免费代理池 + 高并发异步队列** — 聚合多家 AI 图像生成站，统一 OpenAI 风格 API。

![听风AI 首页截图](data/ui_home.png)
![听风AI 模型列表](data/ui_models.png)

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-brightgreen.svg" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/docker-compose-orange.svg" alt="Docker"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-2.1.0-brightgreen.svg" alt="Version"></a>
</p>

---

## 📋 概述

听风AI 是一个**生产级 AI 图像生成 API 网关**，将多家上游 AI 图像服务（imagefree.net、aifreeforever.com、minimaxh3.ai、nanobanana-pro.com 等）聚合为统一的 OpenAI 风格 `/v1/*` 接口。核心能力包括：

- **🔄 多提供商路由** — 根据 model 参数自动路由到对应上游，支持自动降级/熔断
- **👥 号池自动化** — 自动注册 + 每日签到，管理 1000+ 账号无需人工干预
- **🌐 代理池轮换** — 住宅代理 + 免费代理双源，每 IP 递增冷却 + 24h 每日限额重置
- **⚡ 高并发架构** — 有界优先级队列 + Worker 池（4-16 自适应）+ Turnstile token 预取，扛 270+ RPS
- **🔧 零鉴权部署** — 开箱即用，无需配置复杂鉴权；支持 Docker Compose 一键部署

> 📌 **线上演示**：https://imagefree.tingfengai.art（腾讯云东京，公益开放）

---

## 🚀 快速启动

### 前置依赖

- Python 3.11+ 或 Docker
- 网络代理（访问 imagefree.net 等上游需能直连或通过代理）

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/lza6/Image-to-2api.git
cd Image-to-2api/deploy

# 编辑 docker-compose.yml 按需配置，然后启动
docker compose up -d
```

### 方式二：本地启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 cf_solver（Turnstile 求解服务）
python cf_solver/boterdrop_wrapper.py &

# 3. 启动 API 服务
uvicorn api.main:app --host 0.0.0.0 --port 8100
```

访问 `http://localhost:8100` 查看首页仪表盘。

---

## 📸 截图

| 首页仪表盘 | 提供商状态 | 号池看板 |
|:---:|:---:|:---:|
| ![首页](data/ui_home.png) | ![提供商](data/ui_providers.png) | ![号池](data/ui_pool.png) |

| 模型列表 | API 文档 |
|:---:|:---:|
| ![模型](data/ui_models.png) | ![文档](data/ui_docs.png) |

---

## 🏗️ 架构

```
调用方 ──POST /v1/generate ──► ┌──────────────────────────────────────────────────┐
   (同步/异步)                  │  imagefree_api (FastAPI :8100)                  │
                               │                                                   │
                         ┌─ 校验 ── SQLite 入库 ── 优先级队列(三级) ──┐          │
                         └────────────────────────────────────────────────────┘  │
                               │                                                   │
                           ┌───▼─────────┐   ┌──────────────────┐   ┌──────────┐ │
                           │ worker 池    │◄─┤ token 预取池     │◄─┤cf_solver │ │
                           │ (×10,自适应) │   │ (EMA延迟自适应)   │   │解Turnstile│ │
                           │ 4~16 auto   │   │ (熔断保护)        │   │(:8001)   │ │
                           └───┬─────────┘   └──────────────────┘   └──────────┘ │
                               │                                                   │
                               ├──► imagefree.net / aifreeforever / minimaxh3     │
                               │    nanobanana ... 统一 OpenAI 风格路由           │
                               │                                                   │
                               │   配套自动化：                                    │
                               │   ├─ 号池自动注册 + 每日签到                      │
                               │   ├─ 免费代理池抓取 + 住宅代理轮换               │
                               │   ├─ DB 批量写合并(0.2s窗口)                     │
                               │   ├─ 死信队列 + 重试退避 + 幂等提交              │
                               │   └─ Prometheus 指标 + LRU 缓存                  │
                               └──────────────────────────────────────────────────┘
```

### 核心设计

| 特性 | 说明 |
|------|------|
| **入口 50 RPS** | 请求仅做「校验→SQLite 入库→入队→返回」毫秒级，不阻塞 |
| **优先级队列** | 三级优先级（admin/paid/normal），各级独立容量上限 |
| **Worker 自适应** | 4-16 弹性伸缩，排队长则扩容，空闲则缩容 |
| **Token 预取池** | 后台持续预取 Turnstile token，请求零等待；EMA 自适应延迟 |
| **DB 批量写** | 0.2s 窗口合并 commit，50 RPS 下仅 ~5 commit/s |
| **base64 文件分离** | 图片 base64 从 SQLite 移至本地文件，到期自动清理 |
| **LRU 缓存** | 画廊/统计/提供商状态缓存，降低 DB 读压 |
| **熔断降级** | solver 连续失败达阈值→熔断 OPEN；provider 限流达阈值→自动降级 |
| **死信队列** | 重试耗尽的任务推入 DLQ，可在线查询 |
| **持久化队列** | 重启后未消费任务可续跑 |

---

## 🔌 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /` | — | 中文仪表盘首页（统计 + 画廊 + 实时状态） |
| `POST /v1/generate` | 同步 | 文生图/文生视频，阻塞直到出图 |
| `POST /v1/generate/async` | 异步 | 立即返回 task_id，轮询 `/v1/tasks/{id}` |
| `POST /v1/edit` | 异步 | 图生图（AI 照片编辑） |
| `GET /v1/tasks` | — | 任务列表（分页/筛选/排序） |
| `GET /v1/tasks/{id}` | — | 查询单任务结果 |
| `GET /v1/models` | — | 全提供商模型列表（45+ 模型） |
| `GET /v1/providers` | — | 提供商状态看板 |
| `GET /v1/stats` | — | 用量统计（按日/月拆分） |
| `GET /v1/gallery` | — | 最近作品画廊 |
| `GET /v1/healthz` | — | 健康检查 + solver 求解质量指标 |
| `GET /v1/logs` | — | 实时日志（环形缓冲区，200 条） |
| `GET /v1/proxy-pool` | — | 代理池实时状态 |
| `GET /v1/account-pool` | — | 号池看板 |
| `GET /v1/dead-letter-queue` | — | 死信队列 |
| `GET /v1/meta` | — | sitekey / aspect_ratios 等元信息 |
| `GET /metrics` | — | Prometheus 指标 |
| `GET /docs` | — | Swagger 交互文档 |

### curl 示例

```bash
# 文生图
curl -X POST http://localhost:8100/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a red rose","aspect_ratio":"1:1","download":true}'

# 查询任务
curl http://localhost:8100/v1/tasks/{task_id}
```

---

## 🧩 提供商清单

| 提供商 | 上游地址 | 能力 | 认证方式 | 风控 |
|--------|---------|------|---------|------|
| `imagefree` | imagefree.net | txt2img / img2img | Turnstile token | 直连 |
| `minimaxh3` | minimaxh3.ai | txt2img / img2img / txt2vid / img2vid | Auth.js cookie + 号池 | 用完即弃 |
| `aifreeforever` | aifreeforever.com | txt2img / img2img（≤3 参考图） | 匿名 + Turnstile | **每 IP 每日限额 → 每请求轮换代理** |
| `nanobanana` | nanobanana-pro.com | txt2img / img2img | better-auth cookie + 号池 | 每日签到续额 |

---

## ⚙️ 关键配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `IF_HOST` / `IF_PORT` | `127.0.0.1` / `8100` | 监听地址 |
| `IF_CF_SOLVER_URL` | `http://127.0.0.1:8001` | cf_solver 地址 |
| `IF_BASE_URL` | `https://imagefree.net` | 目标站点 |
| `IF_WORKERS` | `10` | Worker 并发数 |
| `IF_TOKEN_POOL_SIZE` | `6` | Token 预取池大小 |
| `IF_GENERATE_TIMEOUT` | `300` | 生成超时（秒） |
| `IF_TXT_RETRY_MAX` | `3` | 重试次数 |
| `IF_FREE_PROXY` | `0` | 免费代理池开关 |
| `IF_PROXY_FILE` | 空 | 住宅代理池文件 |
| `IF_ACCOUNT_AUTO` | `1` | 号池自动注册/签到 |
| `IF_GALLERY_PASSWORD` | 空 | 画廊密码 |
| `IF_DLQ_ENABLED` | `1` | 死信队列开关 |

> 完整配置列表见 [`api/config.py`](api/config.py) 或 `README.md` 内的配置表。

---

## 📁 项目结构

```
└── api/
    ├── main.py              # FastAPI 入口 + 端点
    ├── config.py            # 配置（环境变量）
    ├── worker.py            # 高并发引擎：优先级队列 + worker 池 + token 预取
    ├── db.py                # SQLite 持久化 + 批量写合并
    ├── turnstile_client.py  # cf_solver 客户端
    ├── imagefree_client.py  # imagefree.net 客户端
    ├── solver_guard.py      # 熔断器 + 求解质量统计
    ├── proxy_pool.py        # 住宅代理池 + 冷却策略
    ├── free_proxy_fetcher.py# 免费代理池抓取
    ├── account_pool.py      # 号池管理
    ├── registerer.py        # 自动注册（minimaxh3 / nanobanana）
    ├── providers/           # 多提供商适配器
    │   ├── base.py          # 抽象基类
    │   ├── registry.py      # 提供商注册 + 路由 + 健康检查
    │   ├── imagefree.py
    │   ├── aifreeforever.py
    │   ├── minimaxh3.py
    │   └── nanobanana.py
    ├── cache.py             # LRU 缓存
    ├── retry_policy.py      # 重试策略（指数退避 + jitter）
    ├── base64_store.py      # base64 文件缓存
    └── docs.html            # 中文仪表盘首页
└── tests/                   # 300+ 测试用例
└── deploy/                  # Docker Compose 部署资产
```

---

## 🔬 求解质量监控

前端仪表盘实时显示 cf_solver Turnstile 求解统计：

- **求解状态**：✅ 正常 / ⚠️ 劣化 / ⛔ 熔断
- **窗口成功率**：近 5 分钟滑动窗口成功率
- **累计统计**：总成功/失败次数、平均耗时
- **失败原因**：按原因分类（timeout / transport / solver_rejected / http_error）
- **Token 池水位**：直连池 + per-proxy 池水位
- **熔断状态**：连续失败达阈值自动暂停求解

后端 `/v1/healthz` 和 `/metrics` 暴露完整指标，可与 Prometheus + Grafana 集成。

---

## 🧪 测试

```bash
# 单元测试（300+ 用例）
pytest tests/ -q

# Mock E2E（零真实求解消耗）
python scripts/e2e_validate.py --mode mock

# 真实 E2E（需 cf_solver :8001 + 代理）
python scripts/e2e_validate.py --mode real
```

---

## 📄 许可证

[MIT License](LICENSE) — 开源免费，欢迎使用、修改、再分发。

```
Copyright (c) 2026 听风AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions...
```

---

## 🤝 联系

- 微信：**Tf00798**
- 负责人：**听风**
- GitHub：[@lza6](https://github.com/lza6)

---

> **免责声明**：本项目仅供学习和研究目的。使用本项目时请遵守相关法律法规和上游服务条款。