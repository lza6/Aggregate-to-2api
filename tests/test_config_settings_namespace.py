"""api/config/settings.py 兼容命名空间契约测试（P0-2 覆盖率补强）。

settings.py 是纯 re-export 模块（`from api.config.settings import X` 兼容层），
import 期即执行全部 re-export。本文件验证：
1. 模块可导入且 __all__ 完整生成；
2. 关键符号（Settings / settings / DB_FILE / apply_model 等）与 api.config 同一对象；
3. `from api.config.settings import Settings` 兼容路径可用。
"""

from __future__ import annotations

import api.config.settings as ns
import api.config as root


def test_settings_namespace_importable():
    assert ns.__all__  # __all__ 非空


def test_settings_reexport_same_objects():
    """类/常量 re-export 必须与 api.config 同一对象（防双版本分叉）。

    注意 settings 单例不做同一性断言：conftest autouse 钩子会在每用例前后
    reset_settings() 重建单例，两个模块各自 import 时机不同会拿到不同实例（预期）。
    """
    assert ns.Settings is root.Settings
    assert isinstance(ns.settings, root.Settings)
    assert ns.DB_FILE == root.DB_FILE
    assert ns.BASE_URL == root.BASE_URL
    assert ns.TOKEN_POOL_SIZE == root.TOKEN_POOL_SIZE
    assert ns.apply_model is root.apply_model
    assert ns.DBSettings is root.DBSettings
    assert ns.SecuritySettings is root.SecuritySettings


def test_from_settings_import_path():
    """兼容路径 `from api.config.settings import X` 可用。"""
    from api.config.settings import Settings, settings as s, DB_FILE

    assert Settings is root.Settings
    assert isinstance(s, root.Settings)  # 单例同一性受 reset 钩子影响，只验类型
    assert DB_FILE == root.DB_FILE
