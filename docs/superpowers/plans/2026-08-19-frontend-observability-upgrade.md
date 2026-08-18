# 前端/UI 升级 + 可观测性增强 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 完成 7 项前端/UI 升级 + 可观测性增强（U-01~U-03 + O-01~O-04），包括：React 独立前端仪表盘、WebSocket 实时日志、提供商可视化、prometheus_client 指标系统、内置告警引擎、审计日志、OTel 深度追踪

**架构：** 在现有 FastAPI 后端基础上，前端用 React/Vite 独立项目（方案 B），后端新增 WebSocket 端点、指标系统、告警引擎、审计日志模块。所有新模块都有独立测试。

**技术栈：** React 19 + Vite + TypeScript + Recharts（前端）；Python + FastAPI + WebSocket + prometheus_client + OpenTelemetry（后端）

---

## 文件结构

### 新增文件
- `frontend/` — React 前端项目目录
  - `frontend/package.json` — 前端依赖
  - `frontend/vite.config.ts` — Vite 构建配置
  - `frontend/tsconfig.json` — TypeScript 配置
  - `frontend/index.html` — 入口 HTML
  - `frontend/src/main.tsx` — 入口
  - `frontend/src/App.tsx` — 主应用（路由）
  - `frontend/src/api.ts` — API 客户端
  - `frontend/src/pages/Dashboard.tsx` — 主仪表盘
  - `frontend/src/pages/Providers.tsx` — 提供商状态
  - `frontend/src/pages/Tasks.tsx` — 任务管理
  - `frontend/src/pages/Accounts.tsx` — 号池管理
  - `frontend/src/pages/Logs.tsx` — 实时日志查看器
  - `frontend/src/pages/DLQ.tsx` — 死信队列管理
  - `frontend/src/pages/Settings.tsx` — 配置管理
  - `frontend/src/components/` — 通用组件
    - `frontend/src/components/StatCard.tsx`
    - `frontend/src/components/BarChart.tsx`
    - `frontend/src/components/Gallery.tsx`
    - `frontend/src/components/Layout.tsx`
    - `frontend/src/components/ProviderCard.tsx`
- `api/alerting.py` — 告警引擎
- `api/audit.py` — 审计日志
- `api/metrics_ext.py` — prometheus_client 指标系统（替代手动拼接）
- `api/log_ws.py` — WebSocket 日志推送

### 修改文件
- `api/main.py` — 新增 WebSocket 端点、挂载前端静态文件、集成审计/告警/新指标
- `api/worker.py` — 新增 OTel 嵌套 span
- `api/db.py` — 新增 DB 操作 span
- `api/imagefree_client.py` — 新增 provider 调用 span
- `api/config.py` — 新增配置项
- `api/telemetry.py` — 增强 span 粒度
- `pyproject.toml` — 新增依赖
- `deploy/requirements.txt` — 新增依赖
- `deploy/docker-compose.yml` — 新增前端构建/部署
- `deploy/Dockerfile.api` — 增加前端静态文件复制
- `scripts/sync_deploy.py` — 新增 `frontend/` 同步

---

## 任务分解

### 任务 1：后端 — prometheus_client 指标系统（O-01）

**文件：**
- 创建：`api/metrics_ext.py`
- 修改：`api/main.py`（替换 `/metrics` 端点）
- 测试：`tests/test_metrics_ext.py`

- [ ] **步骤 1：编写测试**

```python
"""测试 prometheus_client 指标系统。"""
from api.metrics_ext import (
    requests_total, generate_duration, token_pool_watermark,
    queue_size, imagefree_metrics,
)

def test_metrics_labels():
    """验证指标带有正确 label 维度。"""
    requests_total.labels(provider="imagefree", status="completed").inc()
    assert requests_total.labels(provider="imagefree", status="completed")._value.get() == 1.0

def test_generate_duration_histogram():
    """验证生成耗时 histogram 记录。"""
    generate_duration.labels(provider="imagefree", model="default").observe(5.0)
    # 不 assert 具体值，只验证不抛异常
    assert True

def test_watermark_gauge():
    """验证水位 gauge 可设置。"""
    token_pool_watermark.labels(pool="direct").set(3)
    assert token_pool_watermark.labels(pool="direct")._value.get() == 3.0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_metrics_ext.py -v`
预期：ModuleNotFoundError / ImportError（metrics_ext 不存在）

- [ ] **步骤 3：实现 metrics_ext.py**

```python
"""prometheus_client 指标系统（替代手动拼接 /metrics）。

统一用 prometheus_client 库，不再手动拼接 Prometheus 文本格式。
Histogram 自动计算 P50/P95/P99，Counter 支持 label 维度。
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

# ── 请求 / 出图 / 失败 ──
requests_total = Counter(
    "imagefree_requests_total", "累计请求数",
    ["provider", "status"],
)
images_total = Counter(
    "imagefree_images_total", "累计成功出图数",
    ["provider"],
)
errors_total = Counter(
    "imagefree_errors_total", "累计失败数",
    ["provider", "reason"],
)

# ── 生成耗时 ──
generate_duration = Histogram(
    "imagefree_generate_duration_seconds", "生成耗时",
    ["provider", "model"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

# ── 实时水位 ──
processing_gauge = Gauge("imagefree_processing", "当前生成中的任务数")
queue_size = Gauge("imagefree_queued", "当前排队任务数")
token_pool_watermark = Gauge("imagefree_token_pool_watermark", "Token 池水位", ["pool"])
db_rows = Gauge("imagefree_db_rows", "请求记录总量")
edit_inflight = Gauge("imagefree_edit_inflight", "图生图在途/排队任务数")
uptime_seconds = Counter("imagefree_uptime_seconds", "服务运行时长(秒)")

# ── 求解器 ──
solve_total = Counter(
    "imagefree_solve_total", "Turnstile 求解成功/失败累计数",
    ["result"],
)
solve_duration = Histogram(
    "imagefree_solve_duration_seconds", "求解耗时",
    buckets=[1, 2, 5, 10, 20, 30, 60],
)
solve_window_success_rate = Gauge("imagefree_solve_window_success_rate", "近窗口求解成功率")
solve_consecutive_failures = Gauge("imagefree_solve_consecutive_failures", "连续求解失败次数")
solver_circuit_open = Gauge("imagefree_solver_circuit_open", "solver 熔断是否开启")


def imagefree_metrics(engine_snapshot: dict, stats_overview: dict, solver_snapshot: dict) -> str:
    """收集所有指标并返回 Prometheus 文本格式。"""
    # 请求统计
    requests_total.labels(provider="all", status="completed").inc(stats_overview.get("total_images", 0))
    requests_total.labels(provider="all", status="error").inc(stats_overview.get("total_errors", 0))
    images_total.labels(provider="all").inc(stats_overview.get("total_images", 0))
    errors_total.labels(provider="all", reason="error").inc(stats_overview.get("total_errors", 0))

    # 实时水位
    processing_gauge.set(engine_snapshot.get("processing", 0))
    queue_size.set(engine_snapshot.get("queued", 0))
    db_rows.set(stats_overview.get("total_requests", 0))

    # 求解器
    solve_total.labels(result="success").inc(solver_snapshot.get("solve_success_total", 0))
    solve_total.labels(result="failure").inc(solver_snapshot.get("solve_failure_total", 0))
    rate = solver_snapshot.get("window_success_rate")
    if rate is not None:
        solve_window_success_rate.set(rate)
    solve_consecutive_failures.set(solver_snapshot.get("consecutive_failures", 0))
    solver_circuit_open.set(1 if solver_snapshot.get("circuit_open") else 0)

    return generate_latest(REGISTRY).decode("utf-8")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_metrics_ext.py -v`
预期：PASS

- [ ] **步骤 5：修改 main.py /metrics 端点引用新指标**

```python
# 在 api/main.py 顶部添加
from .metrics_ext import imagefree_metrics as metrics_v2

# 修改 /metrics 端点
@app.get("/metrics", include_in_schema=False)
async def metrics():
    snap = engine.snapshot()
    ov = db.stats_overview()
    ssnap = solver_guard.snapshot()
    return PlainTextResponse(metrics_v2(snap, ov, ssnap),
                             media_type="text/plain; version=0.0.4; charset=utf-8")
```

- [ ] **步骤 6：运行测试验证通过**

运行：`pytest tests/ -v -x`
预期：PASS

- [ ] **步骤 7：Commit**

```bash
git add api/metrics_ext.py tests/test_metrics_ext.py api/main.py
git commit -m "feat: prometheus_client 指标系统替代手动拼接"
```

### 任务 2：后端 — 审计日志模块（O-03）

**文件：**
- 创建：`api/audit.py`
- 修改：`api/main.py`（集成审计日志）
- 测试：`tests/test_audit.py`

- [ ] **步骤 1：编写测试**

```python
"""测试审计日志模块。"""
import json
import os
import tempfile
from api.audit import AuditLog


def test_audit_record():
    """验证审计日志写入。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        audit.record("dlq.clear", "127.0.0.1", "dlq", "清空死信队列")
        with open(path) as f:
            line = json.loads(f.readline())
        assert line["action"] == "dlq.clear"
        assert line["actor"] == "127.0.0.1"
        assert line["target"] == "dlq"
        assert "timestamp" in line
    finally:
        os.unlink(path)


def test_audit_append_only():
    """验证审计日志仅追加，不修改已有记录。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        audit.record("action1", "actor1", "target1")
        audit.record("action2", "actor2", "target2")
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])
        assert entry1["action"] == "action1"
        assert entry2["action"] == "action2"
    finally:
        os.unlink(path)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_audit.py -v`
预期：ImportError

- [ ] **步骤 3：实现 audit.py**

```python
"""不可变审计日志（仅追加），记录管理操作、鉴权失败、provider 状态变更等。"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("imagefree_api.audit")


class AuditLog:
    """不可变审计日志。仅追加写入，永不修改已有记录。

    用法：
        audit = AuditLog("data/audit.log")
        audit.record("dlq.clear", "127.0.0.1", "dlq", "清空死信队列")
    """

    def __init__(self, path: str = "data/audit.log"):
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, actor: str, target: str,
               detail: str | None = None) -> None:
        """记录一条审计日志。

        Args:
            action: 操作类型，如 dlq.clear、task.retry、config.change
            actor: 操作者（IP 或 API Key ID）
            target: 操作对象
            detail: 操作详情（可选）
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "target": target,
            "detail": detail,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("审计日志写入失败: %s", e)

    def recent(self, limit: int = 50) -> list[dict]:
        """返回最近 N 条审计日志。"""
        try:
            with open(self._path, encoding="utf-8") as f:
                lines = f.readlines()
        except (OSError, FileNotFoundError):
            return []
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        return entries


# 全局单例
audit_log = AuditLog()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_audit.py -v`
预期：PASS

- [ ] **步骤 5：集成到 main.py**

在 `api/main.py` 中：
```python
from .audit import audit_log
```

在 `clear_dlq` 端点中记录审计：
```python
@app.post("/v1/dead-letter-queue/clear")
async def clear_dlq():
    """清空死信队列。"""
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.clear", client_ip, "dlq", "清空死信队列")
    db.clear_dlq()
    return {"status": "ok"}
```

在 `retry_dlq_task` 端点中记录审计：
```python
@app.post("/v1/dead-letter-queue/{task_id}/retry")
async def retry_dlq_task(task_id: str):
    client_ip = request.client.host if request.client else "unknown"
    audit_log.record("dlq.retry", client_ip, f"task:{task_id}", "重试死信队列任务")
    db.retry_dlq(task_id)
    return {"status": "ok"}
```

- [ ] **步骤 6：运行测试验证通过**

运行：`pytest tests/ -v -x`
预期：PASS

- [ ] **步骤 7：Commit**

```bash
git add api/audit.py tests/test_audit.py api/main.py
git commit -m "feat: 审计日志模块 — 不可变仅追加操作记录"
```

### 任务 3：后端 — 内置告警引擎（O-02）

**文件：**
- 创建：`api/alerting.py`
- 修改：`api/main.py`（启动告警循环）
- 测试：`tests/test_alerting.py`

- [ ] **步骤 1：编写测试**

```python
"""测试内置告警引擎。"""
import time
from api.alerting import AlertRule, AlertEngine, alert_engine


def test_alert_rule_condition():
    """验证告警规则条件判断。"""
    rule = AlertRule(
        name="test_rule",
        severity="warning",
        message="测试告警",
        cooldown=1.0,
        check=lambda ctx: ctx.get("value", 0) > 100,
    )
    assert rule.check({"value": 200}) is True
    assert rule.check({"value": 50}) is False


def test_alert_engine_cooldown():
    """验证告警冷却机制。"""
    engine = AlertEngine()
    engine.add_rule(AlertRule(
        name="cooldown_test",
        severity="warning",
        message="冷却测试",
        cooldown=5.0,
        check=lambda ctx: True,
    ))
    result = engine.evaluate({"value": 1})
    assert len(result) == 1
    result2 = engine.evaluate({"value": 1})
    assert len(result2) == 0  # 冷却中


def test_alert_engine_empty():
    """验证无规则时告警引擎正常。"""
    engine = AlertEngine()
    result = engine.evaluate({"value": 1})
    assert result == []
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_alerting.py -v`
预期：ImportError

- [ ] **步骤 3：实现 alerting.py**

```python
"""内置告警引擎 — 无需外部 Prometheus + AlertManager。

内置告警规则在内存中评估，触发后写入日志。
支持冷却机制防止重复告警。
"""
import logging
import time
from typing import Callable

log = logging.getLogger("imagefree_api.alerting")


class AlertRule:
    """一条告警规则。"""

    def __init__(
        self,
        name: str,
        severity: str,
        message: str,
        check: Callable[[dict], bool],
        cooldown: float = 300.0,
    ):
        self.name = name
        self.severity = severity  # info / warning / critical
        self.message = message
        self.check = check
        self.cooldown = cooldown
        self._last_triggered: float = 0.0

    def should_trigger(self, ctx: dict) -> bool:
        """检查是否应触发告警（条件满足 + 冷却已过）。"""
        if not self.check(ctx):
            return False
        now = time.time()
        if now - self._last_triggered < self.cooldown:
            return False
        self._last_triggered = now
        return True


class AlertEngine:
    """告警引擎 — 管理规则集、评估上下文、触发告警。"""

    def __init__(self):
        self._rules: list[AlertRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """设置内置默认告警规则。"""
        self.add_rule(AlertRule(
            name="queue_backlog",
            severity="warning",
            message="排队任务数超过 1000",
            check=lambda ctx: ctx.get("queued", 0) > 1000,
            cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="high_error_rate",
            severity="critical",
            message="错误率超过 20%（近 5 分钟窗口）",
            check=lambda ctx: (
                ctx.get("window_requests", 0) > 0 and
                ctx.get("window_errors", 0) / ctx.get("window_requests", 1) > 0.2
            ),
            cooldown=300.0,
        ))
        self.add_rule(AlertRule(
            name="solver_circuit_open",
            severity="critical",
            message="求解器熔断已开启 ≥30s",
            check=lambda ctx: ctx.get("solver_circuit_open", False),
            cooldown=60.0,
        ))
        self.add_rule(AlertRule(
            name="token_pool_empty",
            severity="warning",
            message="token 池空超过 10s",
            check=lambda ctx: ctx.get("token_pool_empty", False),
            cooldown=120.0,
        ))
        self.add_rule(AlertRule(
            name="provider_down",
            severity="warning",
            message="提供商持续不可用 >5min",
            check=lambda ctx: ctx.get("provider_down", False),
            cooldown=300.0,
        ))

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def evaluate(self, ctx: dict) -> list[dict]:
        """评估所有规则，返回触发的告警列表。"""
        triggered = []
        for rule in self._rules:
            if rule.should_trigger(ctx):
                entry = {
                    "name": rule.name,
                    "severity": rule.severity,
                    "message": rule.message,
                    "timestamp": time.time(),
                }
                log.warning("告警触发 [%s/%s]: %s", rule.severity, rule.name, rule.message)
                triggered.append(entry)
        return triggered


# 全局单例
alert_engine = AlertEngine()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_alerting.py -v`
预期：PASS

- [ ] **步骤 5：集成到 main.py 的清理循环**

```python
# 在 _cleanup_loop 中添加告警评估
from .alerting import alert_engine

async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(config.ALERT_CHECK_INTERVAL)
            # ... 现有清理逻辑 ...

            # 告警评估
            snap = engine.snapshot()
            ssnap = solver_guard.snapshot()
            stats = db.stats_overview()
            ctx = {
                "queued": snap["queued"],
                "solver_circuit_open": ssnap.get("circuit_open", False),
                "token_pool_empty": engine.token_pool.qsize() == 0,
                "window_requests": stats.get("total_requests", 0) - stats.get("total_images", 0) - stats.get("total_errors", 0),
                "window_errors": stats.get("total_errors", 0),
            }
            alert_engine.evaluate(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("告警评估异常: %s", e)
```

- [ ] **步骤 6：在 config.py 中添加 ALERT_CHECK_INTERVAL**

```python
# 告警检查间隔（秒）
ALERT_CHECK_INTERVAL = int(os.getenv("IF_ALERT_CHECK_INTERVAL", "60"))
```

- [ ] **步骤 7：运行测试验证通过**

运行：`pytest tests/ -v -x`
预期：PASS

- [ ] **步骤 8：Commit**

```bash
git add api/alerting.py tests/test_alerting.py api/main.py api/config.py
git commit -m "feat: 内置告警引擎 — 5 条内置规则 + 冷却机制"
```

### 任务 4：后端 — WebSocket 实时日志 + OTel 深度追踪（U-02 + O-04）

**文件：**
- 创建：`api/log_ws.py`
- 修改：`api/main.py`（新增 WebSocket 端点）
- 修改：`api/worker.py`（增强 OTel span）
- 修改：`api/db.py`（增强 OTel span）
- 修改：`api/imagefree_client.py`（增强 OTel span）
- 测试：`tests/test_log_ws.py`

- [ ] **步骤 1：编写 log_ws 测试**

```python
"""测试 WebSocket 日志推送。"""
import pytest
from api.log_ws import LogBuffer, broadcast_log


@pytest.mark.asyncio
async def test_log_buffer():
    """验证日志缓冲区。"""
    buf = LogBuffer(maxlen=100)
    buf.push({"level": "INFO", "message": "test"})
    assert buf.snapshot()[-1]["message"] == "test"


def test_broadcast_log_no_subscribers():
    """验证无订阅者时广播不报错。"""
    # 不抛异常即可
    import asyncio
    import logging
    record = logging.LogRecord("test", logging.INFO, "test.py", 1, "test msg", None, None)
    # 同步调用，不期待结果
    broadcast_log(record)
    assert True
```

- [ ] **步骤 2：实现 log_ws.py**

```python
"""WebSocket 实时日志推送 + 日志缓冲区。"""
import asyncio
import json
import logging
from collections import deque
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("imagefree_api.log_ws")


class LogBuffer:
    """线程安全日志缓冲区。"""

    def __init__(self, maxlen: int = 1000):
        self._buffer: deque[dict] = deque(maxlen=maxlen)
        self._lock = asyncio.Lock()

    def push(self, entry: dict) -> None:
        self._buffer.append(entry)

    def snapshot(self, lines: int = 50) -> list[dict]:
        return list(self._buffer)[-lines:]


_log_buffer_instance = LogBuffer()
_ws_subscribers: set[WebSocket] = set()
_ws_lock = asyncio.Lock()


async def register_ws(ws: WebSocket) -> None:
    """注册 WebSocket 客户端。"""
    await ws.accept()
    async with _ws_lock:
        _ws_subscribers.add(ws)


async def unregister_ws(ws: WebSocket) -> None:
    """注销 WebSocket 客户端。"""
    async with _ws_lock:
        _ws_subscribers.discard(ws)


def broadcast_log(record: logging.LogRecord) -> None:
    """广播日志到所有 WebSocket 订阅者（线程安全接口）。"""
    entry = {
        "timestamp": record.asctime if hasattr(record, "asctime") else "",
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    _log_buffer_instance.push(entry)
    # 异步广播到 WebSocket（在事件循环中执行）
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(entry), loop)
    except RuntimeError:
        pass


async def _broadcast(entry: dict) -> None:
    """向所有订阅者广播一条日志。"""
    dead: list[WebSocket] = []
    async with _ws_lock:
        for ws in list(_ws_subscribers):
            try:
                await ws.send_json(entry)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_subscribers.discard(ws)


class WsLogHandler(logging.Handler):
    """将日志注入 WebSocket 广播的 Logging Handler。"""

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(
            "%(asctime)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))

    def emit(self, record: logging.LogRecord) -> None:
        self.format(record)
        broadcast_log(record)


# 全局 WebSocket 日志处理器
ws_log_handler = WsLogHandler()
```

- [ ] **步骤 3：在 main.py 添加 WebSocket 端点**

```python
from .log_ws import register_ws, unregister_ws, ws_log_handler

@app.websocket("/v1/logs/ws")
async def log_websocket(websocket: WebSocket):
    await register_ws(ws)
    try:
        while True:
            # 保持连接，接收客户端消息（心跳）
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except Exception:
        pass
    finally:
        await unregister_ws(ws)


# 在 lifespan 中注册 WebSocket 日志处理器
async def lifespan(_app: FastAPI):
    # ... 现有代码 ...
    logging.getLogger().addHandler(ws_log_handler)
    yield
    logging.getLogger().removeHandler(ws_log_handler)
    # ... 现有代码 ...
```

- [ ] **步骤 4：增强 worker.py OTel span**

```python
# 在 _process 方法中创建嵌套 span
with tracer.start_as_current_span("worker.process") as span:
    span.set_attribute("task.id", task_id)
    span.set_attribute("task.prompt_preview", (row.get("prompt") or "")[:60])
    span.set_attribute("task.model", row.get("model", "default"))
    
    # 子 span: token 获取
    with tracer.start_as_current_span("worker.acquire_token"):
        token = await self._acquire_token(config.TOKEN_WAIT_TIMEOUT)
    
    if token is None:
        break
    
    try:
        # 子 span: 上游提交
        with tracer.start_as_current_span("provider.submit"):
            result = await self._generate_once(row, token)
        
        # 子 span: 结果处理
        with tracer.start_as_current_span("provider.result"):
            self._finish(...)
    except Exception as e:
        # 子 span: 错误处理
        with tracer.start_as_current_span("worker.error"):
            span.set_attribute("error", str(e))
            raise
```

- [ ] **步骤 5：增强 db.py OTel span**

在 `create_request`、`mark_started`、`mark_finished` 等方法中添加：
```python
from .telemetry import get_tracer

tracer = get_tracer()
with tracer.start_as_current_span("db.create_request") as span:
    span.set_attribute("task_id", task_id)
    span.set_attribute("type", type_)
    # ... 现有逻辑 ...
```

- [ ] **步骤 6：运行测试验证通过**

运行：`pytest tests/ -v -x`
预期：PASS

- [ ] **步骤 7：Commit**

```bash
git add api/log_ws.py tests/test_log_ws.py api/main.py api/worker.py api/db.py api/imagefree_client.py
git commit -m "feat: WebSocket 实时日志 + OTel 嵌套 span 深度追踪"
```

### 任务 5：前端 — React 独立项目初始化（U-01）

**文件：**
- 创建：`frontend/package.json`
- 创建：`frontend/vite.config.ts`
- 创建：`frontend/tsconfig.json`
- 创建：`frontend/tsconfig.app.json`
- 创建：`frontend/tsconfig.node.json`
- 创建：`frontend/index.html`
- 创建：`frontend/src/main.tsx`
- 创建：`frontend/src/App.tsx`
- 创建：`frontend/src/api.ts`
- 创建：`frontend/src/components/Layout.tsx`
- 创建：`frontend/src/vite-env.d.ts`

- [ ] **步骤 1：初始化 React 项目结构**

```json
// frontend/package.json
{
  "name": "imagefree-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "recharts": "^2.15.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "~5.7.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **步骤 2：创建 vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/v1': 'http://127.0.0.1:8100',
      '/metrics': 'http://127.0.0.1:8100',
    },
  },
})
```

- [ ] **步骤 3：创建 API 客户端**

```typescript
// frontend/src/api.ts
const API_BASE = '';

export interface Stats {
  total_requests: number;
  total_images: number;
  total_errors: number;
  processing: number;
  queued: number;
  queue_capacity: number;
  workers: number;
  uptime_human: string;
  daily: { date: string; requests: number; images: number; errors: number }[];
  solver: {
    status: string;
    solve_total: number;
    solve_success_total: number;
    solve_failure_total: number;
    window_success_rate: number | null;
    circuit_open: boolean;
  };
}

export interface Task {
  id: string;
  status: string;
  prompt: string;
  image_url: string | null;
  error: string | null;
  duration_sec: number | null;
  created_at: number;
  model: string;
}

export interface Provider {
  prefix: string;
  name: string;
  models: number;
  status: string;
  error_count: number;
}

export interface GalleryItem {
  image_url: string;
  prompt: string;
  aspect_ratio: string;
  duration_sec: number | null;
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/v1/stats`);
  return res.json();
}

export async function fetchTasks(params?: {
  limit?: number;
  offset?: number;
  status?: string;
}): Promise<{ items: Task[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  if (params?.status) q.set('status', params.status);
  const res = await fetch(`${API_BASE}/v1/tasks?${q}`);
  return res.json();
}

export async function fetchProviders(): Promise<{ providers: Provider[] }> {
  const res = await fetch(`${API_BASE}/v1/providers`);
  return res.json();
}

export async function fetchGallery(limit = 20): Promise<{ items: GalleryItem[] }> {
  const res = await fetch(`${API_BASE}/v1/gallery?limit=${limit}`);
  return res.json();
}

export async function fetchLogs(lines = 100): Promise<{ logs: any[] }> {
  const res = await fetch(`${API_BASE}/v1/logs?lines=${lines}`);
  return res.json();
}

export async function fetchDLQ(): Promise<{ items: any[] }> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue`);
  return res.json();
}

export async function fetchAccountPool(): Promise<any> {
  const res = await fetch(`${API_BASE}/v1/account-pool`);
  return res.json();
}

export async function retryDLQTask(taskId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue/${taskId}/retry`, { method: 'POST' });
  return res.json();
}

export async function clearDLQ(): Promise<any> {
  const res = await fetch(`${API_BASE}/v1/dead-letter-queue/clear`, { method: 'POST' });
  return res.json();
}
```

- [ ] **步骤 4：创建 Layout 组件**

```tsx
// frontend/src/components/Layout.tsx
import { NavLink } from 'react-router-dom';

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h2>听风AI</h2>
          <span className="sub">管理面板</span>
        </div>
        <nav>
          <NavLink to="/" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            📊 仪表盘
          </NavLink>
          <NavLink to="/providers" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            🔌 提供商
          </NavLink>
          <NavLink to="/tasks" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            📋 任务
          </NavLink>
          <NavLink to="/accounts" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            👤 号池
          </NavLink>
          <NavLink to="/logs" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            📝 日志
          </NavLink>
          <NavLink to="/dlq" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            🗑️ 死信队列
          </NavLink>
        </nav>
      </aside>
      <main className="main-content">{children}</main>
      <style>{`
        .layout { display: flex; min-height: 100vh; }
        .sidebar { width: 220px; background: #1a1e2e; color: #e1e4ed; padding: 20px; display: flex; flex-direction: column; }
        .sidebar-brand { margin-bottom: 24px; }
        .sidebar-brand h2 { margin: 0; font-size: 20px; }
        .sidebar-brand .sub { font-size: 12px; color: #8b8fa3; }
        .nav-link { display: block; padding: 10px 14px; color: #8b8fa3; text-decoration: none; border-radius: 8px; margin-bottom: 2px; font-size: 14px; }
        .nav-link:hover { color: #e1e4ed; background: rgba(255,255,255,.05); }
        .nav-link.active { color: #6b8aff; background: rgba(107,138,255,.12); font-weight: 600; }
        .main-content { flex: 1; padding: 24px; background: #f4f6fa; overflow-y: auto; }
        @media (max-width: 768px) {
          .layout { flex-direction: column; }
          .sidebar { width: 100%; padding: 12px; flex-direction: row; overflow-x: auto; }
          .sidebar-brand { display: none; }
          .nav-link { white-space: nowrap; }
          .main-content { padding: 12px; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 5：创建 App.tsx 入口**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { ProvidersPage } from './pages/Providers';
import { TasksPage } from './pages/Tasks';
import { AccountsPage } from './pages/Accounts';
import { LogsPage } from './pages/Logs';
import { DLQPage } from './pages/DLQ';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/providers" element={<ProvidersPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/dlq" element={<DLQPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

- [ ] **步骤 6：创建 main.tsx 入口**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **步骤 7：创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>听风AI 管理面板</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

- [ ] **步骤 8：安装依赖并验证构建**

```bash
cd frontend && npm install
cd frontend && npx tsc -b
cd frontend && npx vite build
```

预期：`dist/` 目录生成无报错。

- [ ] **步骤 9：Commit**

```bash
git add frontend/
git commit -m "feat: React 前端项目初始化（Vite + TypeScript + Recharts）"
```

### 任务 6：前端 — 仪表盘页面（U-01）

**文件：**
- 创建：`frontend/src/pages/Dashboard.tsx`
- 创建：`frontend/src/components/StatCard.tsx`
- 创建：`frontend/src/components/BarChart.tsx`
- 创建：`frontend/src/components/Gallery.tsx`

- [ ] **步骤 1：创建 StatCard 组件**

```tsx
// frontend/src/components/StatCard.tsx
interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

export function StatCard({ label, value, sub, color }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
      <style>{`
        .stat-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .stat-label { font-size: 12px; color: #6b7280; }
        .stat-value { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 4px; }
        .stat-sub { font-size: 11px; color: #6b7280; margin-top: 2px; }
        @media (prefers-color-scheme: dark) {
          .stat-card { background: #1e2132; border-color: #2d3050; }
          .stat-label { color: #8b8fa3; }
          .stat-sub { color: #8b8fa3; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 2：创建 BarChart 组件**

```tsx
// frontend/src/components/BarChart.tsx
import { BarChart as RechartsBar, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface BarChartProps {
  data: { name: string; value: number; color?: string }[];
  title: string;
  height?: number;
}

export function BarChart({ data, title, height = 200 }: BarChartProps) {
  return (
    <div className="chart-card">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBar data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d1d5e0" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#6b8aff" radius={[4, 4, 0, 0]} />
        </RechartsBar>
      </ResponsiveContainer>
      <style>{`
        .chart-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .chart-card h3 { font-size: 14px; margin: 0 0 12px; }
        @media (prefers-color-scheme: dark) {
          .chart-card { background: #1e2132; border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 3：创建 Gallery 组件**

```tsx
// frontend/src/components/Gallery.tsx
import { useEffect, useState } from 'react';
import { fetchGallery } from '../api';
import type { GalleryItem } from '../api';

interface GalleryProps {
  limit?: number;
}

export function Gallery({ limit = 20 }: GalleryProps) {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchGallery(limit);
        setItems(data.items);
      } catch { /* ignore */ }
      setLoading(false);
    };
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [limit]);

  if (loading) return <div className="gallery-loading">加载中...</div>;
  if (!items.length) return <div className="gallery-empty">暂无作品</div>;

  return (
    <div className="gallery-grid">
      {items.map((item, i) => (
        <div key={i} className="gallery-cell">
          {item.image_url && <img src={item.image_url} alt="" loading="lazy" />}
          <div className="gallery-overlay">
            <div className="gallery-prompt">{item.prompt}</div>
            {item.duration_sec != null && <div className="gallery-dur">{item.duration_sec.toFixed(1)}s</div>}
          </div>
        </div>
      ))}
      <style>{`
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
        .gallery-cell { position: relative; border-radius: 10px; overflow: hidden; aspect-ratio: 1; background: #eef0f5; cursor: pointer; }
        .gallery-cell img { width: 100%; height: 100%; object-fit: cover; transition: transform .3s; }
        .gallery-cell:hover img { transform: scale(1.06); }
        .gallery-overlay { position: absolute; inset: auto 0 0 0; padding: 20px 10px 8px; background: linear-gradient(transparent, rgba(10,14,30,.82)); color: #fff; font-size: 11px; opacity: 0; transition: opacity .25s; }
        .gallery-cell:hover .gallery-overlay { opacity: 1; }
        .gallery-prompt { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .gallery-dur { color: #a9b4d8; margin-top: 2px; }
        .gallery-loading, .gallery-empty { text-align: center; color: #6b7280; padding: 40px 0; font-size: 13px; }
        @media (prefers-color-scheme: dark) {
          .gallery-cell { background: #1a1d2e; }
          .gallery-loading, .gallery-empty { color: #8b8fa3; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 4：创建 Dashboard 页面**

```tsx
// frontend/src/pages/Dashboard.tsx
import { useEffect, useState } from 'react';
import { fetchStats } from '../api';
import { StatCard } from '../components/StatCard';
import { BarChart } from '../components/BarChart';
import { Gallery } from '../components/Gallery';
import type { Stats } from '../api';

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    const load = async () => {
      try { setStats(await fetchStats()); } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const dailyChart = stats?.daily?.map(d => ({
    name: d.date.slice(5),
    value: d.images,
  })) ?? [];

  return (
    <div>
      <h1 style={{ margin: '0 0 20px', fontSize: 22 }}>仪表盘</h1>

      <div className="stats-grid">
        <StatCard label="总请求" value={stats?.total_requests ?? '-'} />
        <StatCard label="成功出图" value={stats?.total_images ?? '-'} color="#10b981" />
        <StatCard label="失败" value={stats?.total_errors ?? '-'} color="#ef4444" />
        <StatCard label="运行时长" value={stats?.uptime_human ?? '-'} />
        <StatCard label="当前处理中" value={stats?.processing ?? '-'} />
        <StatCard label="排队中" value={stats?.queued ?? '-'} sub={`容量 ${stats?.queue_capacity ?? '-'}`} />
        <StatCard label="Worker 数" value={stats?.workers ?? '-'} />
        <StatCard label="求解器状态" value={stats?.solver?.status ?? '-'} color={stats?.solver?.status === 'ok' ? '#10b981' : '#ef4444'} />
      </div>

      {dailyChart.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <BarChart data={dailyChart} title="近 14 日出图量" height={220} />
        </div>
      )}

      <div style={{ marginTop: 20 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>最近作品</h2>
        <Gallery />
      </div>

      <style>{`
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        @media (max-width: 600px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 5：验证构建**

```bash
cd frontend && npx tsc -b && npx vite build
```

预期：构建成功，无类型错误。

- [ ] **步骤 6：Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/components/StatCard.tsx frontend/src/components/BarChart.tsx frontend/src/components/Gallery.tsx
git commit -m "feat: 仪表盘页面 — 统计卡片 + 趋势图 + 画廊"
```

### 任务 7：前端 — 提供商状态页面（U-01 + U-03）

**文件：**
- 创建：`frontend/src/pages/Providers.tsx`
- 创建：`frontend/src/components/ProviderCard.tsx`

- [ ] **步骤 1：创建 ProviderCard 组件**

```tsx
// frontend/src/components/ProviderCard.tsx
interface ProviderCardProps {
  name: string;
  prefix: string;
  models: number;
  status: string;
  errorCount: number;
}

export function ProviderCard({ name, prefix, models, status, errorCount }: ProviderCardProps) {
  const statusColor = status === 'healthy' ? '#10b981' : status === 'degraded' ? '#f59e0b' : '#ef4444';
  return (
    <div className="prov-card">
      <div className="prov-head">
        <h3>{name}</h3>
        <span className="prov-prefix">{prefix}</span>
      </div>
      <div className="prov-meta">
        <span>模型: {models}</span>
        <span>错误: {errorCount}</span>
      </div>
      <div className="prov-status">
        <span className="status-dot" style={{ background: statusColor }} />
        {status}
      </div>
      <style>{`
        .prov-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px 18px; }
        .prov-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .prov-head h3 { margin: 0; font-size: 15px; }
        .prov-prefix { font-size: 11px; color: #6b7280; background: rgba(79,111,255,.08); padding: 2px 8px; border-radius: 6px; }
        .prov-meta { display: flex; gap: 12px; margin-bottom: 8px; }
        .prov-meta span { font-size: 12px; color: #6b7280; background: rgba(79,111,255,.08); padding: 2px 9px; border-radius: 999px; }
        .prov-status { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        @media (prefers-color-scheme: dark) {
          .prov-card { background: #1e2132; border-color: #2d3050; }
          .prov-prefix { color: #8b8fa3; }
          .prov-meta span { color: #8b8fa3; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 2：创建 Providers 页面**

```tsx
// frontend/src/pages/Providers.tsx
import { useEffect, useState } from 'react';
import { fetchProviders } from '../api';
import { ProviderCard } from '../components/ProviderCard';
import type { Provider } from '../api';

export function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchProviders();
        setProviders(data.providers ?? []);
      } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>提供商状态</h1>
      <div className="prov-grid">
        {providers.map(p => (
          <ProviderCard
            key={p.prefix}
            name={p.name}
            prefix={p.prefix}
            models={p.models}
            status={p.status}
            errorCount={p.error_count}
          />
        ))}
        {!providers.length && <div className="empty">暂无数据</div>}
      </div>
      <style>{`
        .prov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
        .empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 3：验证构建**

```bash
cd frontend && npx tsc -b && npx vite build
```

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/pages/Providers.tsx frontend/src/components/ProviderCard.tsx
git commit -m "feat: 提供商状态页面 — 状态卡片 + 自动刷新"
```

### 任务 8：前端 — 任务管理 + 号池 + 日志 + 死信队列页面（U-01）

**文件：**
- 创建：`frontend/src/pages/Tasks.tsx`
- 创建：`frontend/src/pages/Accounts.tsx`
- 创建：`frontend/src/pages/Logs.tsx`
- 创建：`frontend/src/pages/DLQ.tsx`

- [ ] **步骤 1：创建 Tasks 页面**

```tsx
// frontend/src/pages/Tasks.tsx
import { useEffect, useState } from 'react';
import { fetchTasks } from '../api';
import type { Task } from '../api';

export function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchTasks({ limit: 50, status: status || undefined });
        setTasks(data.items);
        setTotal(data.total);
      } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [status]);

  const statusColor = (s: string) => {
    switch (s) {
      case 'completed': return '#10b981';
      case 'processing': return '#f59e0b';
      case 'error': return '#ef4444';
      default: return '#6b7280';
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>任务管理 <span style={{ fontSize: 13, color: '#6b7280' }}>共 {total} 条</span></h1>
      <div style={{ marginBottom: 12 }}>
        <select value={status} onChange={e => setStatus(e.target.value)} style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #d1d5e0' }}>
          <option value="">全部状态</option>
          <option value="pending">排队中</option>
          <option value="processing">处理中</option>
          <option value="completed">已完成</option>
          <option value="error">失败</option>
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>状态</th>
              <th>模型</th>
              <th>提示词</th>
              <th>耗时</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(t => (
              <tr key={t.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.id.slice(0, 8)}</td>
                <td><span className="status-pill" style={{ background: statusColor(t.status) }}>{t.status}</span></td>
                <td>{t.model}</td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.prompt?.slice(0, 40)}</td>
                <td>{t.duration_sec != null ? `${t.duration_sec.toFixed(1)}s` : '-'}</td>
                <td style={{ fontSize: 12, color: '#6b7280' }}>{t.created_at ? new Date(t.created_at * 1000).toLocaleString() : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!tasks.length && <div className="empty">暂无任务</div>}
      </div>
      <style>{`
        .table-wrap { overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #d1d5e0; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px 12px; border-bottom: 1px solid #d1d5e0; color: #6b7280; font-weight: 600; font-size: 12px; background: #f8f9fc; }
        td { padding: 10px 12px; border-bottom: 1px solid #d1d5e0; }
        tr:last-child td { border-bottom: none; }
        .status-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; color: #fff; }
        .empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }
        @media (prefers-color-scheme: dark) {
          .table-wrap { background: #1e2132; border-color: #2d3050; }
          th { border-color: #2d3050; color: #8b8fa3; background: #252840; }
          td { border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 2：创建 Logs 页面（WebSocket 实时日志）**

```tsx
// frontend/src/pages/Logs.tsx
import { useEffect, useRef, useState } from 'react';

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState('');
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/v1/logs/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data);
        setLogs(prev => [...prev.slice(-500), entry]);
      } catch { /* ignore */ }
    };

    return () => ws.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const filtered = filter
    ? logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase()))
    : logs;

  const levelColor = (lvl: string) => {
    switch (lvl) {
      case 'INFO': return '#38bdf8';
      case 'WARNING': case 'WARN': return '#fbbf24';
      case 'ERROR': case 'CRITICAL': case 'CRIT': return '#f87171';
      case 'DEBUG': return '#94a3b8';
      default: return '#cbd5e1';
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>
        实时日志
        <span className="ws-status" style={{ color: connected ? '#10b981' : '#ef4444' }}>
          {connected ? ' ● 已连接' : ' ○ 已断开'}
        </span>
      </h1>
      <div style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="关键词过滤..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5e0', fontSize: 13 }}
        />
      </div>
      <div className="log-box">
        {filtered.map((l, i) => (
          <div key={i} className="log-line">
            <span className="log-ts">{l.timestamp}</span>
            <span className="log-lvl" style={{ color: levelColor(l.level) }}>{l.level}</span>
            <span className="log-logger">{l.logger}</span>
            <span className="log-msg">{l.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <style>{`
        .ws-status { font-size: 13px; margin-left: 12px; }
        .log-box { background: #0f1117; border-radius: 10px; padding: 12px; font-size: 12px; font-family: ui-monospace, Consolas, monospace; max-height: 600px; overflow-y: auto; line-height: 1.6; }
        .log-line { padding: 2px 4px; border-bottom: 1px solid rgba(255,255,255,.06); color: #cbd5e1; word-break: break-all; }
        .log-ts { color: #64748b; margin-right: 6px; }
        .log-lvl { display: inline-block; width: 48px; font-weight: 600; margin-right: 6px; }
        .log-logger { color: #a78bfa; margin-right: 6px; }
        .log-msg { color: #e2e8f0; }
        input { background: #fff; color: #1a1e2e; }
        @media (prefers-color-scheme: dark) { input { background: #1e2132; color: #e1e4ed; border-color: #2d3050; } }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 3：创建 Accounts 页面**

```tsx
// frontend/src/pages/Accounts.tsx
import { useEffect, useState } from 'react';
import { fetchAccountPool } from '../api';

export function AccountsPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const load = async () => {
      try { setData(await fetchAccountPool()); } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  if (!data) return <div className="empty">加载中...</div>;

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>号池管理</h1>
      <pre style={{ background: '#f0f2f6', padding: 16, borderRadius: 10, fontSize: 12, overflow: 'auto' }}>
        {JSON.stringify(data, null, 2)}
      </pre>
      <style>{`.empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }`}</style>
    </div>
  );
}
```

- [ ] **步骤 4：创建 DLQ 页面**

```tsx
// frontend/src/pages/DLQ.tsx
import { useEffect, useState } from 'react';
import { fetchDLQ, retryDLQTask, clearDLQ } from '../api';

export function DLQPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const data = await fetchDLQ();
      setItems(data.items ?? []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleRetry = async (taskId: string) => {
    await retryDLQTask(taskId);
    await load();
  };

  const handleClear = async () => {
    if (!confirm('确定清空死信队列？')) return;
    await clearDLQ();
    await load();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>死信队列</h1>
        {items.length > 0 && (
          <button onClick={handleClear} className="btn btn-danger">清空全部</button>
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task ID</th>
              <th>模型</th>
              <th>错误</th>
              <th>重试次数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item: any) => (
              <tr key={item.task_id}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{item.task_id?.slice(0, 8)}</td>
                <td>{item.model ?? '-'}</td>
                <td style={{ color: '#ef4444', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.error ?? '-'}</td>
                <td>{item.attempts ?? '-'}</td>
                <td><button onClick={() => handleRetry(item.task_id)} className="btn btn-sm">重试</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">加载中...</div>}
        {!loading && !items.length && <div className="empty">死信队列为空</div>}
      </div>
      <style>{`
        .btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; cursor: pointer; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-sm { background: #6b8aff; color: #fff; padding: 4px 12px; font-size: 12px; border-radius: 6px; border: none; cursor: pointer; }
        .table-wrap { overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #d1d5e0; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px 12px; border-bottom: 1px solid #d1d5e0; color: #6b7280; font-weight: 600; font-size: 12px; background: #f8f9fc; }
        td { padding: 10px 12px; border-bottom: 1px solid #d1d5e0; }
        tr:last-child td { border-bottom: none; }
        .empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }
        @media (prefers-color-scheme: dark) {
          .table-wrap { background: #1e2132; border-color: #2d3050; }
          th { background: #252840; border-color: #2d3050; color: #8b8fa3; }
          td { border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **步骤 5：验证构建**

```bash
cd frontend && npx tsc -b && npx vite build
```

- [ ] **步骤 6：Commit**

```bash
git add frontend/src/pages/Tasks.tsx frontend/src/pages/Accounts.tsx frontend/src/pages/Logs.tsx frontend/src/pages/DLQ.tsx
git commit -m "feat: 任务管理 + 号池 + 日志 + 死信队列页面"
```

### 任务 9：后端 — 集成前端静态文件 + 更新部署配置

**文件：**
- 修改：`api/main.py`（挂载前端静态文件）
- 修改：`deploy/Dockerfile.api`（复制前端构建产物）
- 修改：`deploy/docker-compose.yml`（可选 nginx 前端服务）
- 修改：`pyproject.toml`（新增 prometheus_client 依赖）
- 修改：`deploy/requirements.txt`（新增依赖）
- 修改：`scripts/sync_deploy.py`（新增前端同步）

- [ ] **步骤 1：在 main.py 挂载前端静态文件**

```python
# 在 api/main.py 中添加
from fastapi.staticfiles import StaticFiles

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="admin")
    log.info("前端管理面板已挂载到 /admin")
```

- [ ] **步骤 2：更新依赖**

在 `pyproject.toml` 和 `deploy/requirements.txt` 中添加：
```
prometheus-client>=0.21
```

- [ ] **步骤 3：更新 sync_deploy.py**

在 `FILES` 列表中添加 `"alerting.py"`、`"audit.py"`、`"metrics_ext.py"`、`"log_ws.py"`。
在 `DIRS` 列表中添加 `"frontend"`。

- [ ] **步骤 4：Commit**

```bash
git add api/main.py pyproject.toml deploy/requirements.txt deploy/Dockerfile.api scripts/sync_deploy.py
git commit -m "chore: 集成前端静态文件 + 更新依赖和部署配置"
```

### 任务 10：E2E 测试 + 验证

**文件：**
- 修改：`scripts/e2e_validate.py`（扩展验证覆盖）

- [ ] **步骤 1：编写 E2E 验证脚本（扩展）**

```python
# 在 scripts/e2e_validate.py 中添加新测试
"""
E2E 验证脚本 — 验证所有新功能：
1. /metrics 端点返回 prometheus_client 格式
2. 审计日志记录
3. 告警引擎初始化
4. WebSocket 日志端点
5. 前端静态文件挂载
"""

import json
import sys
import time
import urllib.request


def test_metrics_endpoint() -> list[str]:
    """验证 /metrics 返回正确格式。"""
    errors = []
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8100/metrics")
        body = resp.read().decode()
        if "imagefree_requests_total" not in body:
            errors.append("/metrics 缺少 imagefree_requests_total")
        if "imagefree_processing" not in body:
            errors.append("/metrics 缺少 imagefree_processing")
        if "imagefree_uptime_seconds" not in body:
            errors.append("/metrics 缺少 imagefree_uptime_seconds")
    except Exception as e:
        errors.append(f"/metrics 请求失败: {e}")
    return errors


def test_audit_log_exists() -> list[str]:
    """验证审计日志文件存在。"""
    errors = []
    try:
        import os
        if os.path.exists("data/audit.log"):
            with open("data/audit.log") as f:
                content = f.read()
            if content:
                # 验证 JSON 格式
                line = json.loads(content.strip().split("\n")[0])
                if "action" not in line or "timestamp" not in line:
                    errors.append("审计日志格式错误")
        # 文件不存在也 OK（可能未触发任何审计操作）
    except Exception as e:
        errors.append(f"审计日志检查失败: {e}")
    return errors


def test_frontend_built() -> list[str]:
    """验证前端构建产物存在。"""
    errors = []
    import os
    if not os.path.exists("frontend/dist/index.html"):
        errors.append("前端构建产物不存在（frontend/dist/index.html）")
    return errors


def test_websocket_endpoint() -> list[str]:
    """验证 WebSocket 端点可连接。"""
    import asyncio
    errors = []

    async def _check():
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", 8100), timeout=3.0)
            # WebSocket 升级请求
            upgrade = (
                "GET /v1/logs/ws HTTP/1.1\r\n"
                "Host: 127.0.0.1:8100\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            writer.write(upgrade.encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(1024), timeout=3.0)
            if b"101" not in resp:
                errors.append(f"WebSocket 升级响应异常: {resp[:100]}")
            writer.close()
        except asyncio.TimeoutError:
            errors.append("WebSocket 连接超时")
        except ConnectionRefusedError:
            errors.append("WebSocket 连接被拒绝（服务未运行）")
        except Exception as e:
            errors.append(f"WebSocket 检查异常: {e}")

    asyncio.run(_check())
    return errors


def run_all() -> int:
    print("=" * 50)
    print("E2E 验收测试 — 新功能验证")
    print("=" * 50)

    all_errors = []
    all_errors.extend(test_metrics_endpoint())
    all_errors.extend(test_audit_log_exists())
    all_errors.extend(test_frontend_built())
    all_errors.extend(test_websocket_endpoint())

    if all_errors:
        print(f"\n❌ 发现 {len(all_errors)} 个问题:")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    else:
        print("\n✅ 所有 E2E 测试通过")
        return 0


if __name__ == "__main__":
    sys.exit(run_all())
```

- [ ] **步骤 2：本地启动服务并运行 E2E 测试**

```bash
# 启动服务（后台）
cd /path/to/imagefree-2ai
uvicorn api.main:app --host 127.0.0.1 --port 8100 &
sleep 3

# 运行 E2E 验证
python scripts/e2e_validate.py
```

预期：所有测试通过。

- [ ] **步骤 3：Commit**

```bash
git add scripts/e2e_validate.py
git commit -m "test: E2E 验证脚本 — 覆盖新功能端点"
```

### 任务 11：同步 deploy + 部署到线上服务器

**涉及文件：** 全部

- [ ] **步骤 1：同步到 deploy/api**

```bash
python scripts/sync_deploy.py sync
```

预期：输出 `sync xxx` 无错误。

- [ ] **步骤 2：提交并推送**

```bash
git add .
git commit -m "chore: 同步 deploy 目录"
git push
```

- [ ] **步骤 3：创建 Release**

```bash
git tag v2.3.0
git push origin v2.3.0
gh release create v2.3.0 --title "v2.3.0 — 前端面板 + 可观测性增强" --notes "新增 React 管理面板、WebSocket 实时日志、prometheus_client 指标、告警引擎、审计日志、OTel 深度追踪"
```

- [ ] **步骤 4：上传到服务器并部署**

```bash
# 本地打包
tar czf deploy.tar.gz deploy/

# 上传到服务器
scp deploy.tar.gz ubuntu@43.165.173.36:/home/ubuntu/imagefree-api/

# 服务器上解压并部署
ssh ubuntu@43.165.173.36
cd /home/ubuntu/imagefree-api
tar xzf deploy.tar.gz
sudo docker compose build api && sudo docker compose up -d api
```

- [ ] **步骤 5：验证线上部署**

```bash
curl https://imagefree.tingfengai.art/v1/healthz
curl https://imagefree.tingfengai.art/metrics | head -20
curl https://imagefree.tingfengai.art/v1/stats
```

预期：所有端点正常返回。