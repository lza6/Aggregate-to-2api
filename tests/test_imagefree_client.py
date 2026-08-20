"""imagefree_client（imagefree HTTP 客户端）单元测试。

覆盖：to_base64 / detect_mime 纯函数（含 5 种魔数 + 未知回退）、submit_generate /
poll_generate_status 的错误处理与终态分支、SSRF 防护（拒绝私网/回环下载）、
download_image 大小上限、图生图 upload/submit/poll 的错误分支。
所有上游交互用 fake httpx client monkeypatch（不碰真实网络）。
"""
import asyncio
import base64
import json
import os

import httpx
import pytest

os.environ.setdefault("IF_MOCK_UPSTREAM", "0")

from api.imagefree_client import (  # noqa: E402
    ImagefreeError,
    MOCK_UPSTREAM,
    close_client,
    detect_mime,
    download_image,
    poll_edit_status,
    poll_generate_status,
    submit_edit,
    submit_generate,
    to_base64,
    upload_edit_image,
)


@pytest.fixture(autouse=True)
def _force_no_mock(monkeypatch):
    """模块级 MOCK_UPSTREAM 在本次会话其他测试设置 IF_MOCK_REGISTER 后可能受影响，
    显式强制为 False，确保真实逻辑路径被测试。"""
    monkeypatch.setattr("api.imagefree_client.MOCK_UPSTREAM", False)
    yield
    assert True


# ── 纯函数 ─────────────────────────────────────────
class TestPure:
    def test_to_base64_roundtrip(self):
        data = b"\x89PNG"
        uri = to_base64(data, "image/png")
        assert uri.startswith("data:image/png;base64,")
        assert base64.b64decode(uri.split(",", 1)[1]) == data

    def test_detect_mime_all_formats(self):
        cases = [
            (b"\xff\xd8\xff\xe0...", "image/jpeg"),
            (b"\x89PNG\r\n\x1a\n....", "image/png"),
            (b"RIFF....WEBP", "image/webp"),
            (b"\x00\x00\x00\x18ftypavif", "image/avif"),
            (b"GIF87a....", "image/gif"),
            (b"GIF89a....", "image/gif"),
            (b"nothing-magic", "application/octet-stream"),
        ]
        for data, expected in cases:
            assert detect_mime(data) == expected


# ── 提交生成（错误处理/TaskId 校验）────────────────
class TestSubmitGenerate:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._ok_200)
        tid = await submit_generate("http://host", "cat", "1:1", "tok")
        assert tid == "task-1"

    @pytest.mark.asyncio
    async def test_http_500_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._err_500)
        with pytest.raises(ImagefreeError):
            await submit_generate("http://host", "cat", "1:1", "tok")

    @pytest.mark.asyncio
    async def test_upstream_error_field_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._err_field)
        with pytest.raises(ImagefreeError, match="error"):
            await submit_generate("http://host", "cat", "1:1", "tok")

    @pytest.mark.asyncio
    async def test_missing_task_id_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._ok_no_task)
        with pytest.raises(ImagefreeError, match="taskId"):
            await submit_generate("http://host", "cat", "1:1", "tok")

    @pytest.mark.asyncio
    async def test_releases_semaphore_on_error(self, monkeypatch):
        """异常路径也必须 release（防信号量泄漏）。"""
        from api.semaphore_manager import upstream_semaphore
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._err_500)
        with pytest.raises(ImagefreeError):
            await submit_generate("http://host", "cat", "1:1", "tok")
        assert upstream_semaphore.locked() is False


class TestPollGenerateStillPending:
    @pytest.mark.asyncio
    async def test_timeout_raises(self, monkeypatch):
        """持续 202 pending，超过超时 → TimeoutError（短超时 + 短轮询间隔）。"""
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._always_pending)
        with pytest.raises(TimeoutError):
            await poll_generate_status("http://host", "t", timeout=1.0, poll_interval=0.05)

    @pytest.mark.asyncio
    async def test_http_4xx_raises_imgfree(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._status_404)
        with pytest.raises(ImagefreeError, match="404"):
            await poll_generate_status("http://host", "t", timeout=10)

    @pytest.mark.asyncio
    async def test_completed_returns_image(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._completed)
        res = await poll_generate_status("http://host", "t", timeout=10, poll_interval=0.05)
        assert res["status"] == "completed"
        assert res["image"] == "https://img.example/1.png"

    @pytest.mark.asyncio
    async def test_completed_missing_image_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._completed_no_img)
        with pytest.raises(ImagefreeError, match="image"):
            await poll_generate_status("http://host", "t", timeout=10)

    @pytest.mark.asyncio
    async def test_error_status_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._status_error)
        with pytest.raises(ImagefreeError, match="boom"):
            await poll_generate_status("http://host", "t", timeout=10)

    @pytest.mark.asyncio
    async def test_transport_error_retries_then_completes(self, monkeypatch):
        """首次 TransportError → 继续轮询 → 完成。"""
        fake = _FakeClient(sequence=[
            _raise_transport(),
            _Resp(200, {"content-type": "application/json"},
                  {"status": "completed", "image": "https://img.example/2.png"}),
        ])
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: fake)
        res = await poll_generate_status("http://host", "t", timeout=5, poll_interval=0.05)
        assert res["status"] == "completed"


# ── SSRF 防护 + 下载 ──────────────────────────────
class TestDownload:
    @pytest.mark.asyncio
    async def test_rejects_private_ip(self):
        with pytest.raises(ImagefreeError, match="内网|不允许"):
            await download_image("http://127.0.0.1:8001/secret.png")

    @pytest.mark.asyncio
    async def test_rejects_private_resolved_host(self, monkeypatch):
        """域名解析到 10.x → 拒绝；getaddrinfo 无法照常 resolve（不碰真实网络）。"""
        monkeypatch.setattr("api.imagefree_client.socket.getaddrinfo",
                            lambda host, port, **kw: [(2, 1, 6, "", ("10.0.0.5", 80))])
        with pytest.raises(ImagefreeError, match="内网|不允许"):
            await download_image("http://evil.example/x.png")

    @pytest.mark.asyncio
    async def test_oversize_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client.socket.getaddrinfo",
                            lambda host, port, **kw: [(2, 1, 6, "", ("93.184.216.34", 80))])
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._stream_oversize)
        with pytest.raises(ImagefreeError, match="字节上限|超过"):
            await download_image("http://example.com/big.png")

    @pytest.mark.asyncio
    async def test_download_ok(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client.socket.getaddrinfo",
                            lambda host, port, **kw: [(2, 1, 6, "", ("93.184.216.34", 80))])
        monkeypatch.setattr("api.imagefree_client._get_client", lambda: _FakeClient._stream_ok)
        data = await download_image("http://example.com/x.png", max_bytes=1024 * 1024)
        assert data == b"chunk1-chunk2-"


# ── 图生图 ─────────────────────────────────────────
class TestEdit:
    @pytest.mark.asyncio
    async def test_upload_missing_urls_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._edit_client", _fake_edit_client(_Resp(200, {}, {})))
        with pytest.raises(ImagefreeError, match="uploadUrl|publicUrl"):
            await upload_edit_image("http://host", b"img")

    @pytest.mark.asyncio
    async def test_upload_http_error_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._edit_client", _fake_edit_client(_Resp(500, {}, {})))
        with pytest.raises(ImagefreeError):
            await upload_edit_image("http://host", b"img")

    @pytest.mark.asyncio
    async def test_upload_success(self, monkeypatch):
        ok = _Resp(200, {}, {"uploadUrl": "http://up.example/f.png", "publicUrl": "http://pub.example/f.png"})
        fake = _FakeClient(sequence=[ok, _Resp(200, {}, None)])
        monkeypatch.setattr("api.imagefree_client._edit_client", _fake_edit_client(fake))
        pub = await upload_edit_image("http://host", b"img")
        assert pub == "http://pub.example/f.png"

    @pytest.mark.asyncio
    async def test_submit_edit_error_field_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._edit_client",
                            _fake_edit_client(_Resp(200, {"content-type": "application/json"},
                                                    {"error": "bad prompt"})))
        with pytest.raises(ImagefreeError):
            await submit_edit("http://host", "http://i/x.png", "p", "tok")

    @pytest.mark.asyncio
    async def test_submit_edit_success(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._edit_client",
                            _fake_edit_client(_Resp(200, {"content-type": "application/json"},
                                                    {"taskId": "e-1"})))
        tid = await submit_edit("http://host", "http://i/x.png", "p", "tok")
        assert tid == "e-1"

    @pytest.mark.asyncio
    async def test_poll_edit_error_status_raises(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._edit_client", _fake_edit_client(_Resp(422, {}, {})))
        with pytest.raises(ImagefreeError, match="422"):
            await poll_edit_status("http://host", "e", timeout=10)

    @pytest.mark.asyncio
    async def test_poll_edit_completed(self, monkeypatch):
        monkeypatch.setattr(
            "api.imagefree_client._edit_client",
            _fake_edit_client(_Resp(200, {"content-type": "application/json"},
                                    {"status": "completed", "image": "http://pub.example/f.png"})),
        )
        res = await poll_edit_status("http://host", "e", timeout=10, poll_interval=0.05)
        assert res["status"] == "completed"

    @pytest.mark.asyncio
    async def test_poll_edit_timeout(self, monkeypatch):
        monkeypatch.setattr("api.imagefree_client._edit_client",
                            _fake_edit_client(_Resp(202, {}, {"status": "pending"})))
        with pytest.raises(TimeoutError):
            await poll_edit_status("http://host", "e", timeout=1.0, poll_interval=0.05)


# ── 测试替身 ───────────────────────────────────────
class _Resp:
    def __init__(self, status_code, headers, json_body) -> None:
        self.status_code = status_code
        self.headers = headers if headers is not None else {"headers": {"content-type": "application/json"}}
        self._json = json_body
        self.text = json.dumps(json_body) if json_body is not None else ""
        self.cookies = {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


class _TransportError(httpx.TransportError):
    pass


def _raise_transport():
    # 返回/抛出由调用方捕获；直接用 Exception 实例会被 _FakeClient._seq 语义处理
    return _TransportError("boom")


class _FakeClient:
    """可编程 httpx client：顺序响应 / 异常 / 流式。"""

    _ok_200 = None
    _err_500 = None
    _err_field = None
    _ok_no_task = None
    _status_404 = None
    _completed = None
    _completed_no_img = None
    _status_error = None
    _always_pending = None
    _stream_ok = None
    _stream_oversize = None

    def __init__(self, sequence=None, stream=None, _max_iter=None) -> None:
        self._seq = list(sequence or [])
        self._stream = stream or []
        self._max_iter = _max_iter
        self.closed = False

    # 便捷静态响应构造
    @classmethod
    def _make(cls, status, body, ctype="application/json"):
        return cls(sequence=[_Resp(status, {"content-type": ctype}, body)])

    async def get(self, url, params=None, headers=None, timeout=None):
        if self._seq:
            item = self._seq.pop(0)
            if isinstance(item, BaseException):
                raise item
            elif isinstance(item, type) and issubclass(item, BaseException):
                raise item()
            return item
        return _Resp(202, {}, {"status": "pending"})

    async def post(self, url, json=None, headers=None, timeout=None, content=None):
        if self._seq:
            item = self._seq.pop(0)
            if isinstance(item, BaseException):
                raise item
            elif isinstance(item, type) and issubclass(item, BaseException):
                raise item()
            return item
        return _Resp(200, {}, {"taskId": "task-1"})

    async def put(self, url, content=None, headers=None, timeout=None):
        if self._seq:
            item = self._seq.pop(0)
            if isinstance(item, BaseException):
                raise item()
            return item
        return _Resp(200, {}, None)

    def stream(self, method, url, timeout=None):
        # httpx stream 上下文管理器；raise_for_status + aiter_bytes
        return _StreamCtx(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self.closed = True
        return False

    def raise_for_status(self):
        pass  # 无状态码语义（fake 流式直接给字节）

    async def aiter_bytes(self):
        if self._max_iter is not None:
            # 有限迭代器的流式读取（模拟 SSE/块式下载）
            n = 0
            while n < self._max_iter:
                yield self._stream[0] if self._stream else b""
                n += 1
            return
        for chunk in self._stream:
            yield chunk

    def close(self):
        self.closed = True

    async def aclose(self):
        self.closed = True


class _StreamCtx:
    """包装 _FakeClient 成为 httpx.stream 上下文（支持 raise_for_status）。"""

    def __init__(self, fake: "_FakeClient") -> None:
        self._fake = fake

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self._fake.closed = True
        return False

    def raise_for_status(self):
        pass

    def aiter_bytes(self):
        return self._fake.aiter_bytes()


# 注册便捷静态响应（测试模块导入时执行）
_FakeClient._ok_200 = _FakeClient._make(200, {"taskId": "task-1"})
_FakeClient._err_500 = _FakeClient._make(500, {"error": "boom"})
_FakeClient._err_field = _FakeClient._make(200, {"error": "upstream error"})
_FakeClient._ok_no_task = _FakeClient._make(200, {"status": "pending"})
_FakeClient._status_404 = _FakeClient._make(404, {"error": "not found"})
_FakeClient._completed = _FakeClient._make(
    200, {"status": "completed", "image": "https://img.example/1.png", "progress": 100})
_FakeClient._completed_no_img = _FakeClient._make(200, {"status": "completed"})
_FakeClient._status_error = _FakeClient._make(200, {"status": "error", "error": "boom"})
_FakeClient._always_pending = _FakeClient._make(202, {"status": "pending"})
_FakeClient._stream_ok = _FakeClient(stream=[b"chunk1-", b"chunk2-"])
_FakeClient._stream_oversize = _FakeClient(
    stream=[b"x" * (3 * 1024 * 1024)] * 4, _max_iter=4)  # 共 12MB，超过默认 4MB 上限


def _fake_edit_client(fake):
    async def _make(proxy=None):
        # 图生图 client 需支持 post/put/get 的 httpx 对外接口；_Resp 直接当单响应 client
        if isinstance(fake, _Resp):
            return _RespClient(fake)
        return _AsClient(fake)
    return _make


class _RespClient:
    """把单个 _Resp 响应包装成「永远返回该响应的」httpx 风格 client。"""

    def __init__(self, resp: "_Resp") -> None:
        self._resp = resp

    async def post(self, url, **kw):
        return self._resp

    async def put(self, url, **kw):
        return self._resp

    async def get(self, url, **kw):
        return self._resp

    async def aclose(self):
        pass


class _AsClient:
    """把可编程响应对象包装成 httpx 风格 client（post/put/get 转发）。"""

    def __init__(self, backend) -> None:
        self._b = backend

    async def post(self, url, **kw):
        return await self._b.post(url, **kw)

    async def put(self, url, **kw):
        return await self._b.put(url, **kw)

    async def get(self, url, **kw):
        return await self._b.get(url, **kw)

    async def aclose(self):
        if isinstance(self._b, _FakeClient):
            self._b.closed = True