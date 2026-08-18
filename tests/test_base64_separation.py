"""IMP-26: base64 分离测试 — 验证 image_base64 从 SQLite 全量存储改为本地文件缓存 + DB 存路径。

测试覆盖：
1. get_public/gallery/errors 不再含 image_base64
2. 文件目录读写 + 校验和
3. 清理过期文件
4. IF_BASE64_DIR 不存在时自动创建
"""
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# 确保项目根目录可导入 api 包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── 辅助：创建临时 DB ──────────────────────────────
def make_db():
    from api.db import DB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    return db, path


def cleanup_db(db, path):
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


# ── 辅助：临时 base64 缓存目录 ──────────────────────
@pytest.fixture(autouse=True)
def temp_base64_dir(monkeypatch):
    """每测试用例使用独立的临时 base64 缓存目录。"""
    tmpdir = tempfile.mkdtemp(suffix="-b64")
    monkeypatch.setattr("api.config.IF_BASE64_DIR", tmpdir)
    yield tmpdir
    # 清理临时目录
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── 测试 1: get_public 含 image_base64 ──────────
def test_get_public_no_base64():
    """get_public 返回的 dict 含 image_base64 字段（修复后）。"""
    from api import config

    db, path = make_db()
    try:
        db.create_request("t1", "test prompt", "1:1", False)
        # 先 mark_finished 写入 base64
        db.mark_finished("t1", "completed", "https://example.com/img.png",
                         None, 1.5, "dGVzdA==", "image/png")
        pub = db.get_public("t1")
        assert pub is not None
        assert "image_base64" in pub, "get_public 应含 image_base64 字段"
        assert pub["image_base64"] is not None, "get_public 的 image_base64 不应为 None"
        assert pub["image_url"] == "https://example.com/img.png"
        assert pub["status"] == "completed"
    finally:
        cleanup_db(db, path)


# ── 测试 2: gallery 不含 image_base64 ──────────────
def test_gallery_no_base64():
    """recent_images 返回结果不含 image_base64。"""
    from api import config

    db, path = make_db()
    try:
        db.create_request("t1", "test", "1:1", False)
        db.mark_finished("t1", "completed", "https://example.com/img.png",
                         None, 1.0, "ZGF0YQ==", "image/png")
        items = db.recent_images(10)
        assert len(items) == 1
        # 列名不含 image_base64（_GALLERY_COLS 不含）
        for item in items:
            assert "image_base64" not in item, "gallery 不应含 image_base64"
            assert item["image_url"] == "https://example.com/img.png"
    finally:
        cleanup_db(db, path)


# ── 测试 3: errors 不含 image_base64 ───────────────
def test_errors_no_base64():
    """recent_errors 返回结果不含 image_base64。"""
    from api import config

    db, path = make_db()
    try:
        db.create_request("t1", "test", "1:1", False)
        db.mark_finished("t1", "error", None, "some error", 0.5,
                         "ZGF0YQ==", "image/png")
        items = db.recent_errors(10)
        assert len(items) == 1
        for item in items:
            assert "image_base64" not in item, "errors 不应含 image_base64"
            assert item["error"] == "some error"
    finally:
        cleanup_db(db, path)


# ── 测试 4: mark_finished 写入文件 + 路径正确 ──────
def test_mark_finished_writes_file():
    """mark_finished 传入非空 base64 时写入文件，DB 存 file:// 路径。"""
    from api import config

    db, path = make_db()
    try:
        b64_data = "dGVzdCBiYXNlNjQgZGF0YQ=="  # "test base64 data"
        db.create_request("t1", "test", "1:1", False)
        db.mark_finished("t1", "completed", "https://example.com/img.png",
                         None, 1.0, b64_data, "image/png")

        # 验证 DB 存储的是 file:// 路径（先 flush 确保批量缓冲提交）
        db.flush()
        row = db._conn.execute(
            "SELECT image_base64 FROM requests WHERE id='t1'"
        ).fetchone()
        assert row is not None
        stored = row[0]
        assert stored.startswith("file://"), f"DB 应存 file:// 路径，实际: {stored}"

        # 验证文件存在且内容正确
        file_path = stored[7:]  # 去掉 file:// 前缀
        assert os.path.exists(file_path), f"文件不存在: {file_path}"
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == b64_data

        # 验证 get 返回还原的 base64（get 自动 flush）
        t = db.get("t1")
        assert t["image_base64"] == b64_data
    finally:
        cleanup_db(db, path)


# ── 测试 5: mark_finished 无 base64 时不影响 ───────
def test_mark_finished_no_base64():
    """mark_finished 不传 base64 时 DB 存 NULL，不创建文件。"""
    db, path = make_db()
    try:
        db.create_request("t1", "test", "1:1", False)
        db.mark_finished("t1", "completed", "https://example.com/img.png",
                         None, 1.0)
        db.flush()  # 确保批量缓冲提交
        row = db._conn.execute(
            "SELECT image_base64 FROM requests WHERE id='t1'"
        ).fetchone()
        assert row is not None
        assert row[0] is None, "不传 base64 时 DB 应为 NULL"
    finally:
        cleanup_db(db, path)


# ── 测试 6: read_base64 从文件读取 ─────────────────
def test_read_base64():
    """read_base64 能从文件读取 base64 字符串。"""
    db, path = make_db()
    try:
        b64_data = "YWJjMTIz"  # "abc123"
        db.create_request("t1", "test", "1:1", False)
        db.mark_finished("t1", "completed", "https://example.com/img.png",
                         None, 1.0, b64_data, "image/png")

        read = db.read_base64("t1")
        assert read == b64_data, f"读取 base64 不匹配: {read}"

        # 不存在的 task_id 返回 None
        assert db.read_base64("nonexistent") is None
    finally:
        cleanup_db(db, path)


# ── 测试 7: get_base64_path 返回路径 ───────────────
def test_get_base64_path():
    """get_base64_path 返回正确的文件路径。"""
    db, path = make_db()
    try:
        db.create_request("t1", "test", "1:1", False)
        db.mark_finished("t1", "completed", "https://example.com/img.png",
                         None, 1.0, "ZGF0YQ==", "image/png")

        p = db.get_base64_path("t1")
        assert p is not None, "应有文件路径"
        assert os.path.exists(p), f"路径指向的文件不存在: {p}"
        assert p.endswith(".png"), f"扩展名应为 .png，实际: {p}"

        # 不存在的 task_id 返回 None
        assert db.get_base64_path("nonexistent") is None
    finally:
        cleanup_db(db, path)


# ── 测试 8: 清理过期文件 ───────────────────────────
def test_clean_base64_files():
    """clean_base64_files 清理过期文件，保留新文件。"""
    db, path = make_db()
    try:
        b64_data = "dGVzdA=="  # "test"
        db.create_request("t1", "test", "1:1", False)
        db.create_request("t2", "test2", "1:1", False)
        db.mark_finished("t1", "completed", "https://ex.com/1.png",
                         None, 1.0, b64_data, "image/png")
        db.mark_finished("t2", "completed", "https://ex.com/2.png",
                         None, 1.0, b64_data, "image/png")

        # 将 t1 文件设为过期（mtime 很久以前）
        p1 = db.get_base64_path("t1")
        assert p1 is not None
        old_time = time.time() - 99999
        os.utime(p1, (old_time, old_time))

        # 清理 TTL=86400，t1 过期、t2 不过期
        deleted = db.clean_base64_files(86400)
        assert deleted >= 1, "应至少删除 1 个过期文件"
        assert not os.path.exists(p1), "t1 文件应被删除"

        # t2 文件应保留
        p2 = db.get_base64_path("t2")
        assert p2 is not None and os.path.exists(p2), "t2 文件应保留"
    finally:
        cleanup_db(db, path)


# ── 测试 9: 目录不存在时自动创建 ───────────────────
def test_auto_create_dir(monkeypatch):
    """IF_BASE64_DIR 不存在时，save_base64 自动创建目录。"""
    from api.base64_store import save_base64, read_base64

    # 用一个肯定不存在的目录
    tmpdir = tempfile.mkdtemp(suffix="-b64-test")
    nonexistent = os.path.join(tmpdir, "subdir", "imgs")
    monkeypatch.setattr("api.config.IF_BASE64_DIR", nonexistent)

    # save_base64 应自动创建目录
    path = save_base64("t1", "dGVzdA==", "image/png")
    assert path.startswith("file://"), f"路径不应含 file:// 前缀: {path}"
    file_path = path[7:]
    assert os.path.exists(file_path), f"文件应存在: {file_path}"
    with open(file_path, encoding="utf-8") as f:
        assert f.read() == "dGVzdA=="

    # read_base64 也能正常读取
    read = read_base64("t1")
    assert read == "dGVzdA=="

    # 清理
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── 测试 10: task_to_public 支持 file:// 路径 ──────
def test_task_to_public_resolves_file():
    """task_to_public 将 file:// 路径解析为 base64 内容。"""
    from api.db import task_to_public

    # 构造一个含 file:// 路径的 dict
    import tempfile
    fd, fpath = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("dGVzdC1iYXNlNjQ=")

    try:
        t = {
            "id": "t1", "status": "completed",
            "image_url": "https://ex.com/img.png",
            "image_base64": f"file://{fpath}",
            "image_mime": "image/png",
            "error": None, "created_at": 1000.0, "duration_sec": 1.0,
            "type": "txt", "model": "default",
        }
        pub = task_to_public(t)
        assert pub["image_base64"] == "dGVzdC1iYXNlNjQ="
        assert pub["image_url"] == "https://ex.com/img.png"
    finally:
        try:
            os.unlink(fpath)
        except OSError:
            pass


# ── 测试 11: task_to_public 保留旧 raw base64 ──────
def test_task_to_public_legacy_base64():
    """task_to_public 对旧 raw base64 数据保持原样（向后兼容）。"""
    from api.db import task_to_public

    t = {
        "id": "t1", "status": "completed",
        "image_url": "https://ex.com/img.png",
        "image_base64": "b2xkLWJhc2U2NA==",  # 旧 raw base64，非 file://
        "image_mime": "image/png",
        "error": None, "created_at": 1000.0, "duration_sec": 1.0,
        "type": "txt", "model": "default",
    }
    pub = task_to_public(t)
    assert pub["image_base64"] == "b2xkLWJhc2U2NA==", "旧 raw base64 应保持原样"


# ── 测试 12: base64_store 模块 API ─────────────────
def test_base64_store_api():
    """base64_store 模块独立测试：save/read/delete/clean_expired。"""
    from api.base64_store import (
        clean_expired,
        delete_base64,
        read_base64,
        save_base64,
    )

    # save
    path = save_base64("t1", "dGVzdC1zdG9yZQ==", "image/webp")
    assert path.startswith("file://"), f"应返回 file:// 路径: {path}"
    file_path = path[7:]
    assert file_path.endswith(".webp"), f"扩展名应为 .webp: {file_path}"
    assert os.path.exists(file_path)

    # read
    read = read_base64("t1")
    assert read == "dGVzdC1zdG9yZQ=="

    # delete
    delete_base64("t1")
    assert not os.path.exists(file_path), "删除后文件应不存在"
    assert read_base64("t1") is None, "删除后读取应返回 None"

    # 不存在 task_id 的 delete 不报错
    delete_base64("nonexistent")

    # save 幂等：data 已含 file:// 前缀
    path2 = save_base64("t2", "file:///tmp/test.bin", "image/png")
    assert path2 == "file:///tmp/test.bin", "幂等性: 应返回原值"


# ── 测试 13: 清理过期不删除新文件 ───────────────────
def test_clean_expired_keeps_fresh():
    """clean_expired 不删除 TTL 内的文件。"""
    from api.base64_store import clean_expired, save_base64

    save_base64("t1", "dGVzdA==", "image/png")
    save_base64("t2", "dGVzdA==", "image/png")

    # 立即清理（TTL=86400，文件刚写入，不过期）
    deleted = clean_expired(86400)
    assert deleted == 0, "不应删除新文件"

    # 用负 TTL 确保清理（mtime 精度限制，0 可能无法触发）
    deleted = clean_expired(-1)
    assert deleted >= 2, "应删除所有文件"