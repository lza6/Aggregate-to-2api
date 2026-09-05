"""cache_warmup / db.queries.task_to_public / email_sources temptf+custom_imap 单元测试（P0-2 续）。

覆盖：
- warmup_cache：各步骤成功/失败容错（mock db 各方法）、统计返回、画廊 limit 循环。
- task_to_public：base64 file:// 读取/超 10MB 跳过/OSError 跳过、IP 私网脱敏、timings 拆解。
- TempTfSource：new_address 随机生成、fetch_mails 成功/非 200/异常。
- CustomImapSource：未配置 is_configured/is_available/new_address 抛错、new_address 成功。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import api.cache_warmup as cw
from api.db.queries import QueueDB, task_to_public
from api.email_sources.custom_imap import CustomImapSource
from api.email_sources.temptf import TempTfSource

# ── cache_warmup.warmup_cache ────────────────────────────────


@pytest.mark.asyncio
async def test_warmup_all_success():
    db = MagicMock()
    db.stats_overview = AsyncMock(return_value={"total": 100})
    db.stats_daily = AsyncMock(return_value=[{"d": "1"}])
    db.stats_monthly = AsyncMock(return_value=[{"m": "1"}])
    db.recent_images = AsyncMock(return_value=[
        {"image_url": "u1", "image_mime": "png", "prompt": "p", "aspect_ratio": "1:1",
         "duration_sec": 1.0, "finished_at": 1.0}
    ])
    cache = MagicMock()
    cache.set = AsyncMock()
    result = await cw.warmup_cache(cache, db)
    assert result["stats:overview"] == 1
    assert result["stats:daily:14"] == 1
    assert result["stats:monthly:12"] == 1
    assert result["gallery:10"] == 1
    assert result["gallery:20"] == 1
    assert result["gallery:50"] == 1


@pytest.mark.asyncio
async def test_warmup_stats_failure_does_not_block_gallery():
    db = MagicMock()
    db.stats_overview = AsyncMock(side_effect=RuntimeError("db down"))
    db.stats_daily = AsyncMock(side_effect=RuntimeError("db down"))
    db.stats_monthly = AsyncMock(side_effect=RuntimeError("db down"))
    db.recent_images = AsyncMock(return_value=[{"image_url": "u", "image_mime": "png",
                                                "prompt": "p", "aspect_ratio": "1:1",
                                                "duration_sec": 1.0, "finished_at": 1.0}])
    cache = MagicMock()
    cache.set = AsyncMock()
    result = await cw.warmup_cache(cache, db)
    assert result["stats:overview"] == 0
    assert result["stats:daily:14"] == 0
    assert result["stats:monthly:12"] == 0
    assert result["gallery:10"] == 1  # 画廊预热仍成功（独立容错）


@pytest.mark.asyncio
async def test_warmup_gallery_partial_failure():
    db = MagicMock()
    db.stats_overview = AsyncMock(return_value={})
    db.stats_daily = AsyncMock(return_value=[])
    db.stats_monthly = AsyncMock(return_value=[])
    # recent_images 对 gallery:20 抛错（模拟某次查询失败）
    call_count = 0

    async def _recent(limit):
        nonlocal call_count
        call_count += 1
        if limit == 20:
            raise OSError("transient")
        return [{"image_url": "u", "image_mime": "png", "prompt": "p",
                 "aspect_ratio": "1:1", "duration_sec": 1.0, "finished_at": 1.0}]

    db.recent_images = _recent
    cache = MagicMock()
    cache.set = AsyncMock()
    result = await cw.warmup_cache(cache, db)
    assert result["gallery:10"] == 1
    assert result["gallery:20"] == 0
    assert result["gallery:50"] == 1


@pytest.mark.asyncio
async def test_warmup_gallery_item_shape():
    db = MagicMock()
    db.stats_overview = AsyncMock(return_value={})
    db.stats_daily = AsyncMock(return_value=[])
    db.stats_monthly = AsyncMock(return_value=[])
    db.recent_images = AsyncMock(return_value=[
        {"image_url": "u1", "image_mime": "png", "prompt": "p", "aspect_ratio": "1:1",
         "duration_sec": 2.5, "finished_at": 1700000000.0}
    ])
    cache = MagicMock()
    cache.set = AsyncMock()
    await cw.warmup_cache(cache, db)
    # gallery:10 的 set 调用参数应是 {items, count}
    calls = cache.set.call_args_list
    gallery_call = next(c for c in calls if c.args[0] == "gallery:10")
    payload = gallery_call.args[1]
    assert payload["count"] == 1
    assert payload["items"][0]["image_url"] == "u1"


# ── task_to_public ───────────────────────────────────────────


def _base_task(**overrides) -> dict:
    base = {
        "id": "t1", "status": "completed", "image_url": "https://x/img.png",
        "image_base64": None, "image_mime": "image/png", "error": None,
        "created_at": 1700000000.0, "duration_sec": 1.5, "type": "txt",
        "model": "imagefree/default", "prompt": "a cat", "aspect_ratio": "1:1",
        "client_ip": "1.2.3.4", "user_agent": "ua",
    }
    base.update(overrides)
    return base


def test_task_to_public_basic():
    out = task_to_public(_base_task())
    assert out["id"] == "t1"
    assert out["status"] == "completed"
    assert out["image_url"] == "https://x/img.png"
    assert out["timings"]["total_sec"] == 1.5
    assert out["prompt"] == "a cat"


def test_task_to_public_file_uri_reads_content(tmp_path, monkeypatch):
    f = tmp_path / "img.b64"
    f.write_text("BASE64DATA")
    t = _base_task(image_base64=f"file://{f}")
    out = task_to_public(t)
    assert out["image_base64"] == "BASE64DATA"


def test_task_to_public_file_uri_oversize_skipped(tmp_path, monkeypatch):
    f = tmp_path / "big.b64"
    f.write_text("x" * (10 * 1024 * 1024 + 1))  # > 10MB
    t = _base_task(image_base64=f"file://{f}")
    out = task_to_public(t)
    assert out["image_base64"] is None


def test_task_to_public_file_uri_oserror_skipped(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("perm")))
    t = _base_task(image_base64="file:///nonexistent/path.b64")
    out = task_to_public(t)
    assert out["image_base64"] is None


def test_task_to_public_internal_ip_masked():
    """私网 IP 不回传（防内网拓扑泄露）。"""
    t = _base_task(client_ip="192.168.1.5")
    out = task_to_public(t)
    assert out["client_ip"] is None or out["client_ip"] == ""
    assert "LAN" not in out["client_location"]  # 显示为局域网，不暴露原 IP


def test_task_to_public_localhost_ip_masked():
    t = _base_task(client_ip="127.0.0.1")
    out = task_to_public(t)
    assert out["client_ip"] is None or out["client_ip"] == ""


def test_task_to_public_public_ip_shown():
    t = _base_task(client_ip="8.8.8.8")
    out = task_to_public(t)
    assert out["client_ip"] == "8.8.8.8"
    assert out["client_location"]  # 非空


def test_task_to_public_no_duration_no_timings():
    t = _base_task(duration_sec=None)
    out = task_to_public(t)
    assert out["timings"] == {}


def test_task_to_public_missing_client_ip():
    t = _base_task(client_ip=None)
    out = task_to_public(t)
    assert out["client_ip"] is None
    assert out["client_location"] == "—"


# ── QueueDB（已废弃但需覆盖）────────────────────────────────


def test_queuedb_lifecycle(tmp_path):
    """QueueDB 虽废弃，覆盖 enqueue/mark/list_pending/cleanup/close 基本路径。"""
    db = QueueDB(str(tmp_path / "q.db"))
    try:
        db.enqueue("t1", priority=1, seq=1)
        db.enqueue("t2", priority=2, seq=2)
        pending = db.list_pending()
        assert len(pending) == 2
        assert pending[0][2] == "t1"  # priority 1 在前
        db.mark_processing("t1")
        pending = db.list_pending()
        assert len(pending) == 1
        db.mark_completed("t1")
        db.mark_completed("t2")
        # cleanup 删 completed/processing。retention 用负值强制 cutoff > created_at（
        # retention=0 时 cutoff==now 而 created_at≈now，created_at<cutoff 不成立会删 0）
        result = db.cleanup(retention_days=-1)
        assert result["deleted"] == 2
    finally:
        db.close()


def test_queuedb_enqueue_ignored_duplicate(tmp_path):
    db = QueueDB(str(tmp_path / "q2.db"))
    try:
        db.enqueue("dup", 1, 1)
        db.enqueue("dup", 1, 1)  # INSERT OR IGNORE
        assert len(db.list_pending()) == 1
    finally:
        db.close()


# ── TempTfSource ─────────────────────────────────────────────


@pytest.fixture
def temptf() -> TempTfSource:
    src = TempTfSource()
    src.session = MagicMock()
    src.session.post = AsyncMock()
    return src


@pytest.mark.asyncio
async def test_temptf_new_address_random():
    src = TempTfSource()
    addr, state = await src.new_address()
    assert "@" in addr
    assert state["source"] == "temp.tf"
    assert state["domain"] in TempTfSource._domains


@pytest.mark.asyncio
async def test_temptf_new_address_uniqueness():
    src = TempTfSource()
    addrs = {(await src.new_address())[0] for _ in range(5)}  # 只取 address（state 是 dict 不可哈希）
    # 5 次随机生成至少 2 个不同地址（极大概率）
    assert len(addrs) >= 2


@pytest.mark.asyncio
async def test_temptf_fetch_success(temptf):
    temptf.session.post.return_value = MagicMock(status_code=200, json=MagicMock(return_value={"data": [{"id": "m1"}]}))
    mails = await temptf.fetch_mails("a@high.edu.pl")
    assert mails == [{"id": "m1"}]


@pytest.mark.asyncio
async def test_temptf_fetch_non_200(temptf):
    temptf.session.post.return_value = MagicMock(status_code=503, json=MagicMock(return_value={}))
    assert await temptf.fetch_mails("a@high.edu.pl") == []


@pytest.mark.asyncio
async def test_temptf_fetch_empty_data(temptf):
    temptf.session.post.return_value = MagicMock(status_code=200, json=MagicMock(return_value={}))
    assert await temptf.fetch_mails("a@high.edu.pl") == []


@pytest.mark.asyncio
async def test_temptf_fetch_exception_swallowed(temptf):
    temptf.session.post.side_effect = ConnectionError("down")
    assert await temptf.fetch_mails("a@high.edu.pl") == []


# ── CustomImapSource ────────────────────────────────────────


def test_custom_imap_unconfigured_defaults():
    src = CustomImapSource()
    assert src.priority == 0
    assert src.is_configured() is False
    assert src.is_available() is False  # 未配置不可用


def test_custom_imap_configured_priority(monkeypatch):
    monkeypatch.setenv("IF_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IF_IMAP_USER", "user@ex.com")
    monkeypatch.setenv("IF_IMAP_PASS", "secret")
    monkeypatch.setenv("IF_IMAP_DOMAIN", "ex.com")
    src = CustomImapSource()
    assert src.priority == 95
    assert src.is_configured() is True
    assert src.is_available() is True  # 配置且未在冷却


def test_custom_imap_ssl_flag_from_env(monkeypatch):
    monkeypatch.setenv("IF_IMAP_SSL", "0")
    src = CustomImapSource()
    assert src.use_ssl is False
    monkeypatch.setenv("IF_IMAP_SSL", "1")
    src2 = CustomImapSource()
    assert src2.use_ssl is True


@pytest.mark.asyncio
async def test_custom_imap_new_address_unconfigured_raises():
    src = CustomImapSource()
    with pytest.raises(RuntimeError, match="未配置"):
        await src.new_address()


@pytest.mark.asyncio
async def test_custom_imap_new_address_configured(monkeypatch):
    monkeypatch.setenv("IF_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IF_IMAP_USER", "user@ex.com")
    monkeypatch.setenv("IF_IMAP_PASS", "secret")
    monkeypatch.setenv("IF_IMAP_DOMAIN", "ex.com")
    src = CustomImapSource()
    addr, state = await src.new_address()
    assert addr.endswith("@ex.com")
    assert state["source"] == "custom-imap"


@pytest.mark.asyncio
async def test_custom_imap_fetch_unconfigured_returns_empty():
    src = CustomImapSource()
    assert await src.fetch_mails("a@ex.com") == []


def test_custom_imap_domain_lstrip_at(monkeypatch):
    monkeypatch.setenv("IF_IMAP_DOMAIN", "@ex.com")  # 带 @ 前缀
    monkeypatch.setenv("IF_IMAP_HOST", "h")
    monkeypatch.setenv("IF_IMAP_USER", "u")
    monkeypatch.setenv("IF_IMAP_PASS", "p")
    src = CustomImapSource()
    assert src.domain == "ex.com"  # @ 被剥离


def test_custom_imap_port_from_env(monkeypatch):
    monkeypatch.setenv("IF_IMAP_PORT", "143")
    src = CustomImapSource()
    assert src.port == 143


def test_custom_imap_explicit_params_override_env():
    src = CustomImapSource(host="h", port=993, username="u", password="p", domain="d.com", use_ssl=False)
    assert src.host == "h" and src.port == 993
    assert src.username == "u" and src.password == "p"
    assert src.domain == "d.com" and src.use_ssl is False
    assert src.is_configured() is True
