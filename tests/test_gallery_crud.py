"""tests/test_gallery_crud.py — v16 P0-3 画廊管理端测试（TDD）。

覆盖（直接调 db 方法 + 端点函数，不启 TestClient lifespan，避免 session DB 冲突）：
- gallery_list：分页/status/model/search 过滤；默认排除 deleted/pending
- gallery_get：单张详情；软删后 404
- gallery_soft_delete：软删 → 列表不再出现（可回滚：数据仍在）
- gallery_search：prompt 子串过滤
- gallery_detail 端点：含 similar 推荐降级（向量未启用 → 空列表不崩）
- gallery_zip 端点：打包 ZIP 流式返回 200 + X-Skipped 头；缺图不崩

策略：每用例独立 tmp DB（conftest.tmp_db 同款），monkeypatch 替换 api.meta.db 与
routes.gallery._db 返回，直接调端点函数（httpx StreamingResponse 验证 zip 头）。
"""

from __future__ import annotations

import base64
import os
import tempfile

import pytest
import pytest_asyncio
from fastapi.responses import StreamingResponse

from api.routes import gallery as gallery_routes


@pytest_asyncio.fixture
async def gdb():
    """独立临时 DB（复用 conftest.tmp_db 同款实现，含建表）+ base64 文件目录隔离。"""
    from api.db import DB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DB(path)
    await db._ensure_initialized()
    # base64 文件落盘指向临时目录（防污染 data/imgs；base64_store 动态读 config.IF_BASE64_DIR）
    from api import config as cfg

    cfg.IF_BASE64_DIR = tempfile.mkdtemp(prefix="gallery_imgs_")
    yield db
    try:
        await db.close()
    except Exception:
        pass
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


async def _seed(gdb, task_id: str, prompt: str, *, status: str = "completed", image_url: str | None = "mock://img.png", model: str = "imagefree/default"):
    """直接插一行画廊任务（base64 走生产 data-URI 落盘路径，供 zip 测试）。"""
    from api.base64_store import save_base64

    raw = b"\x89PNG\r\n\x1a\nfake-image-data"
    b64 = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
    stored = save_base64(task_id, b64, "image/png")  # → file:// 路径
    await gdb._enqueue_write(
        "INSERT INTO requests (id, prompt, status, image_url, image_base64, image_mime, created_at, finished_at, duration_sec, model)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (task_id, prompt, status, image_url, stored, "image/png", 1000.0, 1001.0, 0.5, model),
    )
    await gdb.flush()


@pytest.fixture(autouse=True)
def _pin_meta_db(gdb, monkeypatch):
    """把 gallery 端点用的 meta.db 指向本用例独立 DB。"""
    import api.meta as meta_mod

    monkeypatch.setattr(meta_mod, "db", gdb)
    monkeypatch.setattr(gallery_routes, "_db", lambda: gdb)
    # H4：delete 端点叠加管理 Key（check_admin_key）——测试环境显式开放模式放行。
    # 注：conftest 的 IF_ADMIN_KEY_OPEN=1 只在 _app_instance(session) 里设，本文件不走
    # app 实例，故这里自设 + 重置 settings 单例（动态读 env，open 判定才生效）。
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
    from api.config import reset_settings

    reset_settings()
    yield


@pytest_asyncio.fixture
async def seeded_gdb(gdb):
    await _seed(gdb, "t1", "一只橘猫晒太阳")
    await _seed(gdb, "t2", "蓝色星球抽象艺术")
    await _seed(gdb, "t3", "一只橘猫在花园", model="nanobanana/banana")
    await _seed(gdb, "t4", "被删除的图", status="deleted")
    await _seed(gdb, "t5", "等待中的图", status="pending", image_url=None)
    return gdb


@pytest.mark.asyncio
async def test_gallery_list_pagination_and_filters(seeded_gdb):
    """分页 + 默认排除 deleted/pending；total 正确；列表不投影 base64（防分页 OOM）。"""
    items, total = await seeded_gdb.gallery_list(page=1, page_size=10)
    # 仅 completed 且有图：t1/t2/t3（deleted t4、pending t5 排除）
    assert total == 3
    ids = {i["id"] for i in items}
    assert ids == {"t1", "t2", "t3"}
    # 列表项不含 image_base64（ZIP 显式 read_base64，列表不背 10MB 级字段）
    assert all("image_base64" not in i for i in items)


@pytest.mark.asyncio
async def test_gallery_list_status_and_model_filter(seeded_gdb):
    items, total = await seeded_gdb.gallery_list(status="completed", model="nanobanana/banana")
    assert total == 1 and items[0]["id"] == "t3"


@pytest.mark.asyncio
async def test_gallery_list_search_prompt_substring(seeded_gdb):
    items, total = await seeded_gdb.gallery_list(search="橘猫")
    assert total == 2
    assert {i["id"] for i in items} == {"t1", "t3"}


@pytest.mark.asyncio
async def test_gallery_get_and_missing(seeded_gdb):
    item = await seeded_gdb.gallery_get("t1")
    assert item is not None and item["prompt"] == "一只橘猫晒太阳"
    assert await seeded_gdb.gallery_get("t4") is None  # deleted 不可见
    assert await seeded_gdb.gallery_get("no_such") is None


@pytest.mark.asyncio
async def test_gallery_soft_delete_removes_from_list(seeded_gdb):
    ok = await seeded_gdb.gallery_soft_delete("t2")
    assert ok is True
    items, total = await seeded_gdb.gallery_list(page=1, page_size=10)
    assert total == 2 and {i["id"] for i in items} == {"t1", "t3"}
    # 再次删除同一张 → False（已 deleted）
    assert await seeded_gdb.gallery_soft_delete("t2") is False
    # 软删数据仍在 DB（可回滚）：直接查库
    row = await seeded_gdb.gallery_get("t2")  # deleted 不可见
    assert row is None
    # 原始行仍在（未物理删）

    conn = await seeded_gdb._get_read_conn()
    cursor = await conn.execute("SELECT status FROM requests WHERE id='t2'")
    r = await cursor.fetchone()
    assert r[0] == "deleted"


@pytest.mark.asyncio
async def test_gallery_detail_endpoint_with_similar_degraded(seeded_gdb, monkeypatch):
    """端点级详情：向量未启用时 similar 降级空列表不崩。"""
    monkeypatch.setattr(gallery_routes, "_vector_enabled", lambda: False)
    resp = await gallery_routes.gallery_detail("t1", password=None, top_k=5)
    assert resp["item"]["id"] == "t1"
    assert resp["similar"] == [] and resp["similar_count"] == 0
    # 不存在 → 404 AppError
    from api.errors import AppError

    with pytest.raises(AppError) as ei:
        await gallery_routes.gallery_detail("no_such", password=None, top_k=5)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_gallery_zip_endpoint_streams(seeded_gdb):
    """打包端点：流式 ZIP 200 + X-Skipped 头；含 deleted/缺失张跳过。"""

    from api.routes.gallery import _ZipRequest

    payload = _ZipRequest(task_ids=["t1", "t2", "t4", "no_such"])
    resp = await gallery_routes.gallery_zip(payload, password=None)
    assert isinstance(resp, StreamingResponse)
    assert resp.media_type == "application/zip"
    # 收集流并断言可解压
    chunks = b"".join([c async for c in resp.body_iterator])
    assert chunks.startswith(b"PK")  # zip magic
    skipped = resp.headers.get("X-Skipped", "")
    assert "t4" in skipped  # deleted 张被跳过
    assert "no_such" in skipped  # 缺失张被跳过
    # 解压校验内容
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(chunks))
    names = zf.namelist()
    assert "t1.png" in names and "t2.png" in names
    assert zf.read("t1.png").startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_gallery_delete_endpoint(seeded_gdb):
    # H4：删除叠加管理 Key 校验（check_admin_key）。测试环境 IF_ADMIN_KEY_OPEN=1 开放模式放行，
    # 传最小 Request scope 使鉴权链走真实路径（非 monkeypatch 掉）。
    from fastapi import Request

    from api.errors import AppError

    req = Request({"type": "http", "method": "DELETE", "url": "http://test/gallery/t1", "headers": [], "query_string": b"", "client": ("127.0.0.1", 1)})
    resp = await gallery_routes.gallery_delete("t1", request=req, password=None)
    assert resp["deleted"] is True and resp["soft"] is True
    # 软删后缓存失效（M2）：gallery:{limit} 缓存不应再含 t1（此处仅断言不抛异常即可，缓存细节见集成）
    from api.meta import gallery_cache

    await gallery_cache.invalidate_prefix("gallery:")
    with pytest.raises(AppError):
        await gallery_routes.gallery_delete("t1", request=req, password=None)  # 已删 → 404
