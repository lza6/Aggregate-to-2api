# 终局审计实施计划

## 技术栈
- Python 3.11+ / FastAPI / SQLite (WAL mode)
- asyncio + httpx + LRU cache
- pytest + pytest-asyncio

## 架构概览

```
调用方 → FastAPI(:8100) → 校验 → SQLite 入库 → 优先级队列 → Worker 池 → imagefree.net
                                                                ↑
                                                    Turnstile token 预取池 ← cf_solver(:8001)
```

## 设计模式
- **仓储模式**：DB 类封装所有 SQLite 操作
- **LRU 缓存 + 持久化兜底**：内存缓存 + DB cache_store 表
- **批量写入缓冲区**：0.2s 窗口合并写操作
- **Token 池预取**：事件驱动补池 + EMA 自适应延迟

## 安全考虑
- 输入校验：pydantic 模型 + 白名单排序
- SSRF 防护：IP 地址检查
- CORS 开放（public API 特性）
- 画廊密码保护

## 错误处理
- 所有异常路径有日志记录
- 熔断机制保护 solver
- 死信队列兜底重试耗尽
- 硬超时兜底

## 性能策略
- LRU 缓存降 DB 读压
- 批量写入降 commit 频率
- Token 预取池消除求解等待
- 动态 worker 伸缩

## 数据模型

### requests 表
- id, prompt, aspect_ratio, download, status, image_url
- image_base64, image_mime, error, created_at, started_at
- finished_at, duration_sec, type, model, day, month
- upstream_task_id, proxy_used

### cache_store 表 (IMP-11)
- key, value, ttl, cached_at
