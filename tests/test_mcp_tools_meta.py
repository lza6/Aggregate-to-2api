# -*- coding: utf-8 -*-
"""MCP 渐进工具暴露测试（指南 P1-7，smart-mcp-proxy 对标）。

覆盖：intent 元数据、annotations 完整映射、retrieve_tools 关键词过滤、
describe_tool 详情、tools/list 契约兼容（annotations 新增字段不破坏旧客户端）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.mcp.tools import (  # noqa: E402
    build_tools,
    describe_tool,
    retrieve_tools,
    tool_annotations,
)


def test_all_tools_have_valid_intent():
    tools = build_tools()
    assert len(tools) >= 5
    for t in tools:
        assert t.intent in ("read", "write", "destructive")
        assert t.expose is True  # 现有 6 工具全部对老客户端可见（渐进暴露后置）


def test_read_tools_marked_read():
    tools = {t.name: t for t in build_tools()}
    assert tools["skills_list"].intent == "read"
    assert tools["skills_get"].intent == "read"
    assert tools["dag_status"].intent == "read"
    assert tools["task_status"].intent == "read"


def test_write_tools_marked_write():
    tools = {t.name: t for t in build_tools()}
    assert tools["generate_image"].intent == "write"
    assert tools["dag_plan"].intent == "write"
    assert tools["generate_image"].read_only is False


def test_annotations_mapping():
    tools = {t.name: t for t in build_tools()}
    a_read = tool_annotations(tools["skills_list"])
    assert a_read["readOnlyHint"] is True
    assert a_read["destructiveHint"] is False
    assert a_read["idempotentHint"] is True
    assert "openWorldHint" in a_read
    a_write = tool_annotations(tools["generate_image"])
    assert a_write["readOnlyHint"] is False
    assert a_write["destructiveHint"] is False
    assert a_write["idempotentHint"] is False


def test_retrieve_tools_keyword_filter():
    tools = build_tools()
    hits = retrieve_tools(tools, "image")
    names = [t.name for t in hits]
    assert "generate_image" in names
    no_hits = retrieve_tools(tools, "zzz-no-match-xyz")
    assert no_hits == []


def test_retrieve_tools_empty_query_returns_all_exposed():
    tools = build_tools()
    assert len(retrieve_tools(tools, "")) == len(tools)


def test_describe_tool_returns_detail():
    tools = build_tools()
    d = describe_tool(tools, "skills_get")
    assert d is not None
    assert d["name"] == "skills_get"
    assert d["intent"] == "read"
    assert set(d["annotations"]) >= {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
    assert d["inputSchema"]["required"] == ["name"]
    assert describe_tool(tools, "no-such-tool") is None


def test_expose_flag_filters_retrieve():
    from api.mcp.tools import McpTool

    async def _noop(_a):
        return None

    hidden = McpTool(name="hidden-tool", description="待审批工具", input_schema={}, handler=_noop, expose=False)
    tools = build_tools() + [hidden]
    assert len(retrieve_tools(tools, "hidden")) == 0
    assert len(retrieve_tools(tools, "hidden", include_hidden=True)) == 1


def test_tools_list_contract_annotations_compat():
    """tools/list 响应 annotations 含（readOnlyHint 等）且不影响现有工具只读契约。"""
    from api.mcp.tools import find_tool

    tools = build_tools()
    assert find_tool(tools, "generate_image").read_only is False
    for t in tools:
        ann = tool_annotations(t)
        assert isinstance(ann["readOnlyHint"], bool)