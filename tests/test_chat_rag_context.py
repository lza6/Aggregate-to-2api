"""tests/test_chat_rag_context.py — v11.0.0 chat RAG 增强（system 前缀）。

覆盖：IF_RAG_ENABLED=1 时 chat 在 system 前注入向量检索上下文；
IF_RAG_ENABLED=0（默认）→ 零行为变化。Mock vector store，零真实付费。
TDD：RED（本文件先跑应失败）→ GREEN（实现 api/routes/chat._rag_prefix_if_enabled）→ 回归。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import api.routes.chat as chat_mod
from api.config import get_settings, reset_settings


class TestChatRag:
    async def test_disabled_default_empty(self):
        """默认（IF_RAG_ENABLED=0）→ 空前缀，零行为变化。"""
        reset_settings()
        assert await chat_mod._rag_prefix_if_enabled("画一只猫") == ""

    async def test_enabled_injects_context(self):
        """IF_RAG_ENABLED=1 → 检索结果拼成 system 前缀。"""
        fake = AsyncMock()
        fake.find_duplicate.return_value = {
            "task_id": "k1", "similarity": 0.93, "prompt_hash": "h1", "is_duplicate": False,
        }
        with patch.object(chat_mod, "_rag_flag_override", True), patch(
            "api.vector.store.get_vector_store", return_value=fake
        ):
            prefix = await chat_mod._rag_prefix_if_enabled("电商主图")
        assert "k1" in prefix
        assert "检索" in prefix

    async def test_enabled_empty_result_no_crash(self):
        """开启但无结果 → 返回空串，不崩 chat 链路。"""
        fake = AsyncMock()
        fake.find_duplicate.return_value = None
        with patch.object(chat_mod, "_rag_flag_override", True), patch(
            "api.vector.store.get_vector_store", return_value=fake
        ):
            prefix = await chat_mod._rag_prefix_if_enabled("全新主题")
        assert prefix == ""

    async def test_enabled_store_error_degrades(self):
        """vector store 异常 → 降级返回空串（不崩 chat 主链路）。"""
        with patch.object(chat_mod, "_rag_flag_override", True), patch(
            "api.vector.store.get_vector_store", side_effect=RuntimeError("boom")
        ):
            prefix = await chat_mod._rag_prefix_if_enabled("x")
        assert prefix == ""


class TestConfigSwitch:
    def test_dag_requests_per_minute_field(self):
        """v11.0.0：DAG 独立限流字段已入 config 工厂。"""
        assert hasattr(get_settings(), "if_dag_requests_per_minute")
        assert get_settings().if_dag_requests_per_minute == 30
