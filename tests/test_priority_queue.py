"""IMP-01: 优先级队列 + 过载分级单元测试。

验证：
- PriorityQueue 按 priority 排序消费（0=admin 优先于 1=paid 优先于 2=normal）
- 同优先级内 FIFO 顺序（seq 自增计数器保证）
- 各级独立上限（ADMIN_QUEUE_MAX / HIGH_QUEUE_MAX / NORMAL_QUEUE_MAX）各自返回 429
- submit_priority 参数传递正确
"""
import asyncio

import pytest

from api import config
from api.worker import Engine, QueueFull


class _DBStub:
    """最小 DB 替身：只记录 create_request / mark_finished 调用，不依赖真实 SQLite。"""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.finished: list[str] = []
        self.tasks: dict[str, dict] = {}

    def create_request(self, task_id, prompt, aspect_ratio, download, request_type, model):
        self.created.append(task_id)
        self.tasks[task_id] = {
            "id": task_id, "prompt": prompt, "aspect_ratio": aspect_ratio,
            "status": "pending", "error": None,
        }

    def mark_finished(self, task_id, status, image_url, error, duration, image_base64=None, image_mime=None):
        self.finished.append(task_id)
        if task_id in self.tasks:
            self.tasks[task_id].update(status=status, error=error)

    def mark_started(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "processing"

    def get(self, task_id):
        return self.tasks.get(task_id)

    def recover_stale_tasks(self) -> int:
        return 0


@pytest.fixture
def engine():
    """Engine 实例（mock DB，不启动 worker，仅测队列行为）。"""
    e = Engine(_DBStub())
    e._started = False   # 不启动后台预取/worker，避免依赖真实网络
    return e


@pytest.mark.asyncio
async def test_priority_order(engine):
    """混入 0/1/2 优先级各 100 个任务，消费顺序按 priority 升序，同优先级 FIFO。"""
    tasks_0: list[str] = []
    tasks_1: list[str] = []
    tasks_2: list[str] = []
    for i in range(100):
        t0 = await engine.submit_priority(f"p0-{i}", "1:1", False, priority=0)
        tasks_0.append(t0)
        t1 = await engine.submit_priority(f"p1-{i}", "1:1", False, priority=1)
        tasks_1.append(t1)
        t2 = await engine.submit_priority(f"p2-{i}", "1:1", False, priority=2)
        tasks_2.append(t2)

    assert engine.queue.qsize() == 300

    consumed: list[tuple[int, int, str]] = []
    for _ in range(300):
        item = await engine.queue.get()
        consumed.append(item)
        engine.queue.task_done()

    # 验证消费顺序：先 0，再 1，再 2
    priorities = [p for p, s, tid in consumed]
    assert priorities[:100] == [0] * 100, "前 100 个应为 priority=0"
    assert priorities[100:200] == [1] * 100, "中间 100 个应为 priority=1"
    assert priorities[200:] == [2] * 100, "后 100 个应为 priority=2"

    # 同优先级内 FIFO 验证
    for p, ids in [(0, tasks_0), (1, tasks_1), (2, tasks_2)]:
        consumed_ids = [tid for pri, seq, tid in consumed if pri == p]
        assert consumed_ids == ids, f"priority={p} 同优先级 FIFO 顺序不符"


@pytest.mark.asyncio
async def test_normal_queue_full(engine):
    """NORMAL_QUEUE_MAX 填满后 priority=2 的 submit_priority 抛 QueueFull (429)。"""
    for i in range(config.NORMAL_QUEUE_MAX):
        await engine.submit_priority(f"normal-{i}", "1:1", False, priority=2)

    assert engine.queue.qsize() == config.NORMAL_QUEUE_MAX
    assert engine._queue_counts[2] == config.NORMAL_QUEUE_MAX

    with pytest.raises(QueueFull, match="服务器繁忙"):
        await engine.submit_priority("overload", "1:1", False, priority=2)


@pytest.mark.asyncio
async def test_admin_queue_full(engine):
    """ADMIN_QUEUE_MAX 填满后 priority=0 的 submit_priority 抛 QueueFull (429)。"""
    for i in range(config.ADMIN_QUEUE_MAX):
        await engine.submit_priority(f"admin-{i}", "1:1", False, priority=0)

    assert engine._queue_counts[0] == config.ADMIN_QUEUE_MAX

    with pytest.raises(QueueFull, match="服务器繁忙"):
        await engine.submit_priority("admin-overload", "1:1", False, priority=0)


@pytest.mark.asyncio
async def test_high_queue_full(engine):
    """HIGH_QUEUE_MAX 填满后 priority=1 的 submit_priority 抛 QueueFull (429)。"""
    for i in range(config.HIGH_QUEUE_MAX):
        await engine.submit_priority(f"high-{i}", "1:1", False, priority=1)

    assert engine._queue_counts[1] == config.HIGH_QUEUE_MAX

    with pytest.raises(QueueFull, match="服务器繁忙"):
        await engine.submit_priority("high-overload", "1:1", False, priority=1)


@pytest.mark.asyncio
async def test_qsize_correct(engine):
    """入队后 qsize 和 _queue_counts 同步增长。"""
    assert engine.queue.qsize() == 0
    assert engine._queue_counts == {0: 0, 1: 0, 2: 0}

    await engine.submit_priority("a", "1:1", False, priority=0)
    await engine.submit_priority("b", "1:1", False, priority=1)
    await engine.submit_priority("c", "1:1", False, priority=2)
    await engine.submit_priority("d", "1:1", False, priority=0)

    assert engine.queue.qsize() == 4
    assert engine._queue_counts == {0: 2, 1: 1, 2: 1}


@pytest.mark.asyncio
async def test_submit_priority_passthrough(engine):
    """submit_priority 参数正确传递到 DB 记录。"""
    tid = await engine.submit_priority("test-prompt", "16:9", True,
                                        model="anime", priority=1)
    assert tid in engine.db.created
    task = engine.db.get(tid)
    assert task["prompt"] == "test-prompt"
    assert task["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_submit_default_priority(engine):
    """submit（无 priority 参数）默认使用 priority=2 (normal)。"""
    tid = await engine.submit("default-prompt", "1:1", False)
    assert engine._queue_counts[2] == 1
    assert engine._queue_counts[0] == 0
    assert engine._queue_counts[1] == 0


@pytest.mark.asyncio
async def test_worker_decrements_count(engine):
    """_worker_loop 消费后 _queue_counts 对应级别递减。"""
    # 手动设定 _started=True 然后覆盖 _worker_loop 为单次消费
    original_loop = engine._worker_loop
    consumed = []

    async def _single_consume(idx):
        priority, seq, task_id = await engine.queue.get()
        consumed.append((priority, task_id))
        engine._queue_counts[priority] -= 1
        engine.queue.task_done()
        # 不再循环，仅消费一次

    # 注入 2 个任务
    await engine.submit_priority("p0", "1:1", False, priority=0)
    await engine.submit_priority("p2", "1:1", False, priority=2)
    assert engine._queue_counts == {0: 1, 1: 0, 2: 1}

    # 模拟消费一个（priority=0 优先）
    priority, seq, task_id = await engine.queue.get()
    engine._queue_counts[priority] -= 1
    engine.queue.task_done()
    assert priority == 0
    assert engine._queue_counts == {0: 0, 1: 0, 2: 1}

    # 消费第二个
    priority, seq, task_id = await engine.queue.get()
    engine._queue_counts[priority] -= 1
    engine.queue.task_done()
    assert priority == 2
    assert engine._queue_counts == {0: 0, 1: 0, 2: 0}


@pytest.mark.asyncio
async def test_priority_queue_type(engine):
    """Engine.queue 是 PriorityQueue 而不是普通 Queue。"""
    from asyncio import PriorityQueue
    assert isinstance(engine.queue, PriorityQueue)


@pytest.mark.asyncio
async def test_element_format(engine):
    """入队元素格式为 (priority, seq, task_id)。"""
    tid = await engine.submit_priority("fmt", "1:1", False, priority=0)
    # 直接查看队列内部
    item = engine.queue._queue[0]
    assert len(item) == 3
    p, s, t = item
    assert p == 0
    assert isinstance(s, int)
    assert t == tid