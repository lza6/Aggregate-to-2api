"""api/geo_ip.py 单元测试（P0-2 覆盖率补强，无真实网络）。

覆盖：
- guess_country：空 IP / 本地回环 / 私网段 / 缓存命中 / 在线 API 成功（mock）/ 在线异常 → 离线特征库 / 哈希兜底。
- format_proxy_protocols：多协议链接生成（socks5/ss/vmess/clash/import scheme）。
- generate_subscription_text：base64/raw/clash 三格式 + 损坏 proxy 跳过。
- lookup_ip_detail：等价 guess_country。
- _query_ip_api_online：成功/失败分支（mock urllib）。
- _GEO_CACHE 上限约束。
"""

from __future__ import annotations

import base64
import json
import urllib.request

import pytest

import api.geo_ip as geo


@pytest.fixture(autouse=True)
def _clear_cache():
    geo._GEO_CACHE.clear()
    yield
    geo._GEO_CACHE.clear()


# ── guess_country：本地段 / 空 ────────────────────────────────


def test_guess_country_empty():
    r = geo.guess_country("")
    assert r == {"code": "UNKNOWN", "name": "未知", "desc": "未知地址", "emoji": "🌐"}


def test_guess_country_localhost():
    for ip in ("127.0.0.1", "localhost", "::1"):
        r = geo.guess_country(ip)
        assert r["code"] == "LAN" and r["name"] == "本地回环"


@pytest.mark.parametrize("ip", ["10.1.2.3", "192.168.1.1", "172.16.0.1", "172.31.255.255", "169.254.1.1"])
def test_guess_country_private_ranges(ip):
    r = geo.guess_country(ip)
    assert r["code"] == "LAN" and r["name"] == "局域网"


def test_guess_country_cache_hit():
    geo._GEO_CACHE["1.2.3.4"] = {"code": "XX", "name": "Cached", "desc": "c", "emoji": "❓"}
    assert geo.guess_country("1.2.3.4")["name"] == "Cached"


# ── guess_country：在线 API 成功（mock urllib）──────────────


def test_guess_country_online_success(monkeypatch):
    payload = {
        "status": "success",
        "country": "日本",
        "countryCode": "JP",
        "regionName": "Tokyo",
        "city": "Shinjuku",
        "isp": "Amazon",
    }

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        assert "ip-api.com" in req.full_url
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    r = geo.guess_country("8.8.8.8")
    assert r["code"] == "JP"
    assert "日本" in r["desc"]
    assert "Tokyo" in r["desc"]
    assert "Amazon" in r["desc"]
    # 写入缓存
    assert geo._GEO_CACHE.get("8.8.8.8") == r


def test_guess_country_online_failure_falls_back_offline(monkeypatch):
    """在线 API 抛异常 → 离线特征库兜底（命中前缀）。"""

    def fake_urlopen(*a, **kw):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    r = geo.guess_country("34.1.2.3")  # 34. = Google Cloud US
    assert r["code"] == "US"
    assert "Google Cloud" in r["desc"]


def test_guess_country_online_non_success_status(monkeypatch):
    payload = {"status": "fail", "message": "bogon"}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
    r = geo.guess_country("153.1.2.3")  # 联通前缀，在线 fail → 离线
    assert r["code"] == "CN"


def test_guess_country_hash_fallback_for_unknown_prefix(monkeypatch):
    """在线失败 + 离线特征库无匹配 → 哈希分段兜底。"""

    def fake_urlopen(*a, **kw):
        raise OSError("down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    r = geo.guess_country("99.99.99.99")  # 无前缀匹配
    assert r["code"] in ("US", "JP", "HK", "SG", "KR", "DE", "GB", "FR", "CA", "AU", "NL")


def test_geo_cache_limit_enforced(monkeypatch):
    """缓存达上限时不写入（防内存膨胀）。"""

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"status": "success", "country": "X", "countryCode": "US"}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
    geo._GEO_CACHE.clear()
    # 灌满缓存到上限
    for i in range(geo._GEO_CACHE_LIMIT):
        geo._GEO_CACHE[f"10.{i}.0.0"] = {"code": "LAN"}
    r = geo.guess_country("8.8.4.4")
    assert r["code"] == "US"  # 结果正确返回
    assert "8.8.4.4" not in geo._GEO_CACHE  # 但未写入（达上限）


# ── lookup_ip_detail 等价 guess_country ──────────────────────


def test_lookup_ip_detail_equivalent():
    r = geo.lookup_ip_detail("127.0.0.1")
    assert r["code"] == "LAN"


# ── format_proxy_protocols ────────────────────────────────────


def test_format_proxy_protocols_structure():
    info = {"name": "日本", "emoji": "🇯🇵", "code": "JP"}
    out = geo.format_proxy_protocols("raw://u:p@1.2.3.4:8080", "1.2.3.4", 8080, info, latency_ms=120)
    assert out["ip"] == "1.2.3.4"
    assert out["port"] == 8080
    assert out["country"] == "日本"
    assert out["country_code"] == "JP"
    assert out["country_emoji"] == "🇯🇵"
    assert out["latency_ms"] == 120
    assert out["socks5_link"].startswith("socks5://1.2.3.4:8080#")
    assert out["vmess_link"].startswith("vmess://")
    assert out["ss_link"].startswith("ss://")
    assert out["clash_proxy"]["server"] == "1.2.3.4"
    assert out["v2ray_import"] == out["vmess_link"]
    assert "clash://install-config" in out["clash_import"]
    # vmess base64 可解码
    b64 = out["vmess_link"].removeprefix("vmess://")
    decoded = json.loads(base64.b64decode(b64).decode())
    assert decoded["add"] == "1.2.3.4" and decoded["port"] == 8080


def test_format_proxy_protocols_missing_country_fields_use_defaults():
    out = geo.format_proxy_protocols("", "1.1.1.1", 53, {}, latency_ms=0)
    # country_info.get("name", "全球") 用于 node_name；但 country 字段默认 "未知"
    assert out["country"] == "未知"
    assert out["country_emoji"] == "🌐"
    assert out["country_code"] == "UN"


# ── generate_subscription_text ────────────────────────────────


def _make_proxy(ip: str, port: int) -> dict:
    return geo.format_proxy_protocols("", ip, port, {"name": "X", "emoji": "🌐", "code": "UN"}, latency_ms=10)


def test_subscription_base64_format():
    proxies = [_make_proxy("1.2.3.4", 8080), _make_proxy("5.6.7.8", 9090)]
    out = geo.generate_subscription_text(proxies, fmt="base64")
    decoded = base64.b64decode(out).decode("utf-8")
    assert "听风AI免费代理池" in decoded
    assert "socks5://1.2.3.4:8080" in decoded
    assert "vmess://" in decoded
    assert "ss://" in decoded


def test_subscription_raw_format():
    out = geo.generate_subscription_text([_make_proxy("1.1.1.1", 53)], fmt="raw")
    assert "socks5://1.1.1.1:53" in out
    assert out.startswith("# 听风AI")


def test_subscription_clash_format():
    proxies = [_make_proxy("1.2.3.4", 8080), _make_proxy("5.6.7.8", 9090)]
    out = geo.generate_subscription_text(proxies, fmt="clash")
    assert "proxies:" in out
    assert "socks5" in out
    assert "1.2.3.4" in out and "5.6.7.8" in out
    assert "proxy-groups:" in out
    assert "♻️ 自动选择" in out
    assert "MATCH" in out


def test_subscription_clash_skips_missing_clash_proxy():
    proxies = [{"name": "broken"}, _make_proxy("1.2.3.4", 8080)]
    out = geo.generate_subscription_text(proxies, fmt="clash")
    assert "1.2.3.4" in out
    assert "broken" not in out  # 缺 clash_proxy 的被跳过


def test_subscription_empty_proxies_base64():
    out = geo.generate_subscription_text([], fmt="base64")
    decoded = base64.b64decode(out).decode()
    assert "听风AI" in decoded  # 头部注释仍在


# ── _query_ip_api_online 直接覆盖 ─────────────────────────────


def test_query_ip_api_online_success(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"status": "success", "country": "US", "countryCode": "US", "regionName": "VA", "city": "Ash", "isp": "G"}
            ).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
    r = geo._query_ip_api_online("8.8.8.8")
    assert r is not None and r["code"] == "US"


def test_query_ip_api_online_exception_returns_none(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("slow")))
    assert geo._query_ip_api_online("8.8.8.8") is None
