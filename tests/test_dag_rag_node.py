"""tests/test_dag_rag_node.py — v11.0.0 DAG RAG 检索节点（复用 api/vector/）。

覆盖：
- retrieval 节点：检索先行、结果摘要、vector store 异常降级、prompt 为空提示
TDD：RED（本文件先跑应失败）→ GREEN（实现 api/routes/agent_dag_exec._exec_retrieval）→ 回归。
付费红线：embed 用本地 SimHash（api/vector/embed）零依赖，不触碰任何真实付费上游。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from api.routes.agent_dag_exec import _exec_retrieval, execute_node


class TestRagRetrievalNode:
    async def test_retrieval_returns_summary(self):
        """retrieval 节点执行 → 返回检索摘要（含最相似任务）。"""
        fake = AsyncMock()
        fake.find_duplicate.return_value = {
            "task_id": "t1", "similarity": 0.91, "prompt_hash": "h1", "is_duplicate": False,
        }
        with patch("api.vector.store.get_vector_store", return_value=fake) as m:
            out = await _exec_retrieval("画一只猫")
            m.assert_called_once()
        assert "t1" in out
        assert "0.91" in out
        assert "检索" in out

    async def test_retrieval_through_execute_node(self):
        """经 execute_node 分发：kind=retrieval 命中检索分支。"""
        fake = AsyncMock()
        fake.find_duplicate.return_value = {
            "task_id": "t9", "similarity": 0.99, "prompt_hash": "h", "is_duplicate": False,
        }
        with patch("api.vector.store.get_vector_store", return_value=fake):
            out = await execute_node("r1", {"node": {"kind": "retrieval", "prompt": "查询素材"}})
        assert isinstance(out, str)
        assert "t9" in out

    async def test_retrieval_vector_store_unavailable(self):
        """vector store 不可用/异常 → 降级返回提示，不崩。"""
        with patch("api.vector.store.get_vector_store", side_effect=RuntimeError("no vec")):
            out = await _exec_retrieval("x")
        assert "降级" in out

    async def test_retrieval_empty_result(self):
        """检索无结果 → 返回「未找到相似素材」。"""
        fake = AsyncMock()
        fake.find_duplicate.return_value = None
        with patch("api.vector.store.get_vector_store", return_value=fake):
            out = await _exec_retrieval("全新主题")
        assert "未找到" in out

    async def test_retrieval_prompt_required(self):
        """prompt 缺失 → 返回提示（不抛异常）。"""
        out = await _exec_retrieval("")
        assert isinstance(out, str)
        assert "关键词" in out


class TestChatRagContext:
    async def test_rag_prefix_in_system_prompt(self):
        """IF_RAG_ENABLED=1 时 chat 在 system 前注入检索上下文。"""
        import api.routes.chat as chat_mod

        fake = AsyncMock()
        fake.find_duplicate.return_value = {
            "task_id": "k1", "similarity": 0.9, "prompt_hash": "h", "is_duplicate": False,
        }

        from api.config import reset_settings

        reset_settings()  # autouse 已重置，显式再确认干净
        with patch.object(chat_mod, "_rag_flag_override", True), patch(
            "api.vector.store.get_vector_store", return_value=fake
        ):
            prefix = await chat_mod._rag_prefix_if_enabled("画猫")
        assert isinstance(prefix, str)
        assert "k1" in prefix
        assert "检索" in prefix
        reset_settings()

    async def test_rag_disabled_returns_empty(self):
        """IF_RAG_ENABLED=0（默认）→ 空前缀，零行为变化。"""
        import api.routes.chat as chat_mod
        from api.config import reset_settings

        reset_settings()
        out = await chat_mod._rag_prefix_if_enabled("x")
        assert out == ""
