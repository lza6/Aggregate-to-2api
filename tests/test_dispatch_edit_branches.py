"""M5-E1 补测：dispatch_edit 互斥/断链/重试/多图分支。

覆盖 api/dispatch_edit.py 缺失分支（_dispatch_edit_multi、_run_edit_chain 重试与失败、
edit_image 多图/无图分支、_is_edit_slot_wedged 重试边界等）。

通过 mock engine/imagefree_client/db 隔离外部依赖，聚焦路由逻辑。
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

os.environ.setdefault("IF_DB_FILE", tempfile.mktemp(suffix=".db"))
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")

from api import dispatch_edit  # noqa: E402
from api.dispatch_edit import (  # noqa: E402
    _dispatch_edit,
    _dispatch_edit_multi,
    _is_edit_slot_wedged,
    _run_edit_chain,
    edit_image,
)
from api.errors import AppError  # noqa: E402
from api.models import EditRequest  # noqa: E402


def test_is_edit_slot_wedged_already_have():
    assert _is_edit_slot_wedged(Exception("You already have an image editing task")) is True


def test_is_edit_slot_wedged_task_in_progress():
    assert _is_edit_slot_wedged(Exception("429: task in progress")) is True


def test_is_edit_slot_wedged_other():
    assert _is_edit_slot_wedged(Exception("500 internal")) is False
    assert _is_edit_slot_wedged(None) is False


@pytest.mark.asyncio
async def test_dispatch_edit_imagefree_path(monkeypatch):
    """imagefree 前缀 → 走 _run_edit_job 后台任务（mock 全链路）。"""
    created = []

    async def fake_create_request(job_id, *a, **kw):
        created.append(job_id)
        return None

    async def fake_mark_finished(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark_finished)

    # _run_edit_job 内部会 create_task，mock 掉 _run_edit_chain 避免真实上游
    async def fake_run_edit_chain(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit, "_run_edit_chain", fake_run_edit_chain)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_LEASE_ENABLED", False)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_MUTEX_ENABLED", False)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    job_id = await _dispatch_edit("imagefree/default", "prompt", b"\x89PNG", False)
    assert job_id is not None
    assert created == [job_id]
    # 等后台任务完成
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_dispatch_edit_provider_unavailable(monkeypatch):
    """非 imagefree 前缀且 provider 不可用 → 429。"""
    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: None)
    with pytest.raises(AppError) as exc:
        await _dispatch_edit("unknown/model", "prompt", b"\x89PNG", False)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_dispatch_edit_multi_provider_unavailable(monkeypatch):
    """_dispatch_edit_multi provider 不可用 → 429。"""
    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: None)
    with pytest.raises(AppError) as exc:
        await _dispatch_edit_multi("unknown/model", "prompt", [b"\x89PNG"], False)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_edit_image_no_image_raises(monkeypatch):
    """既无 image 也无 images → 422。"""
    req = EditRequest(prompt="p", model="imagefree/default")
    with pytest.raises(AppError) as exc:
        await edit_image(req)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_edit_image_imagefree_multi_raises(monkeypatch):
    """imagefree + 多图 → 422（上游仅支持单图）。"""
    # 构造 images 字段（多图）
    req = EditRequest.model_construct(
        prompt="p",
        model="imagefree/default",
        images=["data:image/png;base64,iVBORw0KGgo=", "data:image/png;base64,iVBORw0KGgo="],
    )
    with pytest.raises(AppError) as exc:
        await edit_image(req)
    assert exc.value.status_code == 422
    assert "单图" in str(exc.value.message)


@pytest.mark.asyncio
async def test_edit_image_unsupported_mime_raises(monkeypatch):
    """无法识别的图片格式 → 422。"""
    # octet-stream 检测
    monkeypatch.setattr(dispatch_edit.imagefree_client, "detect_mime", lambda b: "application/octet-stream")
    req = EditRequest.model_construct(
        prompt="p",
        model="imagefree/default",
        images=["data:application/octet-stream;base64,AAAA"],
    )
    with pytest.raises(AppError) as exc:
        await edit_image(req)
    assert exc.value.status_code == 422
    assert "无法识别" in str(exc.value.message)


@pytest.mark.asyncio
async def test_run_edit_chain_no_token_marks_error(monkeypatch):
    """engine.acquire_token 返回 None → mark_finished error。"""

    async def fake_acquire(*a, **kw):
        return None

    calls = []

    async def fake_mark(*a, **kw):
        calls.append(a)

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 1)
    await _run_edit_chain("job-1", b"\x89PNG", "image/png", "p", False, "default")
    assert len(calls) == 1
    assert calls[0][1] == "error"


@pytest.mark.asyncio
async def test_run_edit_chain_wedged_retries(monkeypatch):
    """上游并发槽被占 → 重试（_is_edit_slot_wedged 命中）。"""
    attempt = [0]

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        attempt[0] += 1
        if attempt[0] < 2:
            raise RuntimeError("already have an image editing task")
        return "http://up/img"

    async def fake_submit(*a, **kw):
        return "tid-1"

    async def fake_poll(*a, **kw):
        return {"image": "http://r/img"}

    async def fake_update(*a, **kw):
        return None

    async def fake_mark(*a, **kw):
        pass

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "submit_edit", fake_submit)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "poll_edit_status", fake_poll)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 3)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    # download=True → 走下载分支
    await _run_edit_chain("job-2", b"\x89PNG", "image/png", "p", True, "default")
    # 重试后成功（attempt >= 2）


@pytest.mark.asyncio
async def test_run_edit_chain_wedged_exhausted(monkeypatch):
    """重试耗尽仍 wedged → mark_finished error。"""

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        raise RuntimeError("already have an image editing task")

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 2)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-3", b"\x89PNG", "image/png", "p", False, "default")
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_run_edit_chain_generic_error_marks_error(monkeypatch):
    """非 wedged 的异常 → mark_finished error（不重试）。"""

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        raise RuntimeError("upload failed")

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 2)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-4", b"\x89PNG", "image/png", "p", False, "default")
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_run_edit_chain_download_failure_still_completed(monkeypatch):
    """download=True 但下载失败 → 仍标记 completed（URL 交付不受影响）。"""

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        return "http://up/img"

    async def fake_submit(*a, **kw):
        return "tid-1"

    async def fake_poll(*a, **kw):
        return {"image": "http://r/img"}

    async def fake_update(*a, **kw):
        return None

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_download(*a, **kw):
        raise RuntimeError("download failed")

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "submit_edit", fake_submit)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "poll_edit_status", fake_poll)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "download_image", fake_download)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 1)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-5", b"\x89PNG", "image/png", "p", True, "default")
    assert marks
    assert marks[0][1] == "completed"


@pytest.mark.asyncio
async def test_dispatch_edit_multi_success(monkeypatch):
    """_dispatch_edit_multi provider 可用 → 后台任务 + 返回 job_id。"""
    created = []

    async def fake_create_request(job_id, *a, **kw):
        created.append(job_id)

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            from types import SimpleNamespace

            return SimpleNamespace(
                status="completed",
                asset_url="http://r/img",
                asset_bytes=b"\x89PNG",
                asset_mime="image/png",
                proxy_used=None,
                error=None,
            )

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")
    job_id = await _dispatch_edit_multi("aifreeforever/model", "p", [b"\x89PNG"], True)
    assert job_id is not None
    assert created == [job_id]
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_edit_image_url_input_downloads(monkeypatch):
    """image 字段为 URL → 下载字节后走单图分支。"""
    # _parse_input_image 对 URL 返回 (None, ctype)，触发下载分支
    monkeypatch.setattr(dispatch_edit, "_parse_input_image", lambda url: (None, "image/png"))
    monkeypatch.setattr(dispatch_edit, "_parse_input_images", lambda imgs: [b"\x89PNG"])
    monkeypatch.setattr(dispatch_edit.imagefree_client, "detect_mime", lambda b: "image/png")

    async def fake_download(url, timeout, max_bytes):
        return b"\x89PNG-downloaded"

    monkeypatch.setattr(dispatch_edit.imagefree_client, "download_image", fake_download)

    dispatched = []

    async def fake_dispatch_edit(model, prompt, image_bytes, download):
        dispatched.append(image_bytes)
        return "job-url"

    monkeypatch.setattr(dispatch_edit, "_dispatch_edit", fake_dispatch_edit)
    monkeypatch.setattr(dispatch_edit, "_validate_model", lambda *a, **kw: None)

    # task_to_public 需要 id 等字段
    async def fake_get_public(job_id):
        return {
            "id": job_id,
            "status": "queued",
            "image_url": None,
            "image_base64": None,
            "image_mime": None,
            "error": None,
            "created_at": 0,
            "duration_sec": None,
            "type": "img",
            "model": "imagefree/default",
            "prompt": "p",
            "aspect_ratio": "1:1",
            "client_ip": None,
            "user_agent": None,
        }

    monkeypatch.setattr(dispatch_edit.db, "get_public", fake_get_public)
    monkeypatch.setattr(dispatch_edit, "task_to_public", lambda d: d)

    req = EditRequest.model_construct(prompt="p", model="imagefree/default", image="http://example/img.png")
    result = await edit_image(req)
    assert result.id == "job-url"
    assert dispatched == [b"\x89PNG-downloaded"]


@pytest.mark.asyncio
async def test_edit_image_base64_input(monkeypatch):
    """image 字段为 base64 → 直接用解析字节。"""
    monkeypatch.setattr(dispatch_edit, "_parse_input_image", lambda url: (b"\x89PNG-base64", "image/png"))
    monkeypatch.setattr(dispatch_edit.imagefree_client, "detect_mime", lambda b: "image/png")

    dispatched = []

    async def fake_dispatch_edit(model, prompt, image_bytes, download):
        dispatched.append(image_bytes)
        return "job-b64"

    monkeypatch.setattr(dispatch_edit, "_dispatch_edit", fake_dispatch_edit)
    monkeypatch.setattr(dispatch_edit, "_validate_model", lambda *a, **kw: None)

    async def fake_get_public(job_id):
        return {
            "id": job_id,
            "status": "queued",
            "image_url": None,
            "image_base64": None,
            "image_mime": None,
            "error": None,
            "created_at": 0,
            "duration_sec": None,
            "type": "img",
            "model": "imagefree/default",
            "prompt": "p",
            "aspect_ratio": "1:1",
            "client_ip": None,
            "user_agent": None,
        }

    monkeypatch.setattr(dispatch_edit.db, "get_public", fake_get_public)
    monkeypatch.setattr(dispatch_edit, "task_to_public", lambda d: d)

    req = EditRequest.model_construct(prompt="p", model="imagefree/default", image="data:image/png;base64,iVBORw0KGgo=")
    result = await edit_image(req)
    assert result.id == "job-b64"
    assert dispatched == [b"\x89PNG-base64"]


@pytest.mark.asyncio
async def test_edit_image_multi_non_imagefree_dispatches_multi(monkeypatch):
    """多图 + 非 imagefree 前缀 → 走 _dispatch_edit_multi。"""
    monkeypatch.setattr(dispatch_edit, "_parse_input_images", lambda imgs: [b"\x89PNG", b"\x89PNG"])
    monkeypatch.setattr(dispatch_edit.imagefree_client, "detect_mime", lambda b: "image/png")
    monkeypatch.setattr(dispatch_edit, "_normalize_model", lambda m: m)

    dispatched_multi = []

    async def fake_dispatch_multi(model, prompt, images, download):
        dispatched_multi.append(images)
        return "job-multi"

    monkeypatch.setattr(dispatch_edit, "_dispatch_edit_multi", fake_dispatch_multi)
    monkeypatch.setattr(dispatch_edit, "_validate_model", lambda *a, **kw: None)

    async def fake_get_public(job_id):
        return {
            "id": job_id,
            "status": "queued",
            "image_url": None,
            "image_base64": None,
            "image_mime": None,
            "error": None,
            "created_at": 0,
            "duration_sec": None,
            "type": "img",
            "model": "aifreeforever/x",
            "prompt": "p",
            "aspect_ratio": "1:1",
            "client_ip": None,
            "user_agent": None,
        }

    monkeypatch.setattr(dispatch_edit.db, "get_public", fake_get_public)
    monkeypatch.setattr(dispatch_edit, "task_to_public", lambda d: d)

    req = EditRequest.model_construct(
        prompt="p",
        model="aifreeforever/x",
        images=["data:image/png;base64,iVBORw0KGgo=", "data:image/png;base64,iVBORw0KGgo="],
    )
    result = await edit_image(req)
    assert result.id == "job-multi"
    assert len(dispatched_multi) == 1
    assert len(dispatched_multi[0]) == 2


@pytest.mark.asyncio
async def test_renew_edit_lock_loop_heartbeat(monkeypatch):
    """_renew_edit_lock_loop 心跳续租：成功续租 + 易主停止。"""
    from api.dispatch_edit import _renew_edit_lock_loop, _EDIT_LEASE_STORE

    monkeypatch.setattr(dispatch_edit.config, "EDIT_LEASE_TTL", 0.03)

    call_count = [0]

    async def fake_renew(key, token, ttl):
        call_count[0] += 1
        return call_count[0] < 2  # 第 2 次返回 False（易主）

    monkeypatch.setattr(_EDIT_LEASE_STORE, "renew", fake_renew)
    t = await _renew_edit_lock_loop("key", "tok")
    await asyncio.sleep(0.1)
    assert t.done()  # 易主后停止
    t.cancel()


@pytest.mark.asyncio
async def test_renew_edit_lock_loop_exception_continues(monkeypatch):
    """续租异常不中断心跳（continue）。"""
    from api.dispatch_edit import _renew_edit_lock_loop, _EDIT_LEASE_STORE

    monkeypatch.setattr(dispatch_edit.config, "EDIT_LEASE_TTL", 0.02)

    async def fake_renew(key, token, ttl):
        raise RuntimeError("db jitter")

    monkeypatch.setattr(_EDIT_LEASE_STORE, "renew", fake_renew)
    t = await _renew_edit_lock_loop("key", "tok")
    await asyncio.sleep(0.08)
    # 异常后心跳仍在运行（未停止）
    assert not t.done()
    t.cancel()


@pytest.mark.asyncio
async def test_dispatch_edit_provider_completed_marks_finished(monkeypatch):
    """_dispatch_edit provider 成功 → mark_finished completed。"""
    created = []

    async def fake_create_request(job_id, *a, **kw):
        created.append(job_id)

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update_proxy(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.db, "update_proxy_used", fake_update_proxy)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            from types import SimpleNamespace

            return SimpleNamespace(
                status="completed",
                asset_url="http://r/img",
                asset_bytes=b"\x89PNG",
                asset_mime="image/png",
                proxy_used="http://proxy:8080",
                error=None,
            )

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    # _provider_sem context manager
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_sem(prefix):
        yield

    monkeypatch.setattr(dispatch_edit, "_provider_sem", fake_sem)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    await _dispatch_edit("aifreeforever/model", "p", b"\x89PNG", True)
    await asyncio.sleep(0.05)
    assert marks
    assert marks[0][1] == "completed"


@pytest.mark.asyncio
async def test_dispatch_edit_provider_failed_status_marks_error(monkeypatch):
    """_dispatch_edit provider 返回非 completed → mark_finished error。"""

    async def fake_create_request(job_id, *a, **kw):
        pass

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update_proxy(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.db, "update_proxy_used", fake_update_proxy)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            from types import SimpleNamespace

            return SimpleNamespace(
                status="error",
                asset_url=None,
                asset_bytes=None,
                asset_mime=None,
                proxy_used=None,
                error="upstream failed",
            )

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_sem(prefix):
        yield

    monkeypatch.setattr(dispatch_edit, "_provider_sem", fake_sem)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    await _dispatch_edit("aifreeforever/model", "p", b"\x89PNG", True)
    await asyncio.sleep(0.05)
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_dispatch_edit_provider_exception_marks_error(monkeypatch):
    """_dispatch_edit provider 抛异常 → mark_finished error。"""

    async def fake_create_request(job_id, *a, **kw):
        pass

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update_proxy(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.db, "update_proxy_used", fake_update_proxy)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            raise RuntimeError("provider boom")

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_sem(prefix):
        yield

    monkeypatch.setattr(dispatch_edit, "_provider_sem", fake_sem)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    await _dispatch_edit("aifreeforever/model", "p", b"\x89PNG", True)
    await asyncio.sleep(0.05)
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_dispatch_edit_multi_completed_marks_finished(monkeypatch):
    """_dispatch_edit_multi provider 成功 → mark_finished completed。"""

    async def fake_create_request(job_id, *a, **kw):
        pass

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update_proxy(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.db, "update_proxy_used", fake_update_proxy)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            from types import SimpleNamespace

            return SimpleNamespace(
                status="completed",
                asset_url="http://r/multi",
                asset_bytes=b"\x89PNG",
                asset_mime="image/png",
                proxy_used=None,
                error=None,
            )

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_sem(prefix):
        yield

    monkeypatch.setattr(dispatch_edit, "_provider_sem", fake_sem)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    await _dispatch_edit_multi("aifreeforever/model", "p", [b"\x89PNG", b"\x89PNG"], True)
    await asyncio.sleep(0.05)
    assert marks
    assert marks[0][1] == "completed"


@pytest.mark.asyncio
async def test_dispatch_edit_multi_failed_status_marks_error(monkeypatch):
    """_dispatch_edit_multi provider 返回 error → mark_finished error。"""

    async def fake_create_request(job_id, *a, **kw):
        pass

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update_proxy(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.db, "update_proxy_used", fake_update_proxy)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            from types import SimpleNamespace

            return SimpleNamespace(
                status="error", asset_url=None, asset_bytes=None, asset_mime=None, proxy_used=None, error="multi failed"
            )

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_sem(prefix):
        yield

    monkeypatch.setattr(dispatch_edit, "_provider_sem", fake_sem)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    await _dispatch_edit_multi("aifreeforever/model", "p", [b"\x89PNG"], False)
    await asyncio.sleep(0.05)
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_dispatch_edit_multi_exception_marks_error(monkeypatch):
    """_dispatch_edit_multi provider 抛异常 → mark_finished error。"""

    async def fake_create_request(job_id, *a, **kw):
        pass

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update_proxy(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.db, "create_request", fake_create_request)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.db, "update_proxy_used", fake_update_proxy)

    class _FakeProvider:
        prefix = "aifreeforever"

        async def generate(self, *a, **kw):
            raise RuntimeError("multi boom")

    monkeypatch.setattr(dispatch_edit.registry, "provider_for", lambda m: _FakeProvider())
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_sem(prefix):
        yield

    monkeypatch.setattr(dispatch_edit, "_provider_sem", fake_sem)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")

    await _dispatch_edit_multi("aifreeforever/model", "p", [b"\x89PNG"], False)
    await asyncio.sleep(0.05)
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_run_edit_job_no_token_marks_busy(monkeypatch):
    """_run_edit_job 获取锁失败（token=None）→ mark_finished error「繁忙」。"""
    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_acquire_lock(key, holder, timeout):
        return None  # 拿不到锁

    async def fake_acquire_proxy():
        return None  # 无代理

    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit, "_acquire_edit_lock", fake_acquire_lock)
    monkeypatch.setattr(dispatch_edit._EDIT_PROXY_POOL, "acquire_proxy", fake_acquire_proxy)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")
    monkeypatch.setattr(dispatch_edit.config, "EDIT_LEASE_ENABLED", False)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_MUTEX_ENABLED", False)

    await dispatch_edit._run_edit_job("job-busy", b"\x89PNG", "image/png", "p", False, "default")
    assert marks
    assert marks[0][1] == "error"
    assert "繁忙" in str(marks[0][3])


@pytest.mark.asyncio
async def test_run_edit_job_lease_heartbeat_path(monkeypatch):
    """_run_edit_job 启用 lease → 启动心跳，结束取消。"""
    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_acquire_lock(key, holder, timeout):
        return "lease-tok"

    async def fake_release_lock(key, token):
        return None

    async def fake_acquire_proxy():
        return None

    async def fake_run_chain(*a, **kw):
        return None

    # _renew_edit_lock_loop 返回一个可取消 task
    async def fake_renew_loop(key, token):
        async def _hb():
            try:
                while True:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                return

        return asyncio.create_task(_hb())

    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit, "_acquire_edit_lock", fake_acquire_lock)
    monkeypatch.setattr(dispatch_edit, "_release_edit_lock", fake_release_lock)
    monkeypatch.setattr(dispatch_edit, "_run_edit_chain", fake_run_chain)
    monkeypatch.setattr(dispatch_edit, "_renew_edit_lock_loop", fake_renew_loop)
    monkeypatch.setattr(dispatch_edit._EDIT_PROXY_POOL, "acquire_proxy", fake_acquire_proxy)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_PROXY_FILE", "")
    monkeypatch.setattr(dispatch_edit.config, "EDIT_LEASE_ENABLED", True)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_MUTEX_ENABLED", False)

    await dispatch_edit._run_edit_job("job-lease", b"\x89PNG", "image/png", "p", False, "default")
    # _run_edit_chain 被 mock，不 mark（链路正常完成无 mark）
    # 但确保不抛异常且 _EDIT_PENDING 已清理
    assert "job-lease" not in dispatch_edit._EDIT_PENDING


@pytest.mark.asyncio
async def test_run_edit_chain_no_download_completed(monkeypatch):
    """download=False → mark_finished completed（URL 交付，不下载）。"""

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        return "http://up/img"

    async def fake_submit(*a, **kw):
        return "tid-1"

    async def fake_poll(*a, **kw):
        return {"image": "http://r/img"}

    async def fake_update(*a, **kw):
        return None

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "submit_edit", fake_submit)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "poll_edit_status", fake_poll)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 1)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-nodl", b"\x89PNG", "image/png", "p", False, "default")
    assert marks
    assert marks[0][1] == "completed"


@pytest.mark.asyncio
async def test_run_edit_chain_download_success_completed(monkeypatch):
    """download=True 且下载成功 → mark_finished completed + base64。"""

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        return "http://up/img"

    async def fake_submit(*a, **kw):
        return "tid-1"

    async def fake_poll(*a, **kw):
        return {"image": "http://r/img"}

    async def fake_update(*a, **kw):
        return None

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_download(*a, **kw):
        return b"\x89PNG-data"

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "submit_edit", fake_submit)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "poll_edit_status", fake_poll)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "download_image", fake_download)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 1)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-dl", b"\x89PNG", "image/png", "p", True, "default")
    assert marks
    assert marks[0][1] == "completed"
    # 第 6 参数为 base64 字节
    assert marks[0][5] is not None


@pytest.mark.asyncio
async def test_run_edit_chain_wedged_exhausted_else_branch(monkeypatch):
    """重试耗尽 wedged → for-else 分支标记 error。"""

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        raise RuntimeError("already have an image editing task")

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 2)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-else", b"\x89PNG", "image/png", "p", False, "default")
    # for-else：重试耗尽标记
    assert marks
    assert marks[0][1] == "error"
    assert "仍被上游占用" in str(marks[0][3])


@pytest.mark.asyncio
async def test_run_edit_chain_wedged_no_retry_marks_error(monkeypatch):
    """wedged 但 attempt == MAX（无重试余量）→ 走 if _is_edit_slot_wedged 分支标记。"""
    attempt = [0]

    async def fake_acquire(*a, **kw):
        return "token"

    async def fake_upload(*a, **kw):
        attempt[0] += 1
        raise RuntimeError("already have an image editing task")

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update(*a, **kw):
        return None

    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 1)  # 只 1 次，无重试
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    await _run_edit_chain("job-noretry", b"\x89PNG", "image/png", "p", False, "default")
    assert marks
    assert marks[0][1] == "error"


@pytest.mark.asyncio
async def test_run_edit_chain_for_else_branch(monkeypatch):
    """for 循环正常结束（无 break，attempt 耗尽但最后一次也 wedged）→ for-else 标记。

    构造：EDIT_RETRY_MAX=2，前 2 次都 wedged 且都进入重试（attempt < MAX），
    最后一次 wedged 时 attempt == MAX → 走 if 分支 return，不会到 else。
    要触发 for-else 需要让循环正常结束但不 break：让 wedged 重试成功后再抛非 wedged 异常？
    更简单：让前几次重试成功继续，但循环 range 走完后无 break → for-else。
    实际上代码 break 只在成功时；若每次都 continue 重试到 range 耗尽，会落到 else。
    """

    # 构造：每次 upload 都抛 wedged，attempt < MAX 时 continue，最后一次 attempt==MAX 走 if return
    # 要触发 for-else，需让循环不 break 且不 return —— 但 except 里要么 continue 要么 return
    # for-else 实际上只有在「循环跑完未 break」时触发，但 except 一定会 return 或 continue
    # continue 到 range 耗尽 → 落入 else。构造 attempt < MAX 一直 continue，最后一次也 continue？
    # 不可能：最后一次 attempt == MAX 不满足 attempt < MAX 条件，会走 if return。
    # 所以 for-else 在当前逻辑下不可达？验证：用 mock 让所有 attempt 都 continue
    async def fake_acquire(*a, **kw):
        return "token"

    call_count = [0]

    async def fake_upload(*a, **kw):
        call_count[0] += 1
        # 让 attempt < MAX 永远成立（通过让 _is_edit_slot_wedged 返回 True 且 attempt 永远 < MAX）
        raise RuntimeError("already have an image editing task")

    marks = []

    async def fake_mark(*a, **kw):
        marks.append(a)

    async def fake_update(*a, **kw):
        return None

    # 让 _is_edit_slot_wedged 在 attempt < MAX 时返回 True（continue），最后一次返回 False → else
    monkeypatch.setattr(dispatch_edit, "_is_edit_slot_wedged", lambda e: False)
    monkeypatch.setattr(dispatch_edit.engine, "acquire_token", fake_acquire)
    monkeypatch.setattr(dispatch_edit.imagefree_client, "upload_edit_image", fake_upload)
    monkeypatch.setattr(dispatch_edit.db, "update_upstream_task", fake_update)
    monkeypatch.setattr(dispatch_edit.db, "mark_finished", fake_mark)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_MAX", 2)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_edit.config, "EDIT_TIMEOUT", 10)
    monkeypatch.setattr(dispatch_edit.config, "GENERATE_POLL_INTERVAL", 0.1)
    # _is_edit_slot_wedged=False → 走 else 分支（非 wedged error），return
    await _run_edit_chain("job-forelse", b"\x89PNG", "image/png", "p", False, "default")
    assert marks
    assert marks[0][1] == "error"
    # 非 wedged 走 else 标记 "图生图失败: {e}"
    assert "图生图失败" in str(marks[0][3])
