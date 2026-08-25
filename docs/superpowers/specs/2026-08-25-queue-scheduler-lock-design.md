# 队列调度、并发控制与图生图分布式锁 — 设计文档

**日期**: 2026-08-25
**版本**: v5.1.0
**状态**: 设计稿

## 1. 概述

### 1.1 目标

升级 imagefree-api 核心调度层，实现：
1. 内存有界优先级队列优化（三层桶 + 瞬时落盘 + SSE 广播）
2. 图生图互斥锁从 PID 文件锁演进为 SQLite 行级原子租约锁（Lease Lock）

### 1.2 背景

当前系统已具备 `CountedPriorityQueue`（三层优先级：0=Admin / 1=Paid / 2=Normal）和基于文件系统 PID 的 `_edit_mutex` 互斥锁。但存在以下问题：

- **队列**：入队后 SSE 广播是异步非阻塞的，但缺少瞬时落盘保障，进程崩溃丢失内存队列
- **图生图锁**：PID 文件锁在 Docker 容器环境易受干扰（PID 1 特殊处理已用 `if pid <= 1` patch，但仍有竞态窗口）

## 2. 方案设计

### 2.1 内存有界优先级队列优化

#### 现状

```
Request → submit_priority() → CountedPriorityQueue(内存) → worker_loop
                                ↓
                           SSE 广播(best-effort)
```

#### 演进

```
Request → submit_priority() → CountedPriorityQueue(内存) → worker_loop
                                ↓                        ↓
                           Instant SQLite 落盘      SSE 广播(含队列位置)
                                ↓
                           WAL 模式秒级持久化
```

**关键变更**：

1. **瞬时原子落盘**：`submit_priority()` 在入队内存队列的同时，同步写入 SQLite `task_queue` 表（WAL 模式，INSERT 微秒级）
2. **SSE 广播增强**：入队时广播 `status: "pending"` 事件，携带 `queue_pos`（队列位置）、`priority` 字段
3. **持久化恢复**：进程重启时从 `task_queue` 读取 pending 任务，按 `priority/seq` 排序后重新入队

#### 数据结构

```sql
CREATE TABLE IF NOT EXISTS task_queue (
    task_id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 2,
    seq INTEGER NOT NULL,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'  -- pending | processing | completed
);
CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status);
```

### 2.2 图生图互斥锁：Lease Lock

#### 现状（PID 文件锁）

```
_acquire_edit_mutex(key):
    O_CREAT | O_EXCL 创建锁文件
    写入 PID + 时间戳 + token
    _edit_mutex_stale: os.kill(pid, 0) 判断持有者存活
    问题: Docker PID 1 特判脆弱; 异常宕机不自动释放
```

#### 演进（SQLite Lease Lock）

```
_acquire_edit_lease(key):
    BEGIN IMMEDIATE
    INSERT OR REPLACE INTO edit_leases(key, holder, expires_at, token)
    VALUES(?, ?, ?, ?) WHERE expires_at < ?
    SELECT changes() > 0
    COMMIT
    成功 → 返回 token; 失败 → 重试或超时
```

**关键设计**：

| 特性 | 实现 |
|------|------|
| 排他性 | SQLite 行级事务 + `INSERT OR REPLACE WHERE expires_at < now` 条件 |
| 自动超时释放 | `expires_at` 列，超时后后续 acquire 自动覆盖 |
| TTL 续租 | 持锁期间定期 `UPDATE edit_leases SET expires_at = ? WHERE token = ?` |
| 异常宕机释放 | 无续租 → `expires_at` 过期 → 自动被新 acquire 覆盖 |
| 可观测性 | `holder` 记录实例标识，`created_at` 记录获取时间 |

#### 数据结构

```sql
CREATE TABLE IF NOT EXISTS edit_leases (
    key TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    token TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);
```

**续租心跳**：持锁协程启动后台心跳协程，每 `TTL/3` 秒续租一次。协程退出时自动释放锁（`DELETE WHERE token = ?`）。

#### 迁移策略

1. 新增 `EDIT_LEASE_ENABLED` 配置开关，默认 `False`（保持向后兼容）
2. 改 `_dispatch_edit.py` 中的 `_acquire_edit_mutex` → `_acquire_edit_lock`，内部按配置选择文件锁或租约锁
3. 旧文件锁代码保留作为 fallback，新部署使用租约锁

### 2.3 配置变更

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `IF_EDIT_LEASE_ENABLED` | bool | `False` | 启用 SQLite 租约锁替代文件锁 |
| `IF_EDIT_LEASE_TTL` | int | `30` | 租约锁 TTL（秒） |
| `IF_PERSISTENT_QUEUE_ENABLED` | bool | 保持 `False` | 持久化队列开关（生产启用） |

### 2.4 测试计划

#### 单元测试

| 测试 | 文件 | 覆盖范围 |
|------|------|---------|
| 优先级队列顺序 | `test_priority_queue.py` | 已有，补充 batch 模式验证 |
| 持久化队列落盘/恢复 | `test_persistent_queue.py` | 已有，验证 WAL 写入 + 进程重启恢复 |
| Lease Lock 获取/释放 | 新增 `test_edit_lease.py` | 排他获取、超时、续租、释放 |
| Lease Lock 竞态 | 新增 | 并发协程竞争同一 key，仅一个成功 |

#### E2E 测试

| 场景 | 脚本 | 验证方式 |
|------|------|---------|
| 500 RPS 突发入队 | 已有 `loadtest.py` | 主循环延时 ≤ 2ms |
| 图生图三层锁 | 已有 `e2e_full.py` | 并发编辑不冲突 |
| 进程崩溃锁自动释放 | 新增 | 模拟 crash → 新实例可获取锁 |

### 2.5 验证标准

1. 队列单元测试全部通过（已有 200+ 测试 + 新增）
2. 体系测试 `pytest tests/ -v` 全部通过
3. 持久化队列：服务重启后 pending 任务恢复
4. Lease Lock：并发竞争同一 key，仅一个成功；持锁进程崩溃后，新实例在 TTL 后可获取锁
5. 前端 E2E 不变

### 2.6 部署计划

1. 本地开发环境全量测试通过
2. `sync_deploy.py` 同步到 `deploy/api/`
3. 生产服务器更新 `docker-compose` 环境变量启用新特性
4. 灰度观察 30 分钟 → 全量切换

### 2.7 风险与回滚

- **风险**：租约锁 TTL 过短导致频繁续租开销；过长导致故障恢复延迟
- **缓解**：默认 30s TTL，心跳 10s 间隔，可配置
- **回滚**：`IF_EDIT_LEASE_ENABLED=False` 恢复文件锁，无停机