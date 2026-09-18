"""视频 Mock 任务测试（v18 P1-1）。覆盖：提交/轮询推进/完成 URL/开关/不存在。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.providers.video_mock import MockVideoProvider  # noqa: E402


@pytest.fixture()
def provider():
    return MockVideoProvider()


def test_submit_returns_task(provider):
    tid = provider.submit(prompt="城市夜景", mode="txt2vid", duration_seconds=5.0, ratio="16:9")
    assert tid
    job = provider.poll(tid)
    assert job["status"] in ("queued", "rendering")
    assert 0 <= job["progress"] <= 100


def test_poll_completes_after_render(provider):
    tid = provider.submit(prompt="夜景", duration_seconds=0.01)  # 极短渲染
    time.sleep(0.05)
    job = provider.poll(tid)
    assert job["status"] == "completed"
    assert job["progress"] == 100.0
    assert job["url"] and job["url"].endswith(".mp4")


def test_poll_rendering_progress_increases(provider):
    tid = provider.submit(prompt="延时摄影", duration_seconds=2.0)
    p1 = provider.poll(tid)["progress"]
    time.sleep(0.3)
    p2 = provider.poll(tid)["progress"]
    assert p2 >= p1


def test_poll_unknown_task_none(provider):
    assert provider.poll("no-such") is None


def test_provider_importable_via_factory():
    from api.providers.video_provider import get_video_provider

    p = get_video_provider()
    tid = p.submit(prompt="demo")
    assert tid

def test_sse_progress_frame_publish_replay():
    """视频 SSE 帧事件：TaskEventHub 发布 progress 帧后可按任务回放（Last-Event-ID 补偿语义）。"""
    import asyncio

    from api.sse_events import hub as _hub

    async def _run():
        tid = "vid-sse-test"
        await _hub.publish(tid, "progress", {"task_id": tid, "progress": 42.0, "status": "rendering"})
        await _hub.publish(tid, "result", {"task_id": tid, "url": "https://x.mp4", "progress": 100.0})
        events = await _hub.replay_after(tid, None)
        return events

    events = asyncio.run(_run())
    types = [e.event for e in events]
    assert "progress" in types and "result" in types
    data = next(e.data for e in events if e.event == "result")
    assert data["progress"] == 100.0
    # 清理
    asyncio.run(_hub.clear_task("vid-sse-test"))
