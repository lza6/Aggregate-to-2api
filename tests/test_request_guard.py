"""M1-A1（v6.7.0）：三层限流 L1 秒级令牌桶独立验证。

覆盖 A1 验收要求：
- 同 IP 第 N+1 次超桶 → 429（N=容量）；
- 不同 IP 互不影响（独立桶）；
- 回填后恢复（速率回填令牌，恢复放行）；
- 容量 <=0 关闭 L1，退化为仅滑窗 + daily_limit；
- 白名单绕过 L1；
- error_tracker 收到 RATE.001 计数（三层聚合）；
- 重启语义：reset_runtime_state 清零桶（与滑窗/daily 一致）。
"""

from __future__ import annotations

import time

import pytest
from starlette.requests import Request

import api.request_guard as rg
from api import config
from api.errors import AppError


def _make_request(ip: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/generate",
        "raw_path": b"/v1/generate",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"x-forwarded-for", ip.encode()), (b"host", b"testserver"), (b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "state": {},
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """每用例：关闭自动入黑名单 + 关闭滑窗（聚焦 L1）+ 重置内存状态。"""
    monkeypatch.setattr(config, "IF_AUTO_BLOCK_ENABLED", False)
    monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)  # 关闭滑窗，只测 L1
    monkeypatch.setattr(config, "IF_IP_WHITELIST", "")
    rg.reset_runtime_state()
    yield
    rg.reset_runtime_state()


class TestL1TokenBucket:
    def test_over_bucket_returns_429(self, monkeypatch):
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 3.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)  # 不回填
        ip = "203.0.113.41"
        results = []
        for _ in range(5):
            try:
                rg.check_generate_request(_make_request(ip))
                results.append("ok")
            except AppError as e:
                results.append(str(e.status_code))
        # cap=3：前 3 次放行（含首扣 1），第 4、5 次 429
        assert results == ["ok", "ok", "ok", "429", "429"], results

    def test_different_ips_independent(self, monkeypatch):
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 2.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        ip_a, ip_b = "203.0.113.42", "198.51.100.10"
        rg.check_generate_request(_make_request(ip_a))
        rg.check_generate_request(_make_request(ip_a))
        with pytest.raises(AppError) as ea:
            rg.check_generate_request(_make_request(ip_a))
        assert ea.value.status_code == 429
        # ip_b 仍满桶，独立放行 2 次
        rg.check_generate_request(_make_request(ip_b))
        rg.check_generate_request(_make_request(ip_b))

    def test_refill_restores_access(self, monkeypatch):
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 1.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 100.0)  # 极快回填
        ip = "203.0.113.43"
        rg.check_generate_request(_make_request(ip))  # 桶空
        with pytest.raises(AppError) as e1:
            rg.check_generate_request(_make_request(ip))  # 立即再请求 → 429
        assert e1.value.status_code == 429
        time.sleep(0.05)  # 回填 100*0.05=5 token（满）
        rg.check_generate_request(_make_request(ip))  # 恢复放行

    def test_capacity_zero_disables_l1(self, monkeypatch):
        """L1 关闭后不拦截；滑窗也关闭（IF_REQUESTS_PER_MINUTE=0）→ 全放行。"""
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 0.0)
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 0)
        ip = "203.0.113.44"
        for _ in range(100):
            rg.check_generate_request(_make_request(ip))  # 不抛

    def test_whitelist_bypasses_l1(self, monkeypatch):
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 1.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        monkeypatch.setattr(config, "IF_IP_WHITELIST", "203.0.113.45")
        ip = "203.0.113.45"
        for _ in range(20):  # 远超容量，白名单全放行
            rg.check_generate_request(_make_request(ip))

    def test_error_tracker_aggregates_rate_001(self, monkeypatch):
        """L1 超限计入 error_tracker（RATE.001），供 /v1/errors/aggregates 聚合。"""
        from api.error_tracker import count_of, reset

        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 1.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        reset()
        ip = "203.0.113.46"
        rg.check_generate_request(_make_request(ip))  # 放行
        with pytest.raises(AppError):
            rg.check_generate_request(_make_request(ip))  # 429 → record(RATE.001)
        assert count_of("RATE.001") >= 1

    def test_reset_clears_buckets(self, monkeypatch):
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", 1.0)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        ip = "203.0.113.47"
        rg.check_generate_request(_make_request(ip))  # 桶空
        with pytest.raises(AppError):
            rg.check_generate_request(_make_request(ip))
        rg.reset_runtime_state()  # 清零
        # 重置后桶满，首请求放行
        rg.check_generate_request(_make_request(ip))

    def test_default_capacity_aligns_with_per_minute(self, monkeypatch):
        """未显式设 IF_RATE_TOKEN_CAPACITY 时，默认 = IF_REQUESTS_PER_MINUTE。"""
        monkeypatch.setattr(config, "IF_REQUESTS_PER_MINUTE", 4)
        monkeypatch.setattr(config, "IF_RATE_TOKEN_CAPACITY", None)  # 走默认
        monkeypatch.setattr(config, "IF_RATE_TOKEN_REFILL_PER_SEC", 0.0)
        ip = "203.0.113.48"
        results = []
        for _ in range(6):
            try:
                rg.check_generate_request(_make_request(ip))
                results.append("ok")
            except AppError as e:
                results.append(str(e.status_code))
        # 默认容量 4：前 4 ok，第 5、6 → 429
        assert results == ["ok", "ok", "ok", "ok", "429", "429"], results
