"""注册器注册表。

nanobanana 已下线，当前没有自动注册的图片提供商。
号池循环仍可被测试按 provider 名直接调用，但启动时不再挂任何签到型上游。
"""

from __future__ import annotations


def build_registerers() -> dict[str, object]:
    """返回空注册表。tryingopen 是匿名聊天上游，不走号池注册。"""
    return {}


__all__ = ["build_registerers"]
