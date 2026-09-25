"""nanobanana 注册器下线后，注册表必须为空。"""

from api.registerer import build_registerers


def test_build_registerers_empty():
    assert build_registerers() == {}
