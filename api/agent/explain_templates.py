"""DAG 节点教学化释义模板（指南 B3 / P0-3，learn-agent + CowAgent 对标）。

把 8 类节点转成面向小白的「为什么这样规划」大白话（RT-2：先模板释义，后完整教学层）。
- NODE_EXPLAIN：kind → 释义 dict（what/why/io）
- build_node_explain(kind, node_config=None)：返回单节点释义字符串（模板 + 节点级上下文）
- SCENE_EXPLAIN：场景释义（image/chat/video/ecommerce/ppt/unknown）

纯静态模板，零 LLM 依赖（IF_AGENT_EXPLAIN_LLM=0 时用模板；LLM 增强后置）。
"""
from __future__ import annotations

from typing import Any

NODE_EXPLAIN: dict[str, dict[str, str]] = {
    "scene": {
        "what": "任务入口节点：判断用户想干什么（生图/对话/视频/电商/PPT）。",
        "why": "先把意图搞清楚，后面每一步才知道往哪走。",
        "io": "输入：用户的一句话需求；输出：识别出的场景标签。",
    },
    "llm": {
        "what": "大模型处理节点：让 AI 根据提示词做一次思考/生成。",
        "why": "把上一步的结果交给大模型加工，是 DAG 里最常见的加工单元。",
        "io": "输入：提示词 + 上游结果；输出：模型回复文本。",
    },
    "critic": {
        "what": "终检节点：在交付前用干净上下文审查产物质量（内容/尺寸/水印/安全）。",
        "why": "避免坏结果直接交付——先自检一遍，不行就重做或降级。",
        "io": "输入：产物地址 + 质量要求；输出：pass/score/recommendation。",
    },
    "tool": {
        "what": "工具调用节点：执行一个具体工具（如生图/检索/本地命令，受预算与安全门禁保护）。",
        "why": "让 AI 不只是说话，而是真正调用能力完成任务。",
        "io": "输入：工具名 + 参数；输出：工具执行结果。",
    },
    "memory": {
        "what": "记忆节点：读取或写入用户长期偏好（L0-L3 分层记忆）。",
        "why": "记住你的偏好，下次不用重新说。",
        "io": "输入：op(write/read) + scene；输出：记忆内容或确认。",
    },
    "retrieval": {
        "what": "检索节点：从知识库/记忆里召回相关内容（RAG）。",
        "why": "回答前先查资料，答案更有依据。",
        "io": "输入：查询词；输出：召回片段。",
    },
    "image": {
        "what": "多模态图像节点：基于提示词或参考图生成/编辑图片（受 Mock 红线与预算门禁）。",
        "why": "图像类任务的核心执行单元。",
        "io": "输入：prompt + 参考图；输出：图片任务结果。",
    },
    "human_input": {
        "what": "人机审批节点：需要你确认后才继续（如高影响操作、花钱调用）。",
        "why": "把关键决策交还给你，AI 不擅自做高风险动作。",
        "io": "输入：待审批事项；输出：你的批准/拒绝。",
    },
}

SCENE_EXPLAIN: dict[str, str] = {
    "image": "图片生成：根据描述生成或编辑图片。",
    "image_edit": "图片编辑：基于参考图做修改。",
    "video": "视频生成：描述 → 视频（视频上游 Mock 优先）。",
    "chat": "对话问答：多模型对话与工具调用。",
    "ecommerce": "电商视觉：主图/详情页策划 + 合规护栏。",
    "ppt": "PPT 大纲：一句话需求 → 结构化演示文稿大纲。",
    "unknown": "通用任务：交给模型自行规划。",
}


def build_node_explain(kind: str, node_config: dict[str, Any] | None = None) -> str:
    """构造单节点释义（模板 + 节点级上下文，纯 Python）。未知类型回退通用说明。"""
    tmpl = NODE_EXPLAIN.get(kind)
    if tmpl is None:
        return f"节点类型 {kind}：通用处理节点，按配置执行。"
    parts = [
        f"[{kind}] {tmpl['what']}",
        f"为什么：{tmpl['why']}",
        f"输入输出：{tmpl['io']}",
    ]
    if node_config:
        prompt = node_config.get("prompt") or node_config.get("scene")
        if prompt:
            parts.append(f"本节点要点：{str(prompt)[:80]}")
    return "\n".join(parts)


def scene_explain(scene: str) -> str:
    """场景释义（未知回退通用）。"""
    return SCENE_EXPLAIN.get(scene, SCENE_EXPLAIN["unknown"])
