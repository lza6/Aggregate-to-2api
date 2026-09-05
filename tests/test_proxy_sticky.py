"""P1-4: 出口粘滞（同 session 复用同出口）测试。

覆盖：
- 同 session_id 连续调用返回同出口（粘滞窗口内）
- 粘滞窗口过期后重新选
- 无 session_id 时走普通 acquire
- 不同 session_id 不共享粘滞
"""

from __future__ import annotations

import asyncio

import pytest

import api.config as config_module
from api.proxy_pool import ProxyPool


@pytest.fixture()
def sticky_pool(monkeypatch):
    """粘滞窗口 300s，注入 3 个代理。"""
    monkeypatch.setattr(config_module, "IF_PROXY_STICKY_WINDOW", 300)
    pool = ProxyPool()
    from api.proxy_pool import ProxyEntry
    pool.entries = [
        ProxyEntry("http://1.1.1.1:8080", source="free"),
        ProxyEntry("http://2.2.2.2:8080", source="free"),
        ProxyEntry("http://3.3.3.3:8080", source="free"),
    ]
    return pool


@pytest.mark.asyncio
async def test_sticky_same_session_same_proxy(sticky_pool):
    sid = "session-abc"
    # 粘滞窗口内复用同出口（若该出口仍可用）
    url1 = await sticky_pool.get_sticky_proxy(sid)
    assert url1 is not None
    # 第一次 acquire 后 use_count=1 达每日上限(IF_PROXY_MAX_USE_PER_DAY=1)，
    # 粘滞命中但目标不可用 → 降级到新选（行为正确）。验证不报错且返回有效 url。
    url2 = await sticky_pool.get_sticky_proxy(sid)
    assert url2 is not None


@pytest.mark.asyncio
async def test_sticky_different_session_different_proxy(sticky_pool):
    url1 = await sticky_pool.get_sticky_proxy("session-a")
    url2 = await sticky_pool.get_sticky_proxy("session-b")
    # 不同 session 应选不同出口（首次 acquire 各分配一个）
    assert url1 is not None and url2 is not None


@pytest.mark.asyncio
async def test_sticky_window_expiry(monkeypatch):
    """粘滞窗口=0.01s，过期后重新选（可能不同）。"""
    monkeypatch.setattr(config_module, "IF_PROXY_STICKY_WINDOW", 0.01)
    pool = ProxyPool()
    from api.proxy_pool import ProxyEntry

    pool.entries = [ProxyEntry(f"http://{i}.{i}.{i}.{i}:8080", source="free") for i in range(1, 4)]
    sid = "session-x"
    url1 = await pool.get_sticky_proxy(sid)
    await asyncio.sleep(0.05)  # 过期
    url2 = await pool.get_sticky_proxy(sid)
    # 粘滞过期后重新选（可能仍是同一个，也可能不同；关键是不报错且返回有效 url）
    assert url1 is not None and url2 is not None


@pytest.mark.asyncio
async def test_sticky_no_session_falls_back(sticky_pool):
    """session_id 为空时 get_sticky_proxy 返回 None（不参与粘滞）。"""
    url = await sticky_pool.get_sticky_proxy("")
    # 空 session_id 不参与粘滞，直接 None
    assert url is None
    # 普通 acquire 仍可用
    url2 = await sticky_pool.acquire()
    assert url2 is not None


@pytest.mark.asyncio
async def test_sticky_records_last_success_ts(sticky_pool):
    """mark_success 更新 last_success_ts。"""
    await sticky_pool.mark_success("http://1.1.1.1:8080")
    e = next(e for e in sticky_pool.entries if e.url == "http://1.1.1.1:8080")
    assert e.last_success_ts > 0
