"""教学化 explain 模板测试（指南 B3 / P0-3）。纯本地。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.agent.dag import VALID_KINDS  # noqa: E402
from api.agent.explain_templates import (  # noqa: E402
    NODE_EXPLAIN,
    build_node_explain,
    scene_explain,
)


def test_all_dag_kinds_have_explain():
    assert len(VALID_KINDS) == 8
    missing = VALID_KINDS - set(NODE_EXPLAIN)
    assert not missing, f"缺释义: {missing}"


def test_build_node_explain_contains_why():
    text = build_node_explain("critic")
    assert "为什么" in text and "critic" in text and "输入输出" in text


def test_build_node_explain_includes_node_context():
    text = build_node_explain("llm", {"prompt": "写一段产品介绍"})
    assert "写一段产品介绍" in text


def test_unknown_kind_fallback():
    text = build_node_explain("bogus-kind")
    assert "通用处理节点" in text


def test_scene_explain_covers_known_scenes():
    assert "图片生成" in scene_explain("image")
    assert "PPT" in scene_explain("ppt")
    assert "电商" in scene_explain("ecommerce")
    assert "通用" in scene_explain("unknown")
    assert "通用" in scene_explain("no-such-scene")


def test_explain_templates_static_no_llm():
    # 模板为纯静态 dict（RT-2：先模板后教学层，零 LLM 依赖）
    assert isinstance(NODE_EXPLAIN, dict)
    assert len(NODE_EXPLAIN) == 8
