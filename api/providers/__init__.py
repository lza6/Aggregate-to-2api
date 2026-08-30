"""__init__：providers 包。"""

from .base import (
    CAP_IMG2IMG,
    CAP_IMG2VID,
    CAP_TXT2IMG,
    CAP_TXT2VID,
    GenerationResult,
    ModelSpec,
    Provider,
    ProviderError,
    ProviderRateLimited,
)
from .registry import registry  # 单例实例（勿用 `from . import registry`，那会绑到子模块）

__all__ = [
    "CAP_IMG2IMG",
    "CAP_IMG2VID",
    "CAP_TXT2IMG",
    "CAP_TXT2VID",
    "GenerationResult",
    "ModelSpec",
    "Provider",
    "ProviderError",
    "ProviderRateLimited",
    "registry",
]
