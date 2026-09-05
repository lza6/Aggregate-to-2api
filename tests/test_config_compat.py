"""P0-2: api/config/__init__.py 拆分兼容性测试。

验证目标：
1. `from api.config import get_settings, reset_settings, HOST, PORT, CF_SOLVER_URL` 等
   全部旧 import 路径仍可用（向后兼容，调用方密集）。
2. `from api.config.presets import apply_model, MODEL_PRESETS, ASPECT_RATIOS,
   MAX_IMAGE_BYTES, MAX_PROMPT_LEN` 新拆分子模块可用，且与 api.config 同一对象
   （防双版本分叉）。
3. `from api.config.settings import ...` 兼容命名空间仍可用（settings.py 角色不变）。
4. get_settings()/reset_settings() 工厂行为不变（conftest autouse 依赖）。
5. Settings 类、模块级常量（settings 单例快照）保持类型一致。
"""

from __future__ import annotations

import api.config as root
import api.config.presets as presets
import api.config.settings as ns


def test_legacy_top_level_imports() -> None:
    """旧 `from api.config import X` 路径全部可用（调用方密集，不得破坏）。"""
    from api.config import (
        BASE_URL,
        CF_SOLVER_URL,
        HOST,
        MAX_IMAGE_BYTES,
        MAX_PROMPT_LEN,
        PORT,
        Settings,
        apply_model,
        config,
        get_settings,
        reset_settings,
    )

    assert Settings is not None
    assert callable(get_settings)
    assert callable(reset_settings)
    assert callable(apply_model)
    assert isinstance(HOST, str)
    assert isinstance(PORT, int)
    assert isinstance(BASE_URL, str)
    assert isinstance(CF_SOLVER_URL, str)
    assert MAX_IMAGE_BYTES == 4 * 1024 * 1024
    assert MAX_PROMPT_LEN == 2000
    assert config is root  # `from api.config import config` → config 指代包模块本身


def test_presets_module_exposes_constants() -> None:
    """P0-2: presets.py 新拆分子模块暴露纯常量与 apply_model。"""
    assert presets.MAX_IMAGE_BYTES == 4 * 1024 * 1024
    assert presets.MAX_PROMPT_LEN == 2000
    assert "1:1" in presets.ASPECT_RATIOS
    assert "default" in presets.MODEL_PRESETS
    assert "anime" in presets.MODEL_PRESETS
    assert callable(presets.apply_model)


def test_presets_reexport_same_objects() -> None:
    """presets 常量与 api.config 同一对象（防双版本分叉）。"""
    assert presets.MAX_IMAGE_BYTES is root.MAX_IMAGE_BYTES
    assert presets.MAX_PROMPT_LEN is root.MAX_PROMPT_LEN
    assert presets.ASPECT_RATIOS is root.ASPECT_RATIOS
    assert presets.MODEL_PRESETS is root.MODEL_PRESETS
    assert presets.apply_model is root.apply_model


def test_namespace_compat_unchanged() -> None:
    """`from api.config.settings import X` 兼容路径仍可用且同一对象。"""
    from api.config.settings import DB_FILE
    from api.config.settings import Settings as NS_Settings
    from api.config.settings import apply_model as ns_apply

    assert NS_Settings is root.Settings
    assert ns_apply is root.apply_model
    assert DB_FILE == root.DB_FILE
    # settings.py __all__ 非空（re-export 层完整生成）
    assert ns.__all__


def test_get_settings_returns_settings_instance() -> None:
    """get_settings() 返回 Settings 实例（工厂行为不变）。"""
    s = get_settings()
    assert isinstance(s, Settings)
    # 顶层字段可读（host/port 是 Settings 字段名）
    assert s.host
    assert 1 <= s.port <= 65535


def test_reset_settings_rebuilds_singleton() -> None:
    """reset_settings() 重建单例不报错（conftest autouse 依赖）。"""
    new = reset_settings()
    assert isinstance(new, Settings)
    # reset 后 get_settings 拿到新实例
    after = get_settings()
    assert isinstance(after, Settings)
    # 模块级 settings 变量同步刷新
    assert isinstance(root.settings, Settings)


def test_apply_model_behavior_preserved() -> None:
    """apply_model 行为不变（dispatch/worker/imagefree 消费）。"""
    assert presets.apply_model("a cat", "default") == "a cat"
    assert presets.apply_model("a cat", "nope") == "a cat"
    out = presets.apply_model("a cat", "anime")
    assert out.startswith("anime style") and out.endswith("a cat")


# 兼容 import（供 test 体引用）
from api.config import Settings, get_settings, reset_settings  # noqa: E402
