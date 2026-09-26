"""视频 provider 选择（指南 v18 P1-1）。

v20.3.3 注释修正（终局审计 P2）：**视频当前恒 Mock**（falai 等真实上游已下线/未接入），
IF_MOCK_UPSTREAM 开关对视频路径无效——真实 provider 动作族待新上游接入后替换
（见 docs/architecture-evolution.md 演进建议）。前端 PortalVideo 已正确标注 Beta。"""
from __future__ import annotations


def get_video_provider():
    """返回当前视频 provider 实例。恒 Mock（真实上游未接入，见模块 docstring）。"""
    from .video_mock import mock_video_provider

    return mock_video_provider
