"""tryingopen 包拆分兼容性测试（P0-6）。

目的：把 `api/providers/tryingopen.py`（810 行）转为 `api/providers/tryingopen/` 包
（`__init__.py` 保留 `TryingopenChatProvider` 类 + 模块级 `proxy_pool`/`asyncio`/`config`
绑定以保 monkeypatch 语义；`_helpers.py` 提取纯辅助/常量/dataclass/异常）后，
全部旧 import 路径与模块级属性仍可用。

为何类留在 `__init__.py`：tests/test_tryingopen.py 用
`monkeypatch.setattr(tryingopen, "proxy_pool", FakePool())`，chat_stream 内
`proxy_pool.acquire` 必须经 `tryingopen` 模块 globals 解析才能被 monkeypatch 命中；
若类搬到 `provider.py`，`proxy_pool` 绑定在 `provider` 模块，monkeypatch 失效。
"""

from __future__ import annotations

import api.providers.tryingopen as legacy
from api.providers import tryingopen
from api.providers.tryingopen import (
    _FALLBACK_CATALOG,
    TryingopenChatProvider,
    _AttemptResult,
    _last_json_object,
    _parse_plaintext_tool_calls,
    _TryingopenRateLimited,
)


def test_public_class_constructible_with_fallback_catalog():
    provider = TryingopenChatProvider()
    assert provider.prefix == "tryingopen"
    assert provider.base_url == "https://www.tryingopen.com"
    # 回退目录至少 13 个模型（kimi-k3 含 messageLimit/cheaperFallbackId）
    assert len(provider.models) >= 13
    kimi = provider.models["tryingopen/moonshotai/kimi-k3"]
    assert kimi.meta["messageLimit"] == 5
    assert kimi.meta["cheaperFallbackId"] == "minimax/minimax-m3"


def test_legacy_module_attributes_preserved():
    # 测试 monkeypatch 命中的模块级绑定必须仍在 tryingopen 命名空间
    assert hasattr(legacy, "proxy_pool")
    assert hasattr(legacy, "asyncio")
    assert hasattr(legacy, "config")
    # 辅助符号 re-export 一致
    assert legacy._AttemptResult is _AttemptResult
    assert legacy._TryingopenRateLimited is _TryingopenRateLimited
    assert legacy._parse_plaintext_tool_calls is _parse_plaintext_tool_calls
    assert legacy._last_json_object is _last_json_object
    assert legacy._FALLBACK_CATALOG is _FALLBACK_CATALOG


def test_helpers_callable():
    calls = _parse_plaintext_tool_calls('{"tool_call":{"name":"f","arguments":{"q": 1}}}')
    assert calls == [{"name": "f", "arguments": '{"q":1}'}]
    assert _AttemptResult(text="hi").text == "hi"
    exc = _TryingopenRateLimited("limited")
    assert exc.message == "limited"


def test_package_module_identity():
    # import 路径三种形式都解析到同一模块对象
    import api.providers.tryingopen as t1
    from api.providers import tryingopen as t2
    assert t1 is t2 is legacy is tryingopen
