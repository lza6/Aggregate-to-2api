"""tests/test_agent_memory.py — P1-A3 L0-L3 记忆分层 + 异步巩固测试。

验收：
- MemoryStore 建 4 张表（mem_observations/mem_atoms/mem_scenarios/mem_persona）
- observe L0 写入
- query 各层查询
- consolidate Mock 路径：L0→L1 去重 + importance>=0.6 筛选
- 衰减淘汰：超期 L0 记忆被 prune
- 开关关闭：consolidate 返回 0（零回归）
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("IF_MEMORY_CONSOLIDATION_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")


@pytest.fixture
def store(tmp_path):
    """临时 DB 的 MemoryStore。"""
    from api.agent.memory import MemoryStore

    db_path = str(tmp_path / "test_mem.db")
    return MemoryStore(db_path)


@pytest.mark.asyncio
async def test_observe_and_query_l0(store):
    """observe L0 写入 + query L0 查询。"""
    rid = await store.observe("user1", "image", "喜欢猫咪风格", 0.8)
    assert rid > 0
    recs = await store.query("user1", "image", layer="L0", limit=10)
    assert len(recs) == 1
    assert recs[0].content == "喜欢猫咪风格"
    assert recs[0].importance == 0.8
    assert recs[0].layer == "L0"


@pytest.mark.asyncio
async def test_consolidate_mock_promotes_high_importance(store):
    """Mock 巩固：importance>=0.6 的 L0 提升到 L1。"""
    await store.observe("u", "image", "高重要性事实", 0.9)
    await store.observe("u", "image", "低重要性事实", 0.3)
    result = await store.consolidate()
    assert result["L0_to_L1"] == 1  # 只有 importance>=0.6 的被提升
    # L0 已清空（巩固后删除）
    l0 = await store.query("u", "image", layer="L0", limit=10)
    assert len(l0) == 0
    # L1 有 1 条
    l1 = await store.query("u", "image", layer="L1", limit=10)
    assert len(l1) == 1
    assert l1[0].content == "高重要性事实"


@pytest.mark.asyncio
async def test_consolidate_mock_deduplicates(store):
    """Mock 巩固：相同 content 去重（取 importance 最高）。"""
    await store.observe("u", "image", "重复事实", 0.7)
    await store.observe("u", "image", "重复事实", 0.9)  # 相同 content，更高 importance
    result = await store.consolidate()
    assert result["L0_to_L1"] == 1  # 去重后只 1 条
    l1 = await store.query("u", "image", layer="L1", limit=10)
    assert len(l1) == 1
    assert l1[0].importance == 0.9  # 取最高


@pytest.mark.asyncio
async def test_query_updates_access_time(store):
    """query 更新访问时间（hot 记忆不衰减）。"""
    await store.observe("u", "image", "事实", 0.9)
    recs = await store.query("u", "image", layer="L0", limit=10)
    assert len(recs) == 1
    old_access = recs[0].last_accessed_at
    # 等 0.1s 再查，访问时间应更新
    await asyncio.sleep(0.1)
    recs2 = await store.query("u", "image", layer="L0", limit=10)
    assert recs2[0].last_accessed_at > old_access


@pytest.mark.asyncio
async def test_disabled_consolidate_returns_zero(monkeypatch, store):
    """IF_MEMORY_CONSOLIDATION_ENABLED=0 → consolidate 返回 0（零回归）。"""
    import api.agent.memory as mem_mod

    monkeypatch.setattr(mem_mod, "MEMORY_CONSOLIDATION_ENABLED", False)
    await store.observe("u", "image", "事实", 0.9)
    result = await store.consolidate()
    assert result == {"L0_to_L1": 0, "pruned": 0}


@pytest.mark.asyncio
async def test_memory_store_creates_four_tables(store):
    """MemoryStore 建 4 张记忆表。"""
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'mem_%'"
        ).fetchall()
    }
    conn.close()
    assert "mem_observations" in tables
    assert "mem_atoms" in tables
    assert "mem_scenarios" in tables
    assert "mem_persona" in tables


@pytest.mark.asyncio
async def test_query_unknown_layer_returns_empty(store):
    """未知 layer 查询返回空列表（不崩）。"""
    await store.observe("u", "image", "事实", 0.9)
    recs = await store.query("u", "image", layer="L99", limit=10)
    assert recs == []


@pytest.mark.asyncio
async def test_consolidation_loop_starts_and_stops(store):
    """巩固后台 worker 启停正常。"""
    await store.start_consolidation_loop()
    assert store._consolidation_task is not None
    assert not store._consolidation_task.done()
    await store.stop_consolidation_loop()
    assert store._consolidation_task.done() or store._consolidation_task.cancelled()


# ── P0-11 补测：_consolidate_with_llm 真实路径（Mock registry）──────────
# 覆盖 api/agent/memory.py:249-325 _consolidate_with_llm 分支（当前 66% 覆盖率）
# 关键：memory.py:265 用函数内 `from ..providers.registry import bootstrap, registry`，
# 故 monkeypatch 必须打在 api.providers.registry 模块的 registry/bootstrap 符号上（函数内 from-import 读模块属性）。
class TestConsolidateWithLlmPath:
    """真实 LLM 巩固路径：Mock registry.all_chat_models + chat_collect 返回压缩文本。

    覆盖要点：
    - L0 有数据时按 scene 分组压缩
    - LLM 返回 "importance|content" 行格式，importance>=0.5 写入 L1
    - 巩固后清空 L0
    - chat_models 为空时回退 _consolidate_mock
    - provider 为 None 时回退 _consolidate_mock
    - LLM 抛异常时回退 _consolidate_mock
    - L0 无数据时返回 0（不调 LLM）
    """

    @pytest.fixture
    def store_with_l0(self, tmp_path):
        """预填 L0 观察记录的 MemoryStore。"""
        from api.agent.memory import MemoryStore

        return MemoryStore(str(tmp_path / "test_llm_mem.db"))

    def _patch_registry(self, monkeypatch, chat_models, chat_providers):
        """打补丁到 registry 单例 + bootstrap 模块函数。

        关键坑：`import api.providers.registry as reg_mod` 在本项目会被 providers/__init__.py
        的 `from .registry import registry` 拦截，reg_mod 绑成 Registry 实例而非模块。
        用 importlib.import_module 显式拿子模块对象，才能 monkeypatch 模块级 bootstrap。
        """
        import importlib

        reg_mod = importlib.import_module("api.providers.registry")
        reg_singleton = reg_mod.registry

        monkeypatch.setattr(reg_singleton, "all_chat_models", lambda: chat_models)
        for k in list(reg_singleton.chat_providers.keys()):
            monkeypatch.delitem(reg_singleton.chat_providers, k)
        for k, v in chat_providers.items():
            monkeypatch.setitem(reg_singleton.chat_providers, k, v)
        monkeypatch.setattr(reg_mod, "bootstrap", lambda: None)

    @pytest.mark.asyncio
    async def test_llm_consolidate_promotes_and_clears_l0(self, store_with_l0, monkeypatch):
        """真实 LLM 路径：LLM 返回压缩行 → importance>=0.5 写入 L1 → 清空 L0。"""
        await store_with_l0.observe("u1", "image", "事实A", 0.9)
        await store_with_l0.observe("u1", "image", "事实B", 0.8)

        class _FakeChatProvider:
            prefix = "tryingopen"

            async def chat_collect(self, model, messages, **kw):
                return {"text": "0.8|压缩原子事实A\n0.6|压缩原子事实B\n0.2|低重要性忽略"}

        fake_spec = type("Spec", (), {"id": "tryingopen/fake", "provider": "tryingopen"})()
        self._patch_registry(monkeypatch, [fake_spec], {"tryingopen": _FakeChatProvider()})

        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")
        result = await store_with_l0.consolidate()
        assert result["L0_to_L1"] == 2  # importance>=0.5 的两条
        # consolidate 已 DELETE L0 并 commit；用新连接读（避免 query 的 _touch_access
        # 在 consolidate 持有的连接未释放时触发 SQLite lock）
        import sqlite3

        with sqlite3.connect(store_with_l0.db_path) as conn:
            conn.row_factory = sqlite3.Row
            l0_cnt = conn.execute("SELECT COUNT(*) FROM mem_observations").fetchone()[0]
            l1_cnt = conn.execute("SELECT COUNT(*) FROM mem_atoms").fetchone()[0]
        assert l0_cnt == 0  # L0 已清空
        assert l1_cnt == 2  # L1 有 2 条

    @pytest.mark.asyncio
    async def test_llm_consolidate_no_chat_models_falls_back_mock(self, store_with_l0, monkeypatch):
        """all_chat_models 返回空 → 回退 _consolidate_mock（不崩）。"""
        await store_with_l0.observe("u1", "image", "事实A", 0.9)
        self._patch_registry(monkeypatch, [], {})
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        result = await store_with_l0.consolidate()
        # 回退 mock 路径：importance>=0.6 的提升
        assert result["L0_to_L1"] == 1

    @pytest.mark.asyncio
    async def test_llm_consolidate_provider_none_falls_back_mock(self, store_with_l0, monkeypatch):
        """provider 为 None（前缀不匹配）→ 回退 mock。"""
        await store_with_l0.observe("u1", "image", "事实A", 0.9)
        fake_spec = type("Spec", (), {"id": "unknown/fake", "provider": "unknown"})()
        self._patch_registry(monkeypatch, [fake_spec], {})  # 无 "unknown" 前缀 provider
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        result = await store_with_l0.consolidate()
        assert result["L0_to_L1"] == 1  # 回退 mock

    @pytest.mark.asyncio
    async def test_llm_consolidate_exception_falls_back_mock(self, store_with_l0, monkeypatch):
        """LLM 抛异常 → 回退 mock（except 分支）。"""
        await store_with_l0.observe("u1", "image", "事实A", 0.9)

        class _BrokenProvider:
            prefix = "tryingopen"

            async def chat_collect(self, model, messages, **kw):
                raise RuntimeError("LLM 挂了")

        fake_spec = type("Spec", (), {"id": "tryingopen/fake", "provider": "tryingopen"})()
        self._patch_registry(monkeypatch, [fake_spec], {"tryingopen": _BrokenProvider()})
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        result = await store_with_l0.consolidate()
        assert result["L0_to_L1"] == 1  # 回退 mock

    @pytest.mark.asyncio
    async def test_llm_consolidate_empty_l0_returns_zero(self, store_with_l0, monkeypatch):
        """L0 无数据 → LLM 路径返回 0（不调 LLM）。"""
        self._patch_registry(monkeypatch, [], {})
        monkeypatch.setenv("IF_MOCK_UPSTREAM", "0")

        result = await store_with_l0.consolidate()
        assert result["L0_to_L1"] == 0
        assert result["pruned"] == 0
