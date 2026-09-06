"""P3-D1 向量存储单元测试（sqlite-vec + 降级路径全覆盖）。

覆盖：
- embedding 计算（空/重复词/中文/英文/混合）
- prompt_hash 确定性
- cosine_similarity 正确性
- l2_distance_to_similarity 转换
- VectorStore upsert / find_duplicate / similar_search / list_duplicates / stats
- sqlite-vec 可用 + 降级（线性扫描）双路径
- IF_VECTOR_SEARCH_ENABLED=0 时短路返回
- loop 漂移重建
"""

from __future__ import annotations

import struct

import pytest
import pytest_asyncio

from api.vector import embed, store

# ── embed 纯函数层 ──────────────────────────────────────


class TestEmbedCompute:
    """embedding 计算纯函数。"""

    def test_empty_prompt_returns_unit_vector_first_dim(self):
        blob = embed.compute_embedding("")
        vec = embed._unpack_vec(blob)
        assert len(vec) == embed.EMBED_DIM
        assert vec[0] == pytest.approx(1.0)
        # 其余维度为 0
        assert all(v == 0.0 for v in vec[1:])

    def test_embedding_dim_is_256(self):
        blob = embed.compute_embedding("hello world")
        assert len(blob) == embed.EMBED_DIM * 4  # float32 = 4 bytes
        vec = embed._unpack_vec(blob)
        assert len(vec) == embed.EMBED_DIM

    def test_embedding_is_l2_normalized(self):
        """非空 prompt 的向量应 L2 归一化（模=1）。"""
        import math

        blob = embed.compute_embedding("a cute cat on a mat")
        vec = embed._unpack_vec(blob)
        norm = math.sqrt(sum(v * v for v in vec))
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_same_prompt_same_embedding(self):
        """确定性：同一 prompt 产生同一向量。"""
        a = embed.compute_embedding("a beautiful sunset")
        b = embed.compute_embedding("a beautiful sunset")
        assert a == b

    def test_different_prompt_different_embedding(self):
        a = embed.compute_embedding("a beautiful sunset")
        b = embed.compute_embedding("a scary dark forest")
        assert a != b

    def test_repeated_tokens_produce_same_direction(self):
        """纯计数 + L2 归一化下，'cat cat cat' 与 'cat' 方向相同（量级被归一抹平）。

        这是计数型 embedding 的数学属性：单 token prompt 的频率在归一化后不改变方向。
        精确区分交由 prompt_hash（同 prompt 必同 hash，不同 prompt 必不同 hash）。
        """
        a = embed.compute_embedding("cat cat cat")
        b = embed.compute_embedding("cat")
        # 单 token：归一化后方向相同（合理：语义上都是"猫"）
        assert embed.cosine_similarity(a, b) == pytest.approx(1.0, abs=1e-5)

    def test_repeated_tokens_different_prompt_different_hash(self):
        """精确区分由 prompt_hash 负责。"""
        assert embed.compute_prompt_hash("cat cat cat") != embed.compute_prompt_hash("cat")

    def test_chinese_tokenization(self):
        """中文按字切分：'可爱的猫' 与 '可爱的小猫' 相似但不相同。"""
        a = embed.compute_embedding("可爱的猫")
        b = embed.compute_embedding("可爱的小猫")
        assert a != b
        sim = embed.cosine_similarity(a, b)
        # 共享 '可爱' 的 4 个字符 + 猫，相似度应较高
        assert sim > 0.5

    def test_mixed_cn_en(self):
        """中英混合：'cute 猫' 与 'cute 猫' 确定性。"""
        a = embed.compute_embedding("cute 猫")
        b = embed.compute_embedding("cute 猫")
        assert a == b

    def test_image_bytes_ignored_in_pure_text_impl(self):
        """当前实现忽略 image_bytes（纯 text embedding，预留接口）。"""
        a = embed.compute_embedding("prompt", image_bytes=None)
        b = embed.compute_embedding("prompt", image_bytes=b"\x89PNG fake")
        assert a == b


class TestPromptHash:
    """prompt_hash 精确去重指纹。"""

    def test_deterministic(self):
        assert embed.compute_prompt_hash("hello") == embed.compute_prompt_hash("hello")

    def test_different_prompt_different_hash(self):
        assert embed.compute_prompt_hash("hello") != embed.compute_prompt_hash("world")

    def test_length_32_hex(self):
        """digest_size=16 → 32 hex chars。"""
        h = embed.compute_prompt_hash("test")
        assert len(h) == 32
        int(h, 16)  # 合法 hex


class TestSimilarityFns:
    """相似度计算函数。"""

    def test_cosine_identical_vectors(self):
        v = embed.compute_embedding("hello world")
        assert embed.cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-5)

    def test_cosine_different_vectors_in_range(self):
        a = embed.compute_embedding("hello world")
        b = embed.compute_embedding("scary dark forest")
        sim = embed.cosine_similarity(a, b)
        assert 0.0 <= sim <= 1.0

    def test_cosine_zero_vector(self):
        """全零向量返回 0（避免除零）。"""
        zero = struct.pack(f"<{embed.EMBED_DIM}f", *([0.0] * embed.EMBED_DIM))
        v = embed.compute_embedding("hello")
        assert embed.cosine_similarity(zero, v) == 0.0
        assert embed.cosine_similarity(v, zero) == 0.0

    def test_cosine_dim_mismatch(self):
        a = struct.pack("<4f", 1.0, 0.0, 0.0, 0.0)
        b = struct.pack("<8f", 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert embed.cosine_similarity(a, b) == 0.0

    def test_l2_distance_to_similarity_zero_distance(self):
        """distance=0 → similarity=1（完全相同）。"""
        assert embed.l2_distance_to_similarity(0.0) == pytest.approx(1.0)

    def test_l2_distance_to_similarity_clamped(self):
        """大距离 clamp 到 [0, 1]。"""
        assert embed.l2_distance_to_similarity(100.0) == 0.0
        assert embed.l2_distance_to_similarity(-1.0) == 0.0  # 负距离也 clamp

    def test_l2_distance_to_similarity_monotonic(self):
        """距离越大相似度越低。"""
        assert embed.l2_distance_to_similarity(0.1) > embed.l2_distance_to_similarity(0.5)
        assert embed.l2_distance_to_similarity(0.5) > embed.l2_distance_to_similarity(1.0)


# ── VectorStore 集成层（sqlite-vec 路径）────────────────────


@pytest_asyncio.fixture
async def vec_store(tmp_path, monkeypatch):
    """独立 VectorStore 实例（临时 DB，sqlite-vec 可用路径）。"""
    db_path = str(tmp_path / "vectors.db")
    monkeypatch.setenv("IF_VECTOR_DB_FILE", db_path)
    # 重置检测缓存，确保新实例走完整探测
    store.reset_vec_detection()
    s = store.VectorStore(db_path, enabled=True)
    yield s
    await s.close()
    store.reset_vec_detection()


@pytest_asyncio.fixture
async def vec_store_disabled(tmp_path, monkeypatch):
    """IF_VECTOR_SEARCH_ENABLED=0 的禁用实例。"""
    db_path = str(tmp_path / "vectors_disabled.db")
    s = store.VectorStore(db_path, enabled=False)
    yield s
    await s.close()


@pytest_asyncio.fixture
async def vec_store_no_vec(tmp_path, monkeypatch):
    """强制降级路径（禁用 sqlite-vec）。"""
    db_path = str(tmp_path / "vectors_no_vec.db")
    monkeypatch.setenv("IF_VECTOR_DB_FILE", db_path)
    # mock _detect_vec_available 始终返回 False
    monkeypatch.setattr(store, "_detect_vec_available", lambda: False)
    store.reset_vec_detection()
    s = store.VectorStore(db_path, enabled=True)
    yield s
    await s.close()
    store.reset_vec_detection()


class TestVectorStoreUpsert:
    """upsert + 查重。"""

    async def test_upsert_first_no_duplicate(self, vec_store):
        r = await vec_store.upsert("task-1", "a cute cat on a mat")
        assert r["task_id"] == "task-1"
        assert r["is_duplicate"] is False
        assert r["duplicate_of"] is None

    async def test_upsert_same_prompt_marks_duplicate(self, vec_store):
        """同 prompt 再入库 → 标记重复，similarity ≈ 1.0。"""
        await vec_store.upsert("task-1", "a cute cat on a mat")
        r = await vec_store.upsert("task-2", "a cute cat on a mat")
        assert r["is_duplicate"] is True
        assert r["duplicate_of"] == "task-1"
        assert r["similarity"] > 0.95

    async def test_upsert_similar_prompt_below_threshold(self, vec_store):
        """相似但不同的 prompt 在阈值 0.95 以下不标重复。"""
        await vec_store.upsert("task-1", "a cute cat on a mat")
        r = await vec_store.upsert("task-2", "a scary dark forest at night")
        assert r["is_duplicate"] is False
        assert r["duplicate_of"] is None

    async def test_upsert_idempotent(self, vec_store):
        """同 task_id 多次 upsert 不报错（ON CONFLICT 更新）。"""
        await vec_store.upsert("task-1", "prompt A")
        await vec_store.upsert("task-1", "prompt A")  # 第二次：查重排除自己
        # 第三次仍 OK
        r = await vec_store.upsert("task-1", "prompt A")
        assert r["task_id"] == "task-1"

    async def test_upsert_disabled_short_circuits(self, vec_store_disabled):
        """禁用时不建连接、不写表，直接返回。"""
        r = await vec_store_disabled.upsert("task-1", "prompt")
        assert r["is_duplicate"] is False
        assert r["duplicate_of"] is None
        # 未初始化连接
        assert vec_store_disabled._conn is None


class TestFindDuplicate:
    """find_duplicate 查重。"""

    async def test_find_duplicate_returns_match(self, vec_store):
        await vec_store.upsert("task-1", "a cute cat on a mat")
        emb = embed.compute_embedding("a cute cat on a mat")
        dup = await vec_store.find_duplicate(emb, threshold=0.95)
        assert dup is not None
        assert dup["task_id"] == "task-1"
        assert dup["similarity"] > 0.95

    async def test_find_duplicate_below_threshold(self, vec_store):
        await vec_store.upsert("task-1", "a cute cat on a mat")
        emb = embed.compute_embedding("a scary dark forest")
        dup = await vec_store.find_duplicate(emb, threshold=0.95)
        assert dup is None

    async def test_find_duplicate_exclude_self(self, vec_store):
        """排除自身 task_id。"""
        await vec_store.upsert("task-1", "a cute cat on a mat")
        emb = embed.compute_embedding("a cute cat on a mat")
        dup = await vec_store.find_duplicate(emb, threshold=0.5, exclude_task_id="task-1")
        assert dup is None

    async def test_find_duplicate_disabled(self, vec_store_disabled):
        emb = embed.compute_embedding("hello")
        assert await vec_store_disabled.find_duplicate(emb) is None


class TestSimilarSearch:
    """similar_search KNN 检索。"""

    async def test_similar_search_returns_top_k(self, vec_store):
        """入库 5 个，top_k=3 返回 3 个（不含锚点）。"""
        prompts = [
            "a cute cat on a mat",
            "a cute cat on a mat",  # 重复
            "a beautiful sunset over mountains",
            "a scary dark forest at night",
            "a fast car on highway",
        ]
        for i, p in enumerate(prompts):
            await vec_store.upsert(f"task-{i}", p)

        results = await vec_store.similar_search("task-0", top_k=3)
        assert len(results) <= 3
        assert all(r["task_id"] != "task-0" for r in results)
        # 相似度降序
        sims = [r["similarity"] for r in results]
        assert sims == sorted(sims, reverse=True)

    async def test_similar_search_nonexistent_task(self, vec_store):
        await vec_store.upsert("task-1", "hello")
        results = await vec_store.similar_search("nonexistent", top_k=5)
        assert results == []

    async def test_similar_search_same_prompt_high_similarity(self, vec_store):
        await vec_store.upsert("task-1", "a cute cat on a mat")
        await vec_store.upsert("task-2", "a cute cat on a mat")
        results = await vec_store.similar_search("task-1", top_k=5)
        assert len(results) >= 1
        # task-2 与 task-1 完全相同 prompt，相似度应接近 1.0
        task2 = [r for r in results if r["task_id"] == "task-2"]
        assert task2
        assert task2[0]["similarity"] > 0.95

    async def test_similar_search_disabled(self, vec_store_disabled):
        assert await vec_store_disabled.similar_search("task-1") == []


class TestListDuplicates:
    """list_duplicates 重复项列表。"""

    async def test_list_duplicates_empty(self, vec_store):
        assert await vec_store.list_duplicates() == []

    async def test_list_duplicates_returns_marked(self, vec_store):
        await vec_store.upsert("task-1", "same prompt")
        await vec_store.upsert("task-2", "same prompt")
        await vec_store.upsert("task-3", "same prompt")

        dups = await vec_store.list_duplicates()
        # task-2, task-3 被标记为重复（task-1 是首个，未被标记）
        ids = [d["task_id"] for d in dups]
        assert "task-2" in ids
        assert "task-3" in ids
        assert "task-1" not in ids
        # duplicate_of 指向首个非重复任务（task-1），不指向其他重复项
        for d in dups:
            assert d["duplicate_of"] == "task-1"

    async def test_list_duplicates_limit(self, vec_store):
        for i in range(5):
            await vec_store.upsert(f"task-{i}", "same prompt")
        dups = await vec_store.list_duplicates(limit=2)
        assert len(dups) == 2

    async def test_list_duplicates_disabled(self, vec_store_disabled):
        assert await vec_store_disabled.list_duplicates() == []


class TestStats:
    """stats 统计。"""

    async def test_stats_disabled(self, vec_store_disabled):
        s = await vec_store_disabled.stats()
        assert s["enabled"] is False
        assert s["total"] == 0
        assert s["backend"] == "disabled"

    async def test_stats_enabled_empty(self, vec_store):
        s = await vec_store.stats()
        assert s["enabled"] is True
        assert s["total"] == 0
        assert s["duplicates"] == 0
        assert s["dim"] == embed.EMBED_DIM

    async def test_stats_with_data(self, vec_store):
        await vec_store.upsert("task-1", "prompt A")
        await vec_store.upsert("task-2", "prompt A")  # duplicate
        s = await vec_store.stats()
        assert s["total"] == 2
        assert s["duplicates"] == 1


# ── 降级路径（禁用 sqlite-vec）──────────────────────────


class TestLinearScanFallback:
    """sqlite-vec 不可用时的纯 Python 线性扫描。"""

    async def test_fallback_upsert_and_search(self, vec_store_no_vec):
        """降级路径仍可 upsert + similar_search。"""
        assert vec_store_no_vec._use_vec is False  # 初始化后检查

        await vec_store_no_vec.upsert("task-1", "a cute cat on a mat")
        await vec_store_no_vec.upsert("task-2", "a cute cat on a mat")
        results = await vec_store_no_vec.similar_search("task-1", top_k=5)
        assert len(results) >= 1
        task2 = [r for r in results if r["task_id"] == "task-2"]
        assert task2
        assert task2[0]["similarity"] > 0.95

    async def test_fallback_find_duplicate(self, vec_store_no_vec):
        await vec_store_no_vec.upsert("task-1", "a cute cat on a mat")
        emb = embed.compute_embedding("a cute cat on a mat")
        dup = await vec_store_no_vec.find_duplicate(emb, threshold=0.95)
        assert dup is not None
        assert dup["task_id"] == "task-1"

    async def test_fallback_stats_backend(self, vec_store_no_vec):
        await vec_store_no_vec.upsert("task-1", "prompt")
        s = await vec_store_no_vec.stats()
        assert s["backend"] == "linear-scan"


# ── mark_duplicate 显式标记 ────────────────────────────


class TestMarkDuplicate:
    """mark_duplicate 显式标记。"""

    async def test_mark_duplicate(self, vec_store):
        await vec_store.upsert("task-1", "prompt A", check_duplicate=False)
        await vec_store.upsert("task-2", "prompt B", check_duplicate=False)
        await vec_store.mark_duplicate("task-2", "task-1")
        dups = await vec_store.list_duplicates()
        assert any(d["task_id"] == "task-2" and d["duplicate_of"] == "task-1" for d in dups)

    async def test_mark_duplicate_disabled(self, vec_store_disabled):
        """禁用时无副作用（不抛错）。"""
        await vec_store_disabled.mark_duplicate("task-1", "task-2")
        assert await vec_store_disabled.list_duplicates() == []


# ── 单例工厂 ──────────────────────────────────────────


class TestSingletonFactory:
    """get_vector_store + reset_vector_store。"""

    def test_get_vector_store_singleton(self, monkeypatch, tmp_path):
        monkeypatch.setenv("IF_VECTOR_DB_FILE", str(tmp_path / "singleton.db"))
        store.reset_vector_store()
        s1 = store.get_vector_store()
        s2 = store.get_vector_store()
        assert s1 is s2

    def test_reset_vector_store_creates_new(self, monkeypatch, tmp_path):
        monkeypatch.setenv("IF_VECTOR_DB_FILE", str(tmp_path / "reset.db"))
        store.reset_vector_store()
        s1 = store.get_vector_store()
        store.reset_vector_store()
        s2 = store.get_vector_store()
        assert s1 is not s2

    def test_disabled_flag_from_env(self, monkeypatch, tmp_path):
        """IF_VECTOR_SEARCH_ENABLED 未设时 enabled=False。"""
        monkeypatch.delenv("IF_VECTOR_SEARCH_ENABLED", raising=False)
        monkeypatch.setenv("IF_VECTOR_DB_FILE", str(tmp_path / "disabled.db"))
        store.reset_vector_store()
        s = store.get_vector_store()
        assert s._enabled is False


# ── loop 漂移重建 ──────────────────────────────────────


class TestLoopDriftRebuild:
    """VectorStore 在不同 event loop 间应重建连接。"""

    async def test_rebuild_on_loop_drift(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "loop_drift.db")
        monkeypatch.setenv("IF_VECTOR_DB_FILE", db_path)
        store.reset_vec_detection()
        s = store.VectorStore(db_path, enabled=True)

        # 在 loop A 初始化
        await s.upsert("task-1", "prompt A")
        assert s._initialized is True

        # 模拟 loop 漂移：手动改 _pool_loop 触发重建路径
        s._pool_loop = None  # 强制 mismatch
        # 再次调用应触发 _rebuild_for_loop
        r = await s.upsert("task-2", "prompt B")
        assert r["task_id"] == "task-2"
        assert s._initialized is True
        await s.close()
        store.reset_vec_detection()
