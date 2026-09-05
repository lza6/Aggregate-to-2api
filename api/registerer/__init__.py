"""自动注册器与自适应注册工作流 (Adaptive Registration Worker)。

P0-5（v8.0）：将原 `api/registerer.py`（864 行）拆分为 `api/registerer/` 包：
- `types.py`：RegistrationStage / RegistrationErrorCategory / RegistrationError /
  RegistrationSession / AdaptiveRegistrationBackoff + 单例 adaptive_backoff + MOCK_REGISTER + STAGE_LABELS + _parse_iso_ts
- `utils.py`：_browser_headers / _th / _extract_code / _extract_verify_link /
  _proxy_host / _ip_to_proxy / _mail_ai_extract_enabled / _gen_password / _session_data_from_cookies
- `cf_solve.py`：cf_solver / turnstile_client / solver_guard re-export
- `email_verify.py`：邮箱验证码/链接提取 re-export
- `flow.py`：NanobananaRegisterer + build_registerers

向后兼容：本包 `__init__.py` re-export 全部公共符号，`from api.registerer import X`
等旧 import 路径仍可用。`api/registerer.py` 旧文件改为兼容垫片
（`from .registerer import *`），不破坏现有调用方。
"""

from __future__ import annotations

from .. import config  # noqa: F401  (re-export 供测试 monkeypatch `api.registerer.config.PROXY` 等旧路径)
from .cf_solve import solver_guard, turnstile_client
from .flow import NanobananaRegisterer, build_registerers
from .types import (
    MOCK_REGISTER,
    STAGE_LABELS,
    AdaptiveRegistrationBackoff,
    RegistrationError,
    RegistrationErrorCategory,
    RegistrationSession,
    RegistrationStage,
    _parse_iso_ts,
    adaptive_backoff,
)
from .utils import (
    _browser_headers,
    _extract_code,
    _extract_verify_link,
    _gen_password,
    _ip_to_proxy,
    _mail_ai_extract_enabled,
    _proxy_host,
    _session_data_from_cookies,
    _th,
)

__all__ = [
    "MOCK_REGISTER",
    "STAGE_LABELS",
    "AdaptiveRegistrationBackoff",
    "NanobananaRegisterer",
    "RegistrationError",
    "RegistrationErrorCategory",
    "RegistrationSession",
    "RegistrationStage",
    "_browser_headers",
    "_extract_code",
    "_extract_verify_link",
    "_gen_password",
    "_ip_to_proxy",
    "_mail_ai_extract_enabled",
    "_parse_iso_ts",
    "_proxy_host",
    "_session_data_from_cookies",
    "_th",
    "adaptive_backoff",
    "build_registerers",
    "solver_guard",
    "turnstile_client",
]
