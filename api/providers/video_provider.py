"""视频 provider 选择（指南 v18 P1-1）：IF_MOCK_UPSTREAM=1（默认/测试）→ Mock；真实路径后置。"""
from __future__ import annotations


def get_video_provider():
    """返回当前视频 provider 实例。Mock 优先（付费红线）；真实 falai 动作族后置。"""
    from .video_mock import mock_video_provider

    return mock_video_provider
