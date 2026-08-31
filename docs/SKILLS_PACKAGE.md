# imagefree-api 项目 Skills 技能包

## 技能索引

### 1. 项目结构概览

```
imagefree-2ai/
├── api/              # Python 后端服务（FastAPI）
│   ├── main.py          # FastAPI 入口 + 所有端点
│   ├── worker.py        # 高并发引擎（队列 + Worker 池 + Token 池）
│   ├── cache.py         # LRU 缓存（IMP-11 持久化回写）
│   ├── db.py            # SQLite 数据库层（WAL 模式）
│   ├── config.py        # 配置管理（全部环境变量覆盖）
│   ├── turnstile_client.py  # Turnstile 求解客户端
│   ├── imagefree_client.py  # imagefree API 客户端
│   ├── solver_guard.py      # 求解器熔断保护
│   ├── retry_policy.py      # 重试策略
│   ├── providers/          # 多提供商网关
│   │   ├── registry.py     # 提供商注册表
│   │   ├── base.py         # Provider 基类
│   │   ├── imagefree.py    # imagefree 适配器
│   │   ├── minimaxh3.py    # minimaxh3 适配器
│   │   ├── aifreeforever.py
│   │   ├── nanobanana.py
│   │   └── __init__.py
│   ├── account_pool.py     # 号池管理
│   ├── proxy_pool.py       # 代理池管理
│   ├── base64_store.py     # base64 文件缓存
│   ├── log_buffer.py       # 环形日志缓冲区
│   └── telemetry.py        # OpenTelemetry 集成
├── tests/            # 测试套件
├── data/             # 运行时数据目录
├── docs/             # 文档
├── deploy/           # 部署配置
│   └── README.deploy.md
├── scripts/          # 工具脚本
├── .specify/         # Spec-Kit 规范
├── .env.example      # 环境变量模板
├── pyproject.toml    # 项目配置
├── requirements.txt  # Python 依赖
├── start.bat         # Windows 快速启动
└── start.ps1         # PowerShell 启动脚本
```

### 2. 核心架构模式

#### 请求处理流
```
POST /v1/generate/async
  → 校验（pydantic + 白名单）
  → SQLite 入库（毫秒级）
  → 优先级入队（0/1/2 三级）
  → 返回 task_id（无阻塞）

Worker 池（后台）：
  → 取队列任务
  → 取 Turnstile token（预取池，不阻塞求解）
  → 提交到 imagefree.net
  → 轮询到出图
  → 落库 + 失效画廊缓存（IMP-11）
  → 返回结果
```

#### 缓存策略（IMP-11）
```
LRUCache（内存 TTL 5s）
  ├── set(key, value) → 内存 + 挂起缓冲区
  ├── reaper（每 5 轮 flush）→ DB cache_store 表
  ├── stop_reaper() → 全量 flush 到 DB
  ├── start_reaper() → restore_from_db() 恢复
  └── invalidate("gallery:") → 新图入库自动失效
```

### 3. 关键设计决策（ADR）

| ADR | 决策 | 理由 |
|-----|------|------|
| DB 选型 | SQLite WAL 模式 | 标准库、毫秒级 INSERT、WAL 支持读写并行 |
| 缓存持久化 | LRU + DB 回写 | 防重启空窗，5s TTL 降读压，stop 时全量 flush |
| 批量写入 | 0.2s 窗口合并 commit | 降 50 RPS 下 commit 频率 |
| Token 池 | 事件驱动预取 | 消除求解等待，EMA 自适应延迟 |
| 提供商网关 | 注册表模式 | 统一接口，可插拔 |
| 画廊缓存失效 | invalidate_prefix | 新图入库后自动失效所有 limit 变体 |

### 4. 测试策略

```
测试层级：
├── 单元测试（tests/test_*.py）
│   ├── test_lru_cache.py        # LRU 缓存基础功能
│   ├── test_cache_persist.py    # IMP-11 持久化回写
│   ├── test_db_*.py             # 数据库层
│   ├── test_worker_*.py         # Worker 引擎
│   └── ...
├── 集成测试
│   ├── test_priority_queue.py   # 优先级队列
│   ├── test_persistent_queue.py # 持久化队列
│   └── test_providers.py        # 提供商网关
└── E2E 测试
    ├── scripts/e2e_validate.py
    └── scripts/e2e_providers.py
```

### 5. 添加新功能工作流

1. **读取上下文**：检查 `.wolf/cerebrum.md` 和 `workflow_status.md`
2. **创建规范**：`.specify/specs/NNN-name/` 中创建 spec + plan
3. **实现**：TDD 模式，先写测试
4. **验证**：`python -m pytest tests/` 全量运行
5. **文档**：更新 README.md、.env.example、SOP.md
6. **更新状态**：`workflow_status.md` 标记完成
7. **记录**：向 `.wolf/memory.md` 追加单行条目

### 6. 已知限制

- OTel `force_flush` 参数兼容性（opentelemetry-api 版本差异，已修复）
- 图生图上游硬并发=1（住宅代理池可绕过）
- 外部付费 API 无法 E2E 测试（mock 模式替代）
- 服务器 2G 内存限制（cf_solver 限制 1.5G，api 限制 256M）

### 7. 快速联调验证

```bash
# 1. 启动服务
python -m uvicorn api.main:app --host 127.0.0.1 --port 8100

# 2. 健康检查
curl http://127.0.0.1:8100/v1/healthz

# 3. 运行测试
python -m pytest tests/ -v

# 4. 验证缓存持久化（IMP-11）
python -c "
import asyncio, tempfile, os
from api.cache import LRUCache
from api.db import DB
async def test():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = DB(path)
    cache = LRUCache(maxsize=128, ttl=3600, persist_db=db)
    await cache.set('k1', 'hello')
    cache.flush_to_db()
    cache2 = LRUCache(maxsize=128, ttl=3600, persist_db=db)
    await cache2.restore_from_db()
    v = await cache2.get('k1')
    assert v == 'hello', f'got {v}'
    print('OK: 缓存持久化恢复正常')
    db.close(); os.unlink(path)
    for s in ('-wal','-shm'):
        p = path+s
        if os.path.exists(p): os.unlink(p)
asyncio.run(test())
"
```
