"""tests/test_dag_memory_chain.py — v13 P0-5 DAG 记忆节点读写链测试。

覆盖：
- _exec_memory op=write → memory=stored，随后 MemoryStore.query 可查到该内容
- _exec_memory op=read 无记忆 → memory=none；先 write 再 read → memory=read(1条, ...) + 内容片段
- execute_node 分发：config 子键 op=read/scene=image 走 read 分支；op 缺省 write
- info 子键等价传递（node_raw 支持 config/info）
- 异常注入：memory_store.observe 抛错 → memory=error: 不崩

付费红线：全程 Mock（临时 DB + 替换内存 store 单例），不触碰真实付费上游。
"""

from __future__ import annotations

import pytest

from api.routes.agent_dag_exec import _exec_memory, execute_node


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    """临时 DB 的 MemoryStore，并替换模块级单例。

    关键：_exec_memory 函数内 `from ..agent.memory import memory_store`
    在调用时读模块属性 → monkeypatch 模块级单例即可注入隔离 store。
    """
    import api.agent.memory as mem_mod
    from api.agent.memory import MemoryStore

    store = MemoryStore(str(tmp_path / "dag_mem_chain.db"))
    monkeypatch.setattr(mem_mod, "memory_store", store)
    return store


async def test_write_then_query_finds_content(fresh_store):
    """op=write → memory=stored；随后 query L0 能查到该内容。"""
    out = await _exec_memory("记住用户偏好暗黑风配色", op="write")
    assert out == "memory=stored"
    recs = await fresh_store.query("default", "dag", layer="L0", limit=10)
    assert len(recs) == 1
    assert "暗黑风配色" in recs[0].content


async def test_read_without_memory_returns_none(fresh_store):
    """op=read 无记忆 → memory=none。"""
    out = await _exec_memory("任意查询", op="read", scene="image")
    assert out == "memory=none"


async def test_write_then_read_returns_memory(fresh_store):
    """先 write 再 read → memory=read(1条, ...) 且含内容片段。"""
    await _exec_memory("记住关键事实：电商主图用暖色调", op="write", scene="image")
    out = await _exec_memory("查询记忆", op="read", scene="image")
    assert "memory=read(1条" in out
    assert "电商主图用暖色调" in out


async def test_execute_node_read_with_config(fresh_store):
    """execute_node 分发：config 子键 op=read/scene=image → 走 read 分支且 scene=image。"""
    await fresh_store.observe("default", "image", "用户偏好暗黑风", 0.8)
    out = await execute_node(
        "n1", {"node": {"kind": "memory", "prompt": "", "config": {"op": "read", "scene": "image"}}}
    )
    assert out.startswith("memory=read")
    assert "scene=image" in out
    assert "暗黑风" in out


async def test_execute_node_memory_op_defaults_write(fresh_store):
    """execute_node 分发：config 缺省 op → 默认 write。"""
    out = await execute_node("n1", {"node": {"kind": "memory", "prompt": "记住默认写场景"}})
    assert out == "memory=stored"
    recs = await fresh_store.query("default", "dag", layer="L0", limit=10)
    assert len(recs) == 1
    assert "记住默认写场景" in recs[0].content


async def test_execute_node_memory_info_subkey(fresh_store):
    """execute_node 分发：info 子键等价传递 op/scene（node_raw 支持 config/info）。"""
    out = await execute_node("n2", {"node": {"kind": "memory", "prompt": "", "info": {"op": "read", "scene": "video"}}})
    assert out == "memory=none"  # read 分支命中且 scene=video 无数据


async def test_memory_write_error_falls_back(fresh_store, monkeypatch):
    """异常注入：memory_store.observe 抛错 → memory=error: 不崩。"""

    async def _boom(*args, **kwargs):
        raise RuntimeError("observe 爆炸")

    monkeypatch.setattr(fresh_store, "observe", _boom)
    out = await _exec_memory("会失败的写入", op="write")
    assert out.startswith("memory=error:")
    assert "observe 爆炸" in out
