"""P3-D1 画廊相似图检索 + 去重集成测试。

覆盖：
- /v1/gallery/similar 端点（启用/禁用）
- /v1/gallery/similar/stats 端点
- /v1/gallery/duplicates 端点
- on_task_completed 入库钩子（dispatch.py 调用路径）
- IF_VECTOR_SEARCH_ENABLED=0 时端点返回 503
- 端到端：入库 → 查重 → similar_search → list_duplicates 全链路

策略：
- VectorStore 层用独立 tmp_path DB（每用例独立，避免 session DB lock）
- 端点层直接调用路由函数（不启 TestClient lifespan，避免与 session _app_instance 冲突）
"""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def isolated_vector_store(tmp_path, monkeypatch):
    """每用例独立的 VectorStore 实例（避免 session 级连接复用导致 lock）。

    策略：每用例新建 VectorStore + 独立 tmp_path DB，用例结束 await close。
    把全局单例 _vector_store 替换为本用例实例，让 routes/gallery.py 的
    get_vector_store() 拿到本用例实例。
    """
    db_path = str(tmp_path / "vectors.db")
    monkeypatch.setenv("IF_VECTOR_DB_FILE", db_path)
    monkeypatch.setenv("IF_VECTOR_SEARCH_ENABLED", "1")
    monkeypatch.setenv("IF_GALLERY_PASSWORD", "")
    monkeypatch.setenv("IF_GALLERY_SIGNING_SECRET", "")

    from api.vector.store import VectorStore, reset_vec_detection, reset_vector_store

    reset_vector_store()
    reset_vec_detection()
    s = VectorStore(db_path, enabled=True)
    # 替换全局单例
    import api.vector.store as store_mod

    store_mod._vector_store = s
    await s._ensure_initialized()
    yield s
    await s.close()
    store_mod._vector_store = None
    reset_vector_store()
    reset_vec_detection()


@pytest_asyncio.fixture
async def disabled_vector_store(tmp_path, monkeypatch):
    """禁用向量检索的 VectorStore（IF_VECTOR_SEARCH_ENABLED=0）。"""
    monkeypatch.setenv("IF_VECTOR_SEARCH_ENABLED", "0")
    monkeypatch.setenv("IF_GALLERY_PASSWORD", "")
    monkeypatch.setenv("IF_GALLERY_SIGNING_SECRET", "")

    from api.vector.store import VectorStore, reset_vec_detection, reset_vector_store

    reset_vector_store()
    reset_vec_detection()
    s = VectorStore(str(tmp_path / "disabled.db"), enabled=False)
    import api.vector.store as store_mod

    store_mod._vector_store = s
    yield s
    store_mod._vector_store = None
    reset_vector_store()
    reset_vec_detection()


# ── on_task_completed 钩子（纯函数级）────────────────────────


class TestOnTaskCompleted:
    """入库钩子：on_task_completed。"""

    async def test_disabled_short_circuits(self, disabled_vector_store):
        from api.routes.gallery import on_task_completed

        # 禁用时零开销，不抛错
        await on_task_completed("task-1", "prompt A")
        # store 未初始化连接
        assert disabled_vector_store._enabled is False
        assert disabled_vector_store._conn is None

    async def test_enabled_indexes_task(self, isolated_vector_store):
        from api.routes.gallery import on_task_completed

        await on_task_completed("task-1", "a cute cat on a mat")
        stats = await isolated_vector_store.stats()
        assert stats["total"] == 1
        assert stats["duplicates"] == 0

    async def test_same_prompt_marks_duplicate(self, isolated_vector_store):
        """同 prompt 入库两次 → 第二次标记为重复。"""
        from api.routes.gallery import on_task_completed

        await on_task_completed("task-1", "a cute cat on a mat")
        await on_task_completed("task-2", "a cute cat on a mat")

        stats = await isolated_vector_store.stats()
        assert stats["total"] == 2
        assert stats["duplicates"] == 1

    async def test_exception_does_not_propagate(self, isolated_vector_store, monkeypatch):
        """钩子异常不抛（向量检索是旁路，不影响主链路）。"""
        from api.routes.gallery import on_task_completed
        from api.vector import store as store_mod

        original = store_mod.get_vector_store

        def _raise() -> None:
            raise RuntimeError("simulated")

        monkeypatch.setattr(store_mod, "get_vector_store", _raise)
        # 不应抛
        await on_task_completed("task-1", "prompt")
        monkeypatch.setattr(store_mod, "get_vector_store", original)


# ── 端到端：VectorStore 全链路（sqlite-vec 路径）──────────────


class TestVectorEndToEnd:
    """端到端：入库 → 查重 → similar_search → list_duplicates。"""

    async def test_full_flow(self, isolated_vector_store):
        s = isolated_vector_store

        # 入库 5 个，其中 2 个是重复
        await s.upsert("task-1", "a cute cat on a mat")
        await s.upsert("task-2", "a cute cat on a mat")  # 重复
        await s.upsert("task-3", "a beautiful sunset")
        await s.upsert("task-4", "a cute cat on a mat")  # 重复
        await s.upsert("task-5", "a scary dark forest")

        # 1. stats
        stats = await s.stats()
        assert stats["total"] == 5
        assert stats["duplicates"] == 2  # task-2, task-4
        assert stats["backend"] in ("sqlite-vec", "linear-scan")

        # 2. similar_search(task-3) 应能找到 task-1/task-2/task-4（同 prompt）
        results = await s.similar_search("task-3", top_k=5)
        assert len(results) >= 1
        # 相似度降序
        sims = [r["similarity"] for r in results]
        assert sims == sorted(sims, reverse=True)

        # 3. similar_search(task-1) → task-2/task-4 相似度 ≈ 1.0
        results = await s.similar_search("task-1", top_k=5)
        task2 = [r for r in results if r["task_id"] == "task-2"]
        task4 = [r for r in results if r["task_id"] == "task-4"]
        assert task2 and task2[0]["similarity"] > 0.95
        assert task4 and task4[0]["similarity"] > 0.95

        # 4. list_duplicates 返回 task-2, task-4
        dups = await s.list_duplicates()
        ids = [d["task_id"] for d in dups]
        assert set(ids) == {"task-2", "task-4"}
        # duplicate_of 指向 task-1（规范原始任务）
        for d in dups:
            assert d["duplicate_of"] == "task-1"


# ── 端点级测试（直接调用路由函数，不启 TestClient lifespan）──────────


class TestSimilarStatsEndpoint:
    """/v1/gallery/similar/stats 端点（直接调用路由函数）。"""

    async def test_stats_disabled_returns_disabled(self, disabled_vector_store):
        from api.routes.gallery import gallery_similar_stats

        body = await gallery_similar_stats()
        assert body["enabled"] is False
        assert body["backend"] == "disabled"
        assert body["total"] == 0

    async def test_stats_enabled_returns_backend(self, isolated_vector_store):
        from api.routes.gallery import gallery_similar_stats

        body = await gallery_similar_stats()
        assert body["enabled"] is True
        assert body["backend"] in ("sqlite-vec", "linear-scan")
        assert body["dim"] == 256


class TestSimilarEndpoint:
    """/v1/gallery/similar 端点（直接调用路由函数）。"""

    async def test_similar_requires_enabled(self, disabled_vector_store):
        """IF_VECTOR_SEARCH_ENABLED=0 时抛 AppError（503）。"""
        from api.errors import AppError
        from api.routes.gallery import gallery_similar

        with pytest.raises(AppError) as exc_info:
            await gallery_similar(task_id="xxx", top_k=10, password=None)
        assert exc_info.value.status_code == 503

    async def test_similar_nonexistent_task_returns_empty(self, isolated_vector_store):
        from api.routes.gallery import gallery_similar

        body = await gallery_similar(task_id="nonexistent-task-id", top_k=10, password=None)
        assert body["task_id"] == "nonexistent-task-id"
        assert body["items"] == []
        assert body["count"] == 0
        assert body["top_k"] == 10

    async def test_similar_returns_top_k(self, isolated_vector_store):
        """入库几个任务后，similar 端点返回 top_k。"""
        from api.routes.gallery import gallery_similar

        await isolated_vector_store.upsert("task-a", "a cute cat on a mat")
        await isolated_vector_store.upsert("task-b", "a cute cat on a mat")
        await isolated_vector_store.upsert("task-c", "a beautiful sunset")

        body = await gallery_similar(task_id="task-a", top_k=5, password=None)
        assert body["count"] >= 1
        # task-b 相似度应最高（同 prompt）
        items = body["items"]
        task_b = [i for i in items if i["task_id"] == "task-b"]
        assert task_b
        assert task_b[0]["similarity"] > 0.95


class TestDuplicatesEndpoint:
    """/v1/gallery/duplicates 端点（直接调用路由函数）。"""

    async def test_duplicates_requires_enabled(self, disabled_vector_store):
        """IF_VECTOR_SEARCH_ENABLED=0 时抛 AppError（503）。"""
        from api.errors import AppError
        from api.routes.gallery import gallery_duplicates

        with pytest.raises(AppError) as exc_info:
            await gallery_duplicates(limit=50, password=None)
        assert exc_info.value.status_code == 503

    async def test_duplicates_empty(self, isolated_vector_store):
        from api.routes.gallery import gallery_duplicates

        body = await gallery_duplicates(limit=50, password=None)
        assert body["items"] == []
        assert body["count"] == 0
        assert "threshold" in body

    async def test_duplicates_returns_marked(self, isolated_vector_store):
        from api.routes.gallery import gallery_duplicates

        await isolated_vector_store.upsert("task-1", "same prompt")
        await isolated_vector_store.upsert("task-2", "same prompt")

        body = await gallery_duplicates(limit=50, password=None)
        assert body["count"] == 1
        assert body["items"][0]["task_id"] == "task-2"
        assert body["items"][0]["duplicate_of"] == "task-1"

    async def test_duplicates_limit(self, isolated_vector_store):
        from api.routes.gallery import gallery_duplicates

        for i in range(5):
            await isolated_vector_store.upsert(f"task-{i}", "same prompt")

        body = await gallery_duplicates(limit=2, password=None)
        assert len(body["items"]) == 2
