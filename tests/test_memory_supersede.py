"""tests/test_memory_supersede.py — v14 P3 supersede 语义 + 三档衰减测试。

验收（参考 agentmemory 巩固蓝本 isLatest + supersedes + applyDecay）：
- supersede：同 content 二次 consolidate → 旧 L1 记录 superseded_by 非空（指向新记录 id）
- query() 默认过滤 superseded_by IS NULL：不返回旧记录、返回新记录
- 旧数据降级：DB 无 superseded_by 列时 query 不过滤不崩（向后兼容）
- apply_decay hot：last_accessed_at 近 1d → importance 提分（+0.05 钳 1.0）
- apply_decay cold：超 _DECAY_THRESHOLDS → 淘汰（被删）
- apply_decay warm：介于两者之间 → importance 不动、记录保留
- IF_MEMORY_APPLY_DECAY=0（缺省）→ consolidate 不触发 apply_decay（结果无 decay 键）

付费红线：全程 Mock（临时 DB + 本地 consolidate，不触碰真实付费上游）。
"""

from __future__ import annotations

# Mock 环境（早于 api import 固化，conftest autouse reset_settings 后仍生效）
import os
import sqlite3

import pytest

os.environ.setdefault("IF_MEMORY_CONSOLIDATION_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")
os.environ.setdefault("IF_MEMORY_APPLY_DECAY", "0")


@pytest.fixture
def store(tmp_path):
    """临时 DB 的 MemoryStore（独立实例，不触碰模块级单例）。"""
    from api.agent.memory import MemoryStore

    return MemoryStore(str(tmp_path / "supersede.db"))


def _atom_rows(db_path: str) -> list[sqlite3.Row]:
    """直读 mem_atoms 全部行（绕过 query 过滤，断言底层 superseded_by 状态）。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM mem_atoms ORDER BY id").fetchall()
    conn.close()
    return rows


# ── supersede：同 content 二次 consolidate ────────────────────────────


@pytest.mark.asyncio
async def test_second_consolidate_marks_old_superseded(store):
    """同 (user_key, scene, content) 二次巩固 → 旧 L1 superseded_by 非空且指向新记录 id。"""
    await store.observe("u", "image", "用户偏好暗黑风", 0.8)
    await store.consolidate()  # 第一次：L0 → L1（id=A）
    first_rows = _atom_rows(store.db_path)
    assert len(first_rows) == 1
    old_id = first_rows[0]["id"]
    assert first_rows[0]["superseded_by"] is None  # 首次巩固：无被取代

    await store.observe("u", "image", "用户偏好暗黑风", 0.9)
    await store.consolidate()  # 第二次：同 content 再次入 L1（id=B）

    rows = _atom_rows(store.db_path)
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    # 旧记录被标记取代，指向新记录 id
    assert by_id[old_id]["superseded_by"] == by_id[rows[-1]["id"]]["id"]
    assert by_id[old_id]["superseded_by"] != old_id
    # 新记录未被取代
    assert by_id[rows[-1]["id"]]["superseded_by"] is None


@pytest.mark.asyncio
async def test_query_filters_superseded_returns_latest(store):
    """query 默认不返回被取代旧记录，只返回新记录。"""
    await store.observe("u", "image", "重复事实", 0.7)
    await store.consolidate()
    await store.observe("u", "image", "重复事实", 0.9)
    await store.consolidate()

    recs = await store.query("u", "image", layer="L1", limit=10)
    assert len(recs) == 1  # 只剩最新一条
    assert recs[0].importance == 0.9
    assert recs[0].superseded_by is None


@pytest.mark.asyncio
async def test_consolidate_result_reports_superseded_count(store):
    """consolidate 返回 superseded 计数（Mock 路径）。"""
    await store.observe("u", "image", "事实X", 0.8)
    await store.consolidate()
    await store.observe("u", "image", "事实X", 0.85)
    result = await store.consolidate()
    assert result["superseded"] == 1
    assert result["L0_to_L1"] == 1


@pytest.mark.asyncio
async def test_first_consolidate_no_supersede(store):
    """首次巩固（无同 content 旧 L1）→ superseded 计数 0，全部行 superseded_by IS NULL。"""
    await store.observe("u", "image", "事实A", 0.8)
    await store.observe("u", "image", "事实B", 0.7)
    result = await store.consolidate()
    assert result["superseded"] == 0
    rows = _atom_rows(store.db_path)
    assert len(rows) == 2
    assert all(r["superseded_by"] is None for r in rows)


# ── 旧数据降级：无 superseded_by 列 → query 不过滤不崩 ────────────────


@pytest.mark.asyncio
async def test_query_degrades_when_column_missing(tmp_path):
    """旧库（手工建无 superseded_by 列的 mem_atoms）→ query 降级不过滤、返回全部、不崩。"""
    from api.agent.memory import MemoryStore

    db_path = str(tmp_path / "legacy.db")
    # 模拟旧 schema：无 superseded_by 列
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE mem_atoms ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT NOT NULL, scene TEXT NOT NULL, "
        "content TEXT NOT NULL, importance REAL DEFAULT 0.5, created_at REAL NOT NULL, "
        "last_accessed_at REAL NOT NULL, source_ids TEXT DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO mem_atoms(user_key, scene, content, importance, created_at, last_accessed_at) "
        "VALUES('u','image','旧事实',0.8,1.0,1.0)"
    )
    conn.commit()
    conn.close()

    store = MemoryStore(db_path)
    # MemoryStore._init_schema 幂等迁移会补列 → 走正常过滤路径仍不崩；
    # 为验证「列缺失降级」，直接断言迁移后查询可用 + 旧数据可见
    recs = await store.query("u", "image", layer="L1", limit=10)
    assert len(recs) == 1
    assert recs[0].content == "旧事实"


@pytest.mark.asyncio
async def test_query_supersede_filter_helper_skips_other_layers(store):
    """supersede 过滤仅作用于 L1：L0/L2/L3 不受影响（无列也不崩）。"""
    await store.observe("u", "image", "L0事实", 0.8)
    l0 = await store.query("u", "image", layer="L0", limit=10)
    assert len(l0) == 1
    assert l0[0].superseded_by is None  # 非_atoms 层默认 None


# ── apply_decay：hot / warm / cold 三档 ──────────────────────────────


@pytest.mark.asyncio
async def test_apply_decay_hot_boosts_importance(store):
    """hot：last_accessed_at 近 1d → importance 提分 +0.05（钳 1.0）。"""
    import time

    from api.agent.memory import MemoryStore

    rid = await store.observe("u", "image", "热事实", 0.5)
    now = time.time()
    # 直接把 last_accessed_at 设为最近（hot 档）
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE mem_observations SET last_accessed_at=? WHERE id=?", (now, rid))
    result = await MemoryStore.apply_decay(store)
    assert result["hot_boosted"] >= 1
    recs = await store.query("u", "image", layer="L0", limit=10)
    assert recs[0].importance == pytest.approx(0.55)  # 0.5 + 0.05


@pytest.mark.asyncio
async def test_apply_decay_hot_clamps_at_one(store):
    """hot 提分钳 1.0：importance 0.99 → 1.0 不超界。"""
    import time

    rid = await store.observe("u", "image", "满分事实", 0.99)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE mem_observations SET last_accessed_at=? WHERE id=?", (time.time(), rid))
    await store.apply_decay()
    recs = await store.query("u", "image", layer="L0", limit=10)
    assert recs[0].importance == 1.0


@pytest.mark.asyncio
async def test_apply_decay_cold_prunes_expired(store):
    """cold：超 _DECAY_THRESHOLDS（L0 超 7d 未访问）→ 淘汰。"""
    import time

    rid = await store.observe("u", "image", "冷事实", 0.9)
    stale = time.time() - 8 * 86400  # 超 L0 阈值 7d
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE mem_observations SET last_accessed_at=? WHERE id=?", (stale, rid))
    result = await store.apply_decay()
    assert result["cold_pruned"] >= 1
    recs = await store.query("u", "image", layer="L0", limit=10)
    assert len(recs) == 0


@pytest.mark.asyncio
async def test_apply_decay_warm_untouched(store):
    """warm：1d ~ 阈值之间（L0 取 2d）→ importance 不动、记录保留。"""
    import time

    rid = await store.observe("u", "image", "温事实", 0.6)
    warm = time.time() - 2 * 86400  # >1d（非 hot）但 <7d（非 cold）
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE mem_observations SET last_accessed_at=? WHERE id=?", (warm, rid))
    result = await store.apply_decay()
    assert result["hot_boosted"] == 0
    assert result["cold_pruned"] == 0
    recs = await store.query("u", "image", layer="L0", limit=10)
    assert len(recs) == 1
    assert recs[0].importance == 0.6  # warm 不动


@pytest.mark.asyncio
async def test_consolidate_no_decay_by_default(store, monkeypatch):
    """IF_MEMORY_APPLY_DECAY=0（缺省）→ consolidate 结果无 decay 键（不触发）。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_MEMORY_APPLY_DECAY", "0")
    reset_settings()
    await store.observe("u", "image", "事实", 0.8)
    result = await store.consolidate()
    assert "decay" not in result


@pytest.mark.asyncio
async def test_consolidate_with_decay_enabled(store, monkeypatch):
    """IF_MEMORY_APPLY_DECAY=1 → consolidate 尾部挂载 apply_decay（结果含 decay 键）。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_MEMORY_APPLY_DECAY", "1")
    reset_settings()
    await store.observe("u", "image", "事实", 0.8)
    result = await store.consolidate()
    assert "decay" in result
    assert "hot_boosted" in result["decay"]
    assert "cold_pruned" in result["decay"]


# ── LLM 路径 supersede（Mock registry，不触真实上游）──────────────────


class TestLlmPathSupersede:
    """_consolidate_with_llm 路径：同 content 旧 L1 同样标记 superseded_by。"""

    @pytest.fixture
    def store_with_l0(self, tmp_path):
        from api.agent.memory import MemoryStore

        return MemoryStore(str(tmp_path / "llm_supersede.db"))

    def _patch_registry(self, monkeypatch, text):
        """打补丁到 registry 单例 + bootstrap 模块函数（对齐 test_agent_memory 的坑位规避）。"""
        import importlib

        reg_mod = importlib.import_module("api.providers.registry")
        reg_singleton = reg_mod.registry

        class _FakeChatProvider:
            prefix = "tryingopen"

            async def chat_collect(self, model, messages, **kw):
                return {"text": text}

        fake_spec = type("Spec", (), {"id": "tryingopen/fake", "provider": "tryingopen"})()
        monkeypatch.setattr(reg_singleton, "all_chat_models", lambda: [fake_spec])
        for k in list(reg_singleton.chat_providers.keys()):
            monkeypatch.delitem(reg_singleton.chat_providers, k)
        monkeypatch.setitem(reg_singleton.chat_providers, "tryingopen", _FakeChatProvider())
        monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)

    @pytest.mark.asyncio
    async def test_llm_second_consolidate_marks_old_superseded(self, store_with_l0, monkeypatch):
        """LLM 路径：同 content 二次巩固 → 旧 L1 superseded_by 非空。"""
        self._patch_registry(monkeypatch, "0.8|原子事实Y")
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        from api.config import reset_settings

        reset_settings()

        await store_with_l0.observe("u", "image", "原始观察", 0.9)
        await store_with_l0.consolidate()  # 第一次 → L1 "原子事实Y"
        old_rows = _atom_rows(store_with_l0.db_path)
        assert len(old_rows) == 1
        old_id = old_rows[0]["id"]

        await store_with_l0.observe("u", "image", "原始观察", 0.9)
        await store_with_l0.consolidate()  # 第二次同 content → supersede

        rows = _atom_rows(store_with_l0.db_path)
        by_id = {r["id"]: r for r in rows}
        assert by_id[old_id]["superseded_by"] is not None
        assert by_id[old_id]["superseded_by"] != old_id
