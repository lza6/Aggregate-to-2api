"""P-TEST-A1: api/main.py 校验层特征测试。

锁定现有行为（characterization）：
- _validate_model（能力匹配/未知模型/旧版映射/非法 kind）
- _normalize_model（旧版风格 → imagefree/<id>）
- _validate_ratio（格式正反例）
- _parse_input_image（data URI / 坏 base64 / 超大 / URL SSRF 拒绝 / 非法协议）
- _parse_input_images（>3 拒绝 / 非 data URI / 坏 base64 / 超大）
- _uptime_human（秒/分钟/小时/天）
"""
import base64
import os
import sys
import tempfile

import pytest

# 与既有测试（test_edit_proxy_inflight.py）同款隔离导入：临时 DB + 关号池
_tmp_db = tempfile.mktemp(suffix=".db")
os.environ["IF_DB_FILE"] = _tmp_db
os.environ["IF_ACCOUNT_AUTO"] = "0"
os.environ["IF_MOCK_REGISTER"] = "1"

from api.errors import AppError  # noqa: E402
from api.dispatch import (  # noqa: E402
    _normalize_model,
    _parse_input_image,
    _parse_input_images,
    _validate_model,
    _validate_ratio,
)
from api.meta import _uptime_human


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class TestNormalizeModel:
    def test_default_maps_to_imagefree(self):
        assert _normalize_model("default") == "imagefree/default"

    def test_empty_maps_to_imagefree_default(self):
        assert _normalize_model("") == "imagefree/default"

    def test_none_maps_to_imagefree_default(self):
        assert _normalize_model(None) == "imagefree/default"

    def test_prefixed_passthrough(self):
        assert _normalize_model("nanobanana/nano-banana-pro") == "nanobanana/nano-banana-pro"


class TestValidateModel:
    def test_known_model_ok(self):
        _validate_model("imagefree/default")  # 不抛即过
        _validate_model("default", "txt2img")  # 旧版风格映射

    def test_unknown_model_422(self):
        with pytest.raises(AppError) as ei:
            _validate_model("imagefree/no-such-model")
        assert ei.value.status_code == 422

    def test_capability_mismatch_422(self):
        # imagefree/anime 只有 txt2img 能力 → img2img 请求能力不匹配
        with pytest.raises(AppError) as ei:
            _validate_model("imagefree/anime", "img2img")
        assert ei.value.status_code == 422
        assert "不支持" in ei.value.message

    def test_invalid_kind_422(self):
        with pytest.raises(AppError) as ei:
            _validate_model("imagefree/default", "nosuch")
        assert ei.value.status_code == 422


class TestValidateRatio:
    @pytest.mark.parametrize("ok", ["1:1", "16:9", "9:16", "4:3", "100:100"])
    def test_valid(self, ok):
        _validate_ratio(ok)

    @pytest.mark.parametrize("bad", ["11", "1:", ":1", "a:b", "1:1:1", " 1:1", "1 :1", "-1:1"])
    def test_invalid_422(self, bad):
        with pytest.raises(AppError) as ei:
            _validate_ratio(bad)
        assert ei.value.status_code == 422


class TestParseInputImage:
    def test_data_uri_ok(self):
        data, ctype = _parse_input_image(f"data:image/png;base64,{_b64(PNG_1PX)}")
        assert data == PNG_1PX
        assert ctype == "image/png"

    def test_bad_data_uri_format_422(self):
        with pytest.raises(AppError) as ei:
            _parse_input_image("data:image/png,notbase64")
        assert ei.value.status_code == 422

    def test_bad_base64_422(self):
        # Python b64decode 默认宽松（忽略非法字符），构造真正抛异常的输入：
        # 正确 padding 声明但内容长度非法
        with pytest.raises(AppError) as ei:
            _parse_input_image("data:image/png;base64,AAB")  # 错误 padding 长度 → binascii.Error
        assert ei.value.status_code == 422

    def test_oversize_413(self):
        from api import config
        big = b"x" * (config.MAX_IMAGE_BYTES + 1)
        with pytest.raises(AppError) as ei:
            _parse_input_image(f"data:image/png;base64,{_b64(big)}")
        assert ei.value.status_code == 413

    def test_url_passthrough(self):
        # 公网域名解析非私网 → (None, url) 交由端点下载
        data, url = _parse_input_image("https://imagefree.net/a.png")
        assert data is None
        assert url == "https://imagefree.net/a.png"

    def test_private_ip_ssrf_rejected(self):
        # 用字面 IPv4 主机（无需 DNS）：私网/回环/链路本地一律拒绝
        for u in ("http://127.0.0.1/x.png", "http://10.0.0.1/x.png",
                  "http://192.168.1.1/x.png", "http://172.16.0.1/x.png",
                  "http://169.254.1.1/x.png"):
            with pytest.raises(AppError) as ei:
                _parse_input_image(u)
            assert ei.value.status_code in (400, 422)

    def test_no_host_422(self):
        with pytest.raises(AppError):
            _parse_input_image("http:///x.png")

    def test_other_scheme_422(self):
        with pytest.raises(AppError) as ei:
            _parse_input_image("ftp://example.com/a.png")
        assert ei.value.status_code == 422


class TestParseInputImages:
    def _uri(self, data: bytes = PNG_1PX) -> str:
        return f"data:image/png;base64,{_b64(data)}"

    def test_empty_ok(self):
        assert _parse_input_images([]) == []

    def test_single_ok(self):
        out = _parse_input_images([self._uri()])
        assert out == [PNG_1PX]

    def test_three_ok(self):
        out = _parse_input_images([self._uri()] * 3)
        assert len(out) == 3

    def test_over_three_422(self):
        with pytest.raises(AppError) as ei:
            _parse_input_images([self._uri()] * 4)
        assert ei.value.status_code == 422

    def test_not_data_uri_422(self):
        with pytest.raises(AppError) as ei:
            _parse_input_images(["https://example.com/a.png"])
        assert ei.value.status_code == 422

    def test_bad_uri_format_422(self):
        with pytest.raises(AppError) as ei:
            _parse_input_images(["data:image/png,raw"])
        assert ei.value.status_code == 422

    def test_bad_base64_422(self):
        # Python b64decode 宽松模式对 !!! 不抛异常；用错误 padding 长度构造真实异常
        with pytest.raises(AppError) as ei:
            _parse_input_images(["data:image/png;base64,AAB"])
        assert ei.value.status_code == 422

    def test_oversize_413(self):
        from api import config
        big = b"x" * (config.MAX_IMAGE_BYTES + 1)
        with pytest.raises(AppError) as ei:
            _parse_input_images([f"data:image/png;base64,{_b64(big)}"])
        assert ei.value.status_code == 413


class TestUptimeHuman:
    def test_seconds(self):
        assert _uptime_human(59) == "59秒"

    def test_minutes(self):
        assert _uptime_human(60) == "1分钟"
        assert _uptime_human(3599) == "59分钟"

    def test_hours(self):
        assert _uptime_human(3600) == "1小时0分钟"
        assert _uptime_human(7260) == "2小时1分钟"

    def test_days(self):
        assert _uptime_human(86400) == "1天0小时"
        assert _uptime_human(90000) == "1天1小时"


class TestRequestBodyLimit:
    """P0-安全：请求体总量上限（starlette 1.6 RequestBodyLimitMiddleware，8MB 默认）。

    大 base64 正文在到达「4MB/张」判断前即应被 413 拒绝，防止占满内存。
    未挂中间件的纯解析函数不受影响（_parse_input_images 仍按 3 张与 MAX_IMAGE_BYTES 判）。
    """
    def test_oversized_request_body_413(self):
        import api.main as m
        from fastapi.testclient import TestClient
        c = TestClient(m.app, raise_server_exceptions=False)
        big = b"x" * (9 * 1024 * 1024)
        r = c.post("/v1/generate", content=big, headers={"Content-Type": "application/json"})
        assert r.status_code == 413

    def test_small_body_passes_guard(self):
        import api.main as m
        from fastapi.testclient import TestClient
        c = TestClient(m.app, raise_server_exceptions=False)
        r = c.post("/v1/generate", json={"prompt": "t", "aspect_ratio": "1:1"})
        # 校验层（isolation）未挂载真实鉴权时，可能 401/422/200，但绝不应 413
        assert r.status_code != 413
