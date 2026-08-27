"""imagefree.net 图像生成 API 客户端。

契约（来自抓包）：
  POST /api/generate  body={prompt, aspect_ratio, turnstile_token}
                      → {taskId, status:"pending"}
  GET  /api/generate/status?taskId=<id>
                      → {status:"completed", image:<r2 url>, progress:100}
                      → {status:"error", error:...} / 其他中间态

H2: 共享单个 httpx.AsyncClient（连接池/keep-alive 复用），避免每任务多次 TLS 握手。
"""
import asyncio
import base64
import ipaddress
import logging
import os
import socket
import time
from collections import deque
from urllib.parse import urlsplit

import httpx

from . import config
from .semaphore_manager import upstream_semaphore

log = logging.getLogger("imagefree")

# 测试钩子：IF_MOCK_UPSTREAM=1 时所有上游交互返回假数据（E2E/CI 零外部依赖、确定性）。
# 与 scripts/mock_cfsolver.py 配合实现完整 mock 模式；生产绝不开。
MOCK_UPSTREAM = os.getenv("IF_MOCK_UPSTREAM", "0").strip().lower() in {"1", "true", "yes", "on"}


def _shrink_buf(buf: bytearray, target: int) -> None:
    """将扩展过大的 bytearray 缩容到 target 字节，回收扩容产生的流浪内存。

    CPython 的 bytearray 切片删除（del buf[target:]）会物理 realloc 到 target
    （实测 ob_alloc 回到 target+1）；随后 clear() 清零长度。调用方获得的仍是
    一个已清空（len=0）的 bytearray，可继续 extend 追加。
    """
    if len(buf) <= target:
        buf.clear()
        return
    del buf[target:]
    buf.clear()


class _BufferPool:
    """大缓冲区池：复用 bytearray，减少 download_image 大对象反复分配的 GC 压力。

    P-05: 只对 download 专属内存做复用。bytearray 自身不可弱引用，故池中持有的是
    可弱引用的 _Slot 包装；池用 deque 登记"空闲"槽——槽的强引用常驻 _slots
    （模块级 _buffer_pool 持有，进程存活期间不释放），空闲集合随租出/归还动态
    变化（P2-6 从 WeakSet 改为 deque：不再依赖弱引用作为可用标记，逻辑更直白）。

    并发语义（与任务示例等价但修正了正确性）：
    - 初始全部预分配槽登记为空闲；acquire 从空闲集取走一个并清除，返回内部
      bytearray；空闲集因此随租出而动态缩小。
    - release 按身份把槽放回空闲集；重复入池由"已空闲谓词"去重，池成员数不膨胀。
    - acquire 时空闲集为空（全部租出）则新建临时缓冲——永不阻塞、永不抛异常。
      扩展过大（超过预分配）的缓冲在 acquire 时用 _shrink_buf 截断回收"流浪内存"。
    """

    __slots__ = ("_slots", "_pool", "_prealloc_size")

    class _Slot:
        """槽位：内嵌预分配 bytearray（cpython 不支持 bytearray 弱引用）。

        无 __weakref__（P2-6：改用 deque 登记，不再需要弱引用能力）。
        """

        __slots__ = ("buf", "idle")

        def __init__(self, buf: bytearray) -> None:
            self.buf = buf
            self.idle = True  # P2-6: 显式空闲标记，供 release 去重（避免槽重复入池）

    def __init__(self, max_size: int = 10, prealloc_size: int = 64 * 1024) -> None:
        self._slots = tuple(self._Slot(bytearray(prealloc_size)) for _ in range(max_size))
        self._pool: "deque[_BufferPool._Slot]" = deque(self._slots)  # 仅登记空闲槽，初始全部空闲
        self._prealloc_size = prealloc_size

    def acquire(self) -> bytearray:
        """获取一个缓冲区：优先复用池中空闲的预分配内存，返回其内部 bytearray。

        返回字节数组已清空（初始容量 = _prealloc_size 或经截断复用的容量）。
        调用方直接对返回值做 bytearray.extend() 追加；_PoolView 仅在 Python 代码层
        提供长度与最终字节截取。返回值仍被 _slots 强引用，调用方不得持有跨调用的
        引用，且必须负责在 finally 中通过 release() 归还。
        """
        while self._pool:
            slot = self._pool.popleft()
            if not slot.idle:  # 防御：已空闲标记的槽若出现在池中，跳过（逻辑<->标记 本应同步）
                continue
            slot.idle = False
            buf = slot.buf
            if len(buf) <= self._prealloc_size:
                # 未扩容缓冲：直接清空复用（保留容量）
                buf.clear()
                return buf
            # 扩展过大的缓冲：截断到预分配下沿，回收扩容产生的流浪内存
            _shrink_buf(buf, self._prealloc_size)
            return buf
        return bytearray(self._prealloc_size)  # 全部租出：新建临时缓冲（复用失败路径）

    def release(self, buf: bytearray) -> None:
        """归还缓冲区到池中。

        始终通过身份匹配将预分配槽位归还到 _pool 中（idle 谓词保证已空闲槽
        不会重复入池，池成员数严格 ≤ _slots 槽数），临时缓冲（非 _slots 成员）
        直接静默释放。移除原 `>= _max_size` 早期返回以避免并发 release 中两个
        task 同时观察到 `len(_pool) == _max_size - 1` 而其中一个被丢弃的 TOCTOU
        竞争（P2-6）。预分配槽常驻 _slots 不会因池成员数达上限而泄漏；超出
        _prealloc_size 的扩容缓冲由下一次 acquire 的截断逻辑处理。
        """
        for slot in self._slots:
            if slot.buf is buf:
                if not slot.idle:  # P2-6: 已在池中则跳过，避免重复登记
                    slot.idle = True
                    self._pool.append(slot)
                return


class _PoolView:
    """缓冲池视图容器：为调用方提供写入 API（extend）并跟踪实时长度。

    内部持有 acquire 返回的 bytearray；写入通过 bytearray 原生 extend 追加，
    len() 反映已写入字节数。与任务契约（io.BytesIO 或 bytearray 包装）对齐。
    """

    __slots__ = ("_buf", "_len")

    def __init__(self, buf: bytearray) -> None:
        self._buf = buf
        self._len = 0

    @classmethod
    def from_pool(cls, pool) -> "_PoolView":
        return cls(pool.acquire())

    def extend(self, data: bytes) -> None:
        """追加字节：写到底层缓冲区，并更新已写长度。"""
        self._buf.extend(data)
        self._len += len(data)

    def __len__(self) -> int:
        return self._len

    def __bytes__(self) -> bytes:
        """返回截至 _len 的精确字节副本（与池内后续复用隔离）。"""
        return bytes(self._buf[: self._len])


# P-05: 模块级共享图像下载缓冲区池（H2 连接池之外的又一层大对象复用）
# 预分配 10 个 64KB 槽位；模块基类天然强持有 _slots，保证复用对象常驻不失效。
_buffer_pool = _BufferPool(max_size=10, prealloc_size=64 * 1024)


class ImagefreeError(RuntimeError):
    pass


# ── 共享连接池（H2）─────────────────────────────────
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """惰性创建共享 client：复用连接，避免每请求 TLS 握手。"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            proxy=config.PROXY,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": config.USER_AGENT},
            limits=httpx.Limits(
                max_keepalive_connections=config.IF_HTTP_KEEPALIVE,
                max_connections=config.IF_HTTP_MAX_CONNECTIONS,
            ),
        )
    return _client


async def close_client() -> None:
    """服务停止时关闭共享连接池。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _browser_headers(base_url: str, referer: str | None = None) -> dict:
    """模拟前端 fetch 的浏览器头（抓包中前端只显式设了 Content-Type，其余为标准头）。"""
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": base_url,
        "Referer": referer or (base_url + "/"),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=1, i",
    }
    return h


async def submit_generate(
    base_url: str,
    prompt: str,
    aspect_ratio: str,
    turnstile_token: str,
    timeout: float = 30.0,
    proxy: str | None = None,
) -> str:
    """提交生成任务，返回 taskId。

    连接默认走模块级共享 client（H2，创建时绑定 config.PROXY），不逐调用新建。
    传入 proxy 时改用一次性 client 走该出口 —— 必须与解 token 时传给 cf_solver
    的 proxy 同一 IP（Turnstile token 与 IP 绑定，见 _edit_client 同款约束）。
    通过全局信号量控制上游并发（IF_UPSTREAM_MAX_INFLIGHT）。
    """
    await upstream_semaphore.acquire()
    own_client: httpx.AsyncClient | None = None
    try:
        if MOCK_UPSTREAM:
            return f"mock-task-{int(time.time() * 1000)}"
        url = f"{base_url}/api/generate"
        payload = {"prompt": prompt, "aspect_ratio": aspect_ratio, "turnstile_token": turnstile_token}
        client = _get_client()
        if proxy:
            # 直连被 429 → 换出口重试路径：一次性 client，绕过共享 H2 连接池
            own_client = httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(30.0),
                                           headers={"User-Agent": config.USER_AGENT})
            client = own_client
        r = await client.post(url, json=payload, headers=_browser_headers(base_url),
                              timeout=httpx.Timeout(timeout))
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

        if r.status_code != 200 or data.get("error"):
            detail = data.get("error") or f"HTTP {r.status_code}"
            raise ImagefreeError(f"generate 提交失败: {detail}")

        task_id = data.get("taskId")
        if not task_id:
            raise ImagefreeError(f"generate 响应缺少 taskId: {data}")
        log.info("generate 已提交 taskId=%s%s", task_id, " (proxy)" if proxy else "")
        return task_id
    finally:
        if own_client is not None:
            await own_client.aclose()
        upstream_semaphore.release()


async def poll_generate_status(
    base_url: str,
    task_id: str,
    timeout: float = 180.0,
    poll_interval: float = 2.0,
) -> dict:
    """轮询生成状态直到 completed/error，返回 {status, image, progress, ...}。

    通过全局信号量控制上游并发（IF_UPSTREAM_MAX_INFLIGHT）。
    """
    await upstream_semaphore.acquire()
    try:
        if MOCK_UPSTREAM:
            await asyncio.sleep(0.1)
            return {"status": "completed", "image": "https://mock.example/images/x.png", "progress": 100}
        url = f"{base_url}/api/generate/status"
        deadline = time.monotonic() + timeout
        client = _get_client()
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("生成超时")
            try:
                r = await client.get(url, params={"taskId": task_id}, headers=_browser_headers(base_url),
                                     timeout=httpx.Timeout(30))
            except httpx.TransportError as e:
                log.warning("status 请求异常: %s", e)
                await asyncio.sleep(poll_interval)
                continue

            # MEDIUM-3: 上游持续 4xx/5xx 时直接失败，而不是空耗到超时（404 表示任务丢失，重试无意义）
            if r.status_code >= 400:
                raise ImagefreeError(f"状态查询失败: HTTP {r.status_code} {r.text[:120]}")

            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            status = data.get("status")
            if status == "completed":
                image = data.get("image")
                if not image:
                    raise ImagefreeError(f"completed 但缺 image 字段: {data}")
                return {"status": "completed", "image": image, "progress": data.get("progress", 100)}
            if status in ("error", "failed"):
                raise ImagefreeError(f"生成失败: {data.get('error') or data}")
            # 中间态（pending/progress），继续轮询
            await asyncio.sleep(poll_interval)
    finally:
        upstream_semaphore.release()


async def download_image(
    image_url: str,
    timeout: float = 60.0,
    max_bytes: int = 4 * 1024 * 1024,
) -> bytes:
    """下载图片二进制（R2 URL 公开可访问）。SSRF 防护：拒绝私网/回环/链路本地地址。"""
    if MOCK_UPSTREAM:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # 最小合法 PNG 魔数（detect_mime 识别用）
    # SSRF 防护：检查 URL 目标地址，并绑定 IP 连接防止 DNS rebinding（P0-4）
    host = urlsplit(image_url).hostname
    if not host:
        raise ImagefreeError(f"图片 URL 无效: {image_url}")
    try:
        results = socket.getaddrinfo(host, 80, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ImagefreeError(f"图片 URL 无法解析: {image_url}")
    # 使用解析后的 IP 地址连接，而非主机名，防止 DNS rebinding（TOCTOU）
    first_ip = None
    for i in results:
        a = ipaddress.ip_address(i[4][0])
        if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast:
            raise ImagefreeError(f"不允许下载内网地址的图片: {image_url}")
        if first_ip is None:
            first_ip = i[4][0]
    # 用 IP 替换主机名（保持端口和路径不变）
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(image_url)
    ip_port = f"{first_ip}:{parsed.port}" if parsed.port else first_ip
    safe_url = urlunparse((parsed.scheme, ip_port, parsed.path, parsed.params, parsed.query, parsed.fragment))
    client = _get_client()
    buf = _PoolView(_buffer_pool.acquire())
    try:
        async with client.stream("GET", safe_url, timeout=httpx.Timeout(timeout),
                                 headers={"Host": host}) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ImagefreeError(f"图片超过 {max_bytes} 字节上限")
            return bytes(buf)
    finally:
        _buffer_pool.release(buf._buf)


def to_base64(data: bytes, mime: str = "image/png") -> str:
    """图片二进制 → data URI，方便调用方直接展示。"""
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def detect_mime(data: bytes) -> str:
    """按文件魔数判定图片类型（比 URL 后缀匹配可靠，H8）。"""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "application/octet-stream"


# ── 图生图（/api/ai-photo-editor 通道）─────────────
# 上游契约（在线探测确认）：
#   POST /api/ai-photo-editor/upload-url  body={filename, content_type} → {uploadUrl, publicUrl}
#   PUT  {uploadUrl}                      图片字节 → 对象存储
#   POST /api/ai-photo-editor  body={image_url, prompt, turnstile_token} → {taskId}
#   GET  /api/ai-photo-editor/status?taskId= → {status, image}
#
# proxy 参数：住宅代理池会话（图生图并发绕过）。token 与提交必须同一代理 IP，
# 故 upload/submit/poll 全走该代理；cf_solver 解 token 时也传同一 proxy。

async def _edit_client(proxy: str | None) -> httpx.AsyncClient:
    """图生图专用 client：指定代理时新建（session 绑定），否则用共享连接池。"""
    if proxy:
        return httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(30.0),
                                 headers={"User-Agent": config.USER_AGENT})
    return _get_client()


async def upload_edit_image(base_url: str, image_bytes: bytes, content_type: str = "image/png",
                            timeout: float = 60.0, proxy: str | None = None) -> str:
    """上传图片到上游对象存储，返回 publicUrl。"""
    if MOCK_UPSTREAM:
        return "https://mock.example/uploads/edit.png"
    client = await _edit_client(proxy)
    headers = _browser_headers(base_url, referer=base_url + "/ai-photo-editor")
    r = await client.post(f"{base_url}/api/ai-photo-editor/upload-url",
                          json={"filename": "edit.png", "content_type": content_type},
                          headers=headers, timeout=httpx.Timeout(timeout))
    if r.status_code != 200:
        raise ImagefreeError(f"获取上传地址失败: HTTP {r.status_code} {r.text[:120]}")
    data = r.json()
    upload_url, public_url = data.get("uploadUrl"), data.get("publicUrl")
    if not upload_url or not public_url:
        raise ImagefreeError(f"上传响应缺 uploadUrl/publicUrl: {data}")
    up = await client.put(upload_url, content=image_bytes,
                          headers={"Content-Type": content_type},
                          timeout=httpx.Timeout(timeout))
    if up.status_code not in (200, 201, 204):
        raise ImagefreeError(f"上传图片失败: HTTP {up.status_code} {up.text[:120]}")
    log.info("图生图图片已上传 publicUrl=%s%s", public_url, " (proxy)" if proxy else "")
    if proxy:
        await client.aclose()
    return public_url


async def submit_edit(base_url: str, image_url: str, prompt: str, turnstile_token: str,
                      timeout: float = 30.0, proxy: str | None = None) -> str:
    """提交图生图任务，返回 taskId。"""
    if MOCK_UPSTREAM:
        return f"mock-edit-task-{int(time.time() * 1000)}"
    client = await _edit_client(proxy)
    headers = _browser_headers(base_url, referer=base_url + "/ai-photo-editor")
    r = await client.post(f"{base_url}/api/ai-photo-editor",
                          json={"image_url": image_url, "prompt": prompt,
                                "turnstile_token": turnstile_token},
                          headers=headers, timeout=httpx.Timeout(timeout))
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or data.get("error"):
        detail = data.get("error") or f"HTTP {r.status_code}"
        raise ImagefreeError(f"图生图提交失败: {detail}")
    tid = data.get("taskId")
    if not tid:
        raise ImagefreeError(f"图生图响应缺少 taskId: {data}")
    log.info("图生图已提交 taskId=%s%s", tid, " (proxy)" if proxy else "")
    if proxy:
        await client.aclose()
    return tid


async def poll_edit_status(base_url: str, task_id: str,
                           timeout: float = 180.0, poll_interval: float = 2.0,
                           proxy: str | None = None) -> dict:
    """轮询图生图状态直到 completed/error，返回 {status, image, ...}。"""
    if MOCK_UPSTREAM:
        await asyncio.sleep(0.1)
        return {"status": "completed", "image": "https://mock.example/images/edit.png"}
    url = f"{base_url}/api/ai-photo-editor/status"
    deadline = time.monotonic() + timeout
    client = await _edit_client(proxy)
    try:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("图生图生成超时")
            try:
                r = await client.get(url, params={"taskId": task_id}, headers=_browser_headers(base_url),
                                     timeout=httpx.Timeout(30))
            except httpx.TransportError as e:
                log.warning("图生图 status 请求异常: %s", e)
                await asyncio.sleep(poll_interval)
                continue
            if r.status_code >= 400:
                raise ImagefreeError(f"图生图状态查询失败: HTTP {r.status_code} {r.text[:120]}")
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            status = data.get("status")
            if status == "completed":
                image = data.get("image")
                if not image:
                    raise ImagefreeError(f"图生图 completed 但缺 image: {data}")
                return {"status": "completed", "image": image}
            if status in ("error", "failed"):
                raise ImagefreeError(f"图生图失败: {data.get('error') or data}")
            await asyncio.sleep(poll_interval)
    finally:
        if proxy:
            await client.aclose()
