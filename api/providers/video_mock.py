"""视频 Mock provider（指南 v18 P1-1，zack-d _submit_and_poll 语义的 Mock 版）。

提交→轮询→完成 全 Mock（IF_MOCK_UPSTREAM=1 语义）：渲染进度按时间推进（约 5s 完成），
最终产出占位 mp4 URL（零真实付费）。真实视频 provider 动作族后置。
"""
from __future__ import annotations

import time
import uuid
from typing import Any

_MOCK_RENDER_SECONDS = 5.0
_MOCK_URL = "https://mock.tingfeng.ai/v1/video/{task_id}.mp4"


class MockVideoProvider:
    """内存 Mock 视频任务：submit → task_id；poll → 状态/进度/URL。"""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, *, prompt: str, mode: str = "txt2vid", duration_seconds: float = 5.0, ratio: str = "16:9") -> str:
        task_id = uuid.uuid4().hex
        self._jobs[task_id] = {
            "task_id": task_id,
            "prompt": prompt,
            "mode": mode,
            "ratio": ratio,
            "duration_seconds": duration_seconds,
            "status": "queued",
            "progress": 0,
            "created_at": time.time(),
            "url": None,
        }
        return task_id

    def poll(self, task_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(task_id)
        if job is None:
            return None
        now = time.time()
        if job["status"] == "completed":
            return dict(job)
        elapsed = now - job["created_at"]
        render_seconds = max(0.01, float(job.get("duration_seconds") or _MOCK_RENDER_SECONDS))
        progress = min(100.0, round(elapsed / render_seconds * 100.0, 1))
        job["progress"] = progress
        if progress >= 100:
            job["status"] = "completed"
            job["progress"] = 100.0
            job["url"] = _MOCK_URL.format(task_id=task_id)
        elif progress > 0:
            job["status"] = "rendering"
        return dict(job)


mock_video_provider = MockVideoProvider()
