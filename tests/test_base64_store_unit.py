"""api/base64_store.py 单元测试（P0-2 覆盖率补强，纯函数无 session loop）。

覆盖：
- _mime_to_ext：已知 mime / 未知 bin / 含 charset 参数。
- save_base64：幂等 file:// 前缀 / 正常写入 / OSError 降级返回原 data。
- read_base64：存在 / 不存在 / OSError 返回 None。
- delete_base64：存在删除 / 不存在不抛 / OSError 静默。
- clean_expired：TTL 内/外文件分类删除 / 目录不存在返回 0。
- gc_stats：hot/cold 统计 / usage_pct 计算 / 目录不可读降级。
- dir_size_gb / list_oldest_files / enforce_quota：配额保护链路。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from api import base64_store as bs
from api import config


@pytest.fixture
def tmp_img_dir(tmp_path, monkeypatch):
    d = tmp_path / "imgs"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "IF_BASE64_DIR", str(d))
    monkeypatch.setattr(bs.config, "IF_BASE64_DIR", str(d))
    return str(d)


# ── _mime_to_ext ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("image/png", "png"),
        ("image/jpeg", "jpg"),
        ("image/webp", "webp"),
        ("image/svg+xml", "svg"),
        ("image/png; charset=binary", "png"),
        ("application/octet-stream", "bin"),
        ("", "bin"),
    ],
)
def test_mime_to_ext(mime, expected):
    assert bs._mime_to_ext(mime) == expected


# ── save_base64 ──────────────────────────────────────────────


def test_save_idempotent_file_prefix(tmp_img_dir):
    """data 已是 file:// 开头 → 原样返回不重写。"""
    assert bs.save_base64("t1", "file:///existing/path", "image/png") == "file:///existing/path"
    assert not os.listdir(tmp_img_dir)


def test_save_writes_file_and_returns_file_uri(tmp_img_dir):
    path = bs.save_base64("t2", "aGVsbG8=", "image/png")
    assert path.startswith("file://") and path.endswith("t2.png")
    with open(path.removeprefix("file://")) as f:
        assert f.read() == "aGVsbG8="


def test_save_oserror_returns_original_data(tmp_img_dir, monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    out = bs.save_base64("t3", "data", "image/png")
    assert out == "data"  # 降级：返回原 base64


# ── read_base64 ───────────────────────────────────────────────


def test_read_returns_content(tmp_img_dir):
    bs.save_base64("r1", "content", "image/jpeg")
    assert bs.read_base64("r1") == "content"


def test_read_missing_returns_none(tmp_img_dir):
    assert bs.read_base64("nope") is None


def test_read_oserror_returns_none(tmp_img_dir, monkeypatch):
    bs.save_base64("r2", "x", "image/png")
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("perm")))
    assert bs.read_base64("r2") is None


# ── delete_base64 ────────────────────────────────────────────


def test_delete_removes_file(tmp_img_dir):
    bs.save_base64("d1", "x", "image/png")
    bs.delete_base64("d1")
    assert bs.read_base64("d1") is None


def test_delete_missing_no_error(tmp_img_dir):
    bs.delete_base64("ghost")  # 不抛


def test_delete_oserror_silenced(tmp_img_dir, monkeypatch):
    bs.save_base64("d2", "x", "image/png")
    monkeypatch.setattr("os.unlink", lambda p: (_ for _ in ()).throw(OSError("locked")))
    bs.delete_base64("d2")  # 不抛


# ── clean_expired ────────────────────────────────────────────


def test_clean_expired_removes_old_only(tmp_img_dir):
    old_path = tmp_img_dir + os.sep + "old.png"
    new_path = tmp_img_dir + os.sep + "new.png"
    with open(old_path, "w") as f:
        f.write("old")
    with open(new_path, "w") as f:
        f.write("new")
    old_ts = time.time() - 9999
    os.utime(old_path, (old_ts, old_ts))
    deleted = bs.clean_expired(ttl=100)
    assert deleted == 1
    assert os.path.exists(new_path)
    assert not os.path.exists(old_path)


def test_clean_expired_dir_missing_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IF_BASE64_DIR", str(tmp_path / "no_such"))
    monkeypatch.setattr(bs.config, "IF_BASE64_DIR", str(tmp_path / "no_such"))
    assert bs.clean_expired(ttl=100) == 0


# ── gc_stats ─────────────────────────────────────────────────


def test_gc_stats_hot_cold_split(tmp_img_dir, monkeypatch):
    monkeypatch.setattr(config, "IF_BASE64_FILE_TTL", 100)
    monkeypatch.setattr(bs.config, "IF_BASE64_FILE_TTL", 100)
    monkeypatch.setattr(config, "IF_IMG_MAX_GB", 10)
    monkeypatch.setattr(bs.config, "IF_IMG_MAX_GB", 10)
    bs.save_base64("hot", "x" * 100, "image/png")
    cold = tmp_img_dir + os.sep + "cold.png"
    with open(cold, "w") as f:
        f.write("y" * 200)
    old_ts = time.time() - 9999
    os.utime(cold, (old_ts, old_ts))
    stats = bs.gc_stats()
    assert stats["total_files"] == 2
    assert stats["hot_files"] == 1
    assert stats["cold_files"] == 1
    assert stats["hot_gb"] > 0
    assert stats["usage_pct"] > 0


def test_gc_stats_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IF_BASE64_DIR", str(tmp_path / "x"))
    monkeypatch.setattr(bs.config, "IF_BASE64_DIR", str(tmp_path / "x"))
    s = bs.gc_stats()
    assert s["total_files"] == 0 and s["usage_pct"] == 0.0


def test_gc_stats_unreadable_dir_falls_back(tmp_img_dir, monkeypatch):
    monkeypatch.setattr("os.listdir", lambda d: (_ for _ in ()).throw(OSError("perm")))
    s = bs.gc_stats()
    assert s["total_files"] == 0


# ── dir_size_gb / list_oldest_files ───────────────────────────


def test_dir_size_gb_recursive(tmp_img_dir):
    sub = Path(tmp_img_dir) / "sub"
    sub.mkdir()
    (sub / "a.png").write_text("x" * 500)
    (Path(tmp_img_dir) / "b.png").write_text("y" * 300)
    size = bs.dir_size_gb(tmp_img_dir)
    assert 0 < size < 0.001  # <1KB → <0.001 GB


def test_dir_size_gb_missing():
    assert bs.dir_size_gb("Z:/no/such/path") == 0.0


def test_list_oldest_files_sorted_by_mtime(tmp_img_dir):
    f1 = Path(tmp_img_dir) / "1.png"
    f2 = Path(tmp_img_dir) / "2.png"
    f1.write_text("a")
    os.utime(f1, (1, 1))
    f2.write_text("b")
    os.utime(f2, (2, 2))
    paths = bs.list_oldest_files(tmp_img_dir)
    assert paths == [str(f1), str(f2)]


def test_list_oldest_files_with_limit(tmp_img_dir):
    for i in range(5):
        f = Path(tmp_img_dir) / f"{i}.png"
        f.write_text("x")
        os.utime(f, (i, i))
    assert len(bs.list_oldest_files(tmp_img_dir, n=2)) == 2


def test_list_oldest_files_missing_dir():
    assert bs.list_oldest_files("Z:/no/such") == []


# ── enforce_quota ────────────────────────────────────────────


def test_enforce_quota_no_deletion_when_under_target(tmp_img_dir):
    Path(tmp_img_dir + os.sep + "x.png").write_text("tiny")
    assert bs.enforce_quota(tmp_img_dir, max_gb=1000) == 0  # 远未超


def test_enforce_quota_deletes_oldest_until_80pct(tmp_img_dir, monkeypatch):
    # 每文件 1KB，配额 0.00001 GB ≈ 10KB → target 8KB → 删若干个旧文件
    monkeypatch.setattr(bs.config, "IF_BASE64_DIR", tmp_img_dir)
    files = []
    for i in range(15):
        f = Path(tmp_img_dir) / f"{i}.png"
        f.write_text("x" * 1024)
        os.utime(f, (i, i))
        files.append(f)
    deleted = bs.enforce_quota(tmp_img_dir, max_gb=0.000015)  # 15KB quota
    assert deleted >= 1
    # 最旧的几个被删，最新的保留
    assert not files[0].exists()
    assert files[-1].exists()


def test_enforce_quota_zero_quota_returns_zero(tmp_img_dir):
    assert bs.enforce_quota(tmp_img_dir, max_gb=0) == 0


def test_enforce_quota_audit_callback_called(tmp_img_dir, monkeypatch):
    monkeypatch.setattr(bs.config, "IF_BASE64_DIR", tmp_img_dir)
    for i in range(10):
        f = Path(tmp_img_dir) / f"{i}.png"
        f.write_text("x" * 1024)
        os.utime(f, (i, i))
    calls = []

    def audit(path, detail):
        calls.append((path, detail))

    bs.enforce_quota(tmp_img_dir, max_gb=0.000008, audit_fn=audit)
    assert len(calls) >= 1
    assert "配额" in calls[0][1]


def test_enforce_quota_missing_dir_returns_zero(tmp_path):
    assert bs.enforce_quota(str(tmp_path / "no"), max_gb=10) == 0


def test_enforce_quota_unlink_error_continues(tmp_img_dir, monkeypatch):
    monkeypatch.setattr(bs.config, "IF_BASE64_DIR", tmp_img_dir)
    for i in range(5):
        Path(tmp_img_dir + os.sep + f"{i}.png").write_text("x" * 1024)
    monkeypatch.setattr("os.unlink", lambda p: (_ for _ in ()).throw(OSError("locked")))
    # unlink 全失败 → deleted=0 但不抛
    assert bs.enforce_quota(tmp_img_dir, max_gb=0.000001) == 0
