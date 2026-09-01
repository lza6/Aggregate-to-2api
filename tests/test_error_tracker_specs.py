"""api/error_tracker.py + api/system_spec.py 单元测试（P0-2 覆盖率补强）。

覆盖：
- error_tracker：后端 P0-P1 聚合计数（空码兜底/降序快照/单码计数/重置）+
  前端遥测（截断/隔离/ring buffer 上限/空快照）。
- system_spec：规格检测容错（cpu/memory/disk fallback）+ system_spec() 结构 +
  模块级自适应常量。
"""

from __future__ import annotations

import pytest

import api.error_tracker as et
import api.system_spec as ss


# ── error_tracker：后端聚合 ─────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_tracker():
    et.reset()
    # 前端遥测也要清（模块无 reset_frontend，手动清内部状态）
    with et._frontend_lock:
        et._frontend_counts.clear()
        et._frontend_recent.clear()
    yield
    et.reset()
    with et._frontend_lock:
        et._frontend_counts.clear()
        et._frontend_recent.clear()


def test_record_empty_code_falls_back_to_sys():
    et.record("")
    assert et.count_of("SYS.001") == 1


def test_record_and_snapshot_desc_order():
    for _ in range(3):
        et.record("AUTH.001")
    et.record("RATE.001")
    snap = et.snapshot()
    assert snap["AUTH.001"] == 3
    assert snap["RATE.001"] == 1
    # 降序：次数多的在前
    codes = list(snap)
    assert codes.index("AUTH.001") < codes.index("RATE.001")


def test_count_of_missing_code_is_zero():
    assert et.count_of("NOPE.999") == 0


def test_watched_codes_returns_copy():
    codes = et.watched_codes()
    assert "AUTH.001" in codes
    codes.append("X")
    assert "X" not in et.watched_codes()


# ── error_tracker：前端遥测（与后端隔离）──────────────────────


def test_frontend_error_isolated_from_backend_counts():
    et.record_frontend_error(code="FE.ERR", message="boom")
    assert et.count_of("FE.ERR") == 0  # 后端计数不受污染
    snap = et.frontend_snapshot()
    assert snap["total"] == 1
    assert snap["counts"]["FE.ERR"] == 1


def test_frontend_error_empty_code_defaults_and_truncates():
    et.record_frontend_error(code="", message="m" * 900, stack="s" * 5000, url="u" * 900, ua="a" * 500)
    entry = et.frontend_snapshot()["recent"][0]
    assert entry["code"] == "FE.UNKNOWN"
    assert len(entry["message"]) == 500
    assert len(entry["stack"]) == 2000
    assert len(entry["url"]) == 500
    assert len(entry["ua"]) == 300
    assert "ts" in entry


def test_frontend_ring_buffer_capped():
    for i in range(60):
        et.record_frontend_error(code=f"FE.{i}", message="x")
    snap = et.frontend_snapshot()
    assert snap["total"] == 60  # 计数不丢
    assert len(snap["recent"]) == 50  # 明细 ring buffer 封顶


def test_frontend_snapshot_empty():
    snap = et.frontend_snapshot()
    assert snap == {"counts": {}, "recent": [], "total": 0}


# ── system_spec：检测容错 + 结构 ─────────────────────────────


def test_detect_cpu_count_returns_positive():
    assert ss._detect_cpu_count() >= 1


def test_detect_memory_mb_positive():
    assert ss._detect_memory_mb() > 0


def test_detect_disk_gb_fallback_zero_when_statvfs_missing(monkeypatch):
    """psutil 缺失 + os.statvfs 缺失（Windows）→ (0,0,0) 兜底。"""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # os.statvfs 在 Windows 不存在；如存在则删除以触发 AttributeError 分支
    monkeypatch.delattr(ss.os, "statvfs", raising=False)
    total, used, free = ss._detect_disk_gb(".")
    assert (total, used, free) == (0, 0, 0)


def test_detect_cpu_count_fallback_on_error(monkeypatch):
    """multiprocessing.cpu_count 抛 NotImplementedError → 容错返回 2。"""
    import multiprocessing

    monkeypatch.setattr(multiprocessing, "cpu_count", lambda: (_ for _ in ()).throw(NotImplementedError))
    assert ss._detect_cpu_count() == 2


def test_system_spec_structure():
    spec = ss.system_spec()
    assert set(spec) == {"cpu", "memory", "disk", "adaptive"}
    assert spec["cpu"]["cores"] == ss.CPU_COUNT
    assert spec["memory"]["total_mb"] == ss.MEMORY_MB
    assert set(spec["adaptive"]) == {"workers", "upstream_inflight", "token_pool_size", "max_queue"}
    # 自适应常量下限约束
    assert ss.ADAPTIVE_WORKERS >= 2
    assert ss.ADAPTIVE_UPSTREAM_INFLIGHT >= 4
    assert ss.ADAPTIVE_TOKEN_POOL_SIZE >= 2
    assert ss.ADAPTIVE_MAX_QUEUE >= 500


def test_adaptive_constants_constrained_by_memory():
    """当前进程内存档位与常量一致性（任一分档的 min/max 均已应用）。"""
    if ss.MEMORY_MB < 2048:
        assert ss.ADAPTIVE_WORKERS <= 4
        assert ss.ADAPTIVE_TOKEN_POOL_SIZE <= 3
    elif ss.MEMORY_MB < 4096:
        assert ss.ADAPTIVE_WORKERS <= 8
    elif ss.MEMORY_MB >= 8192:
        assert ss.ADAPTIVE_WORKERS >= 16


# ── system_spec：import 期分档分支（importlib.reload + fake psutil）──


def _reload_with_memory(monkeypatch, total_mb: int):
    """注入 fake psutil 后重载 system_spec，使模块级分档分支按指定内存执行。"""
    import importlib
    import types

    fake_psutil = types.ModuleType("psutil")
    fake_psutil.virtual_memory = lambda: types.SimpleNamespace(total=total_mb * 1024 * 1024)
    fake_psutil.disk_usage = lambda p: types.SimpleNamespace(total=100e9, used=40e9, free=60e9)
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)
    return importlib.reload(ss)


def test_reload_low_memory_tier(monkeypatch):
    mod = _reload_with_memory(monkeypatch, 1024)
    assert mod.MEMORY_MB == 1024
    assert mod.ADAPTIVE_WORKERS <= 4
    assert mod.ADAPTIVE_UPSTREAM_INFLIGHT <= 12
    assert mod.ADAPTIVE_TOKEN_POOL_SIZE <= 3
    assert mod.ADAPTIVE_MAX_QUEUE <= 1000


def test_reload_mid_memory_tier(monkeypatch):
    mod = _reload_with_memory(monkeypatch, 3072)
    assert mod.MEMORY_MB == 3072
    assert mod.ADAPTIVE_WORKERS <= 8
    assert mod.ADAPTIVE_UPSTREAM_INFLIGHT <= 24
    assert mod.ADAPTIVE_MAX_QUEUE <= 2000


def test_reload_high_memory_tier(monkeypatch):
    mod = _reload_with_memory(monkeypatch, 16384)
    assert mod.MEMORY_MB == 16384
    assert mod.ADAPTIVE_WORKERS >= 16
    assert mod.ADAPTIVE_UPSTREAM_INFLIGHT >= 64
    assert mod.ADAPTIVE_TOKEN_POOL_SIZE >= 8
    assert mod.ADAPTIVE_MAX_QUEUE >= 5000


def test_reload_memory_fallback_proc_meminfo(monkeypatch):
    """psutil 缺失 + /proc/meminfo 不存在（Windows）→ 2048 兜底。"""
    import importlib
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        builtins,
        "open",
        lambda f, *a, **kw: (_ for _ in ()).throw(OSError("no /proc on win")),
    )
    mod = importlib.reload(ss)
    assert mod.MEMORY_MB == 2048


@pytest.fixture(autouse=True, scope="module")
def _restore_system_spec():
    """本模块结束后恢复原始 system_spec 模块状态（防 reload 污染其他测试）。"""
    yield
    import importlib

    importlib.reload(ss)
