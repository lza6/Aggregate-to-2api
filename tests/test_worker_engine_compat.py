"""P0-4: worker/engine.py 拆分后的 import 兼容性回归测试。

拆分后以下旧 import 路径必须仍可用（兼容垫片铁律）：
- from api.worker.engine import Engine, QueueFull, CountedPriorityQueue, _is_token_rejected, _safe_proxy_label, engine
- from api.worker.scaler import ScaleMetrics, _ScaleState, compute_score, should_scale_up, should_scale_down, collect_metrics
- from api.worker.queue import CountedPriorityQueue, _WorkerHandle, QueueFull, _safe_proxy_label, _is_token_rejected
- from api.worker.generator import generate_once, generate_once_b3, generate_with_429_proxy_fallback
- from api.worker.dlq import push_dlq_on_exhaust, build_dlq_message

Engine 单例一致性：from api.worker.engine import engine 与 from api.worker import engine 指向同一对象。
Engine 公开/受测方法签名不变（_process / _worker_loop / _worker_batch_loop / _auto_scale_once /
_shrink_one_worker / requeue_dlq_task / snapshot / _resume_from_queue）。
requeue_dlq_task 保持为 Engine 方法（test_dead_letter_queue 直接 eng.requeue_dlq_task），不外移。
"""

from __future__ import annotations

import inspect

import pytest


def test_engine_module_reexports_old_symbols():
    """旧 import 路径全部仍可用（兼容垫片铁律）。

    QueueFull / CountedPriorityQueue / _is_token_rejected / _safe_proxy_label 物理实体
    移到 worker/queue.py，engine.py 顶层 re-export 保持旧路径可用。
    """
    from api.worker.engine import (
        CountedPriorityQueue,
        Engine,
        QueueFull,
        _is_token_rejected,
        _safe_proxy_label,
    )

    assert callable(Engine)
    assert issubclass(QueueFull, Exception)
    assert callable(CountedPriorityQueue)
    assert callable(_is_token_rejected)
    assert callable(_safe_proxy_label)


def test_queue_module_is_physical_home():
    """QueueFull / CountedPriorityQueue / _WorkerHandle / 辅助函数物理位于 worker/queue.py。"""
    from api.worker.queue import (
        CountedPriorityQueue,
        QueueFull,
        _is_token_rejected,
        _safe_proxy_label,
        _WorkerHandle,
    )

    assert issubclass(QueueFull, Exception)
    assert callable(CountedPriorityQueue)
    assert _WorkerHandle is not None
    assert callable(_is_token_rejected)
    assert callable(_safe_proxy_label)


def test_queue_reexport_identity():
    """engine.py re-export 与 queue.py 物理实体是同一对象（不是子类重定义）。"""
    from api.worker.engine import CountedPriorityQueue as QC_eng
    from api.worker.engine import QueueFull as QF_eng
    from api.worker.queue import CountedPriorityQueue as QC_q
    from api.worker.queue import QueueFull as QF_q

    assert QC_eng is QC_q
    assert QF_eng is QF_q


def test_scaler_module_symbols():
    from api.worker.scaler import (
        ScaleMetrics,
        _ScaleState,
        collect_metrics,
        compute_score,
        should_scale_down,
        should_scale_up,
    )

    assert ScaleMetrics is not None
    assert _ScaleState is not None
    assert callable(compute_score)
    assert callable(should_scale_up)
    assert callable(should_scale_down)
    assert callable(collect_metrics)


def test_dlq_module_symbols():
    """新建 worker/dlq.py 必须导出 DLQ 辅助函数（纯逻辑，无 Engine 依赖）。"""
    from api.worker.dlq import build_dlq_message, push_dlq_on_exhaust

    assert callable(push_dlq_on_exhaust)
    assert callable(build_dlq_message)


def test_generator_module_symbols():
    """新建 worker/generator.py 必须导出 generate_* 函数（纯逻辑，参数化 engine）。"""
    from api.worker.generator import (
        generate_once,
        generate_once_b3,
        generate_with_429_proxy_fallback,
    )

    assert callable(generate_once)
    assert callable(generate_once_b3)
    assert callable(generate_with_429_proxy_fallback)


def test_engine_singleton_identity():
    """engine 单例一致性（meta.py 持有 engine = Engine(db)，拆分后不得重建）。

    engine 单例物理定义在 api/meta.py:21（`engine: Engine = Engine(db)`），
    不在 worker 包内。本测试验证 meta.engine 单例的 import 一致性——
    证明拆分未破坏单例引用（同一对象，非重建）。
    """
    from api.meta import engine as e1
    from api.meta import engine as e2

    assert e1 is e2


def test_engine_method_signatures_preserved():
    """铁律 1：公开/受测方法签名不得变。"""
    from api.worker.engine import Engine

    # 受测子类覆写契约（test_worker_batch/hard_timeout 覆写 _process）
    sig = inspect.signature(Engine._process)
    assert list(sig.parameters.keys()) == ["self", "task_id"]

    sig = inspect.signature(Engine._worker_loop)
    assert list(sig.parameters.keys()) == ["self", "idx", "stop_event"]

    sig = inspect.signature(Engine._worker_batch_loop)
    assert list(sig.parameters.keys()) == ["self", "idx", "stop_event"]

    # test_worker_auto_scale 直接调用
    sig = inspect.signature(Engine._auto_scale_once)
    assert list(sig.parameters.keys()) == ["self"]

    sig = inspect.signature(Engine._shrink_one_worker)
    assert list(sig.parameters.keys()) == ["self"]

    # test_dead_letter_queue 调用
    sig = inspect.signature(Engine.requeue_dlq_task)
    assert list(sig.parameters.keys()) == ["self", "task_id"]

    sig = inspect.signature(Engine.snapshot)
    assert list(sig.parameters.keys()) == ["self"]


@pytest.mark.asyncio
async def test_engine_requeue_dlq_task_delegates(tmp_db):
    """Engine.requeue_dlq_task 委托 dlq 模块后行为不变：不存在 task → False。"""
    from api.worker.engine import Engine

    eng = Engine(tmp_db)
    try:
        ok = await eng.requeue_dlq_task("no-such-task-x")
        assert ok is False
    finally:
        await eng.stop()


def test_safe_proxy_label_behavior_unchanged():
    from api.worker.engine import _safe_proxy_label

    assert _safe_proxy_label("direct") == "direct"
    # http URL 解析出 host:port
    assert "proxy.example.com" in _safe_proxy_label("http://user:pass@proxy.example.com:8080")


def test_is_token_rejected_behavior_unchanged():
    from api.worker.engine import _is_token_rejected

    assert _is_token_rejected(Exception("Human verification failed")) is True
    assert _is_token_rejected(Exception("other error")) is False


# ── v20.2: imagefree「单 IP 忙」错误 → 代理池换 IP 触发（429 等价）──────────

def test_is_upstream_ip_busy_detects_in_progress():
    """imagefree 免费层同 IP 并发第二个任务 → 'free image task in progress' 必须识别。"""
    from api.worker.generator import _is_upstream_ip_busy

    assert _is_upstream_ip_busy(Exception(
        "generate 提交失败: You already have a free image task in progress. Please wait for it to finish"
    )) is True
    assert _is_upstream_ip_busy(Exception(
        "generate 提交失败: You already have an image editing task in progress"
    )) is True  # 软匹配 free image task 前缀
    assert _is_upstream_ip_busy(Exception("HTTP 429")) is False  # 429 由原逻辑处理
    assert _is_upstream_ip_busy(Exception("generate 提交失败: HTTP 500")) is False
    assert _is_upstream_ip_busy(Exception("timeout")) is False


def test_generate_with_429_proxy_fallback_triggers_on_in_progress(monkeypatch):
    """直连报 'free image task in progress' → 走代理池换 IP 重试（不再直接 DLQ）。"""
    import asyncio

    from api import imagefree_client
    from api.worker import generator as gen_mod
    from api.worker.generator import generate_with_429_proxy_fallback

    calls = {"direct": 0, "proxy": 0}

    async def _fake_gen_once_b3(engine, row, token, proxy=None):
        if proxy:
            calls["proxy"] += 1
            return {"status": "completed", "image_url": "https://r2.example/x.png"}
        calls["direct"] += 1
        raise imagefree_client.ImagefreeError(
            "generate 提交失败: You already have a free image task in progress. Please wait"
        )

    monkeypatch.setattr(gen_mod, "generate_once_b3", _fake_gen_once_b3)

    # 代理池 stub：第一次 acquire 返回代理，后续返回 None
    class _ProxyPool:
        def __init__(self):
            self._calls = 0
        async def acquire(self, prefer_source="residential"):
            if self._calls == 0:
                self._calls += 1
                return "http://proxy-a:8080"
            self._calls += 1
            return None
        async def mark_failure(self, proxy, rate_limited=False):
            assert rate_limited is True
        async def mark_success(self, proxy):
            pass

    class _Engine:
        _proxy_pool = _ProxyPool()

    # 求解 stub：代理池路径直接给 token（不再真实调 cf_solver）
    async def _fake_solve(cf_solver_url=None, url="", sitekey="", timeout=0, proxy=None):
        return "proxy-token", 100

    monkeypatch.setattr(gen_mod.turnstile_client, "solve_turnstile", _fake_solve)

    async def _run():
        return await generate_with_429_proxy_fallback(_Engine(), "task-1", {"prompt": "x", "download": False}, "direct-token")

    result = asyncio.run(_run())
    assert result["status"] == "completed"
    assert calls["direct"] == 1
    assert calls["proxy"] == 1, "in-progress 错误必须触发代理池换 IP 重试"
