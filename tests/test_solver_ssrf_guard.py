"""tests/test_solver_ssrf_guard.py — P1-A6（M13）solver SSRF 守卫测试。

验收：
- validate_solver_url：http/https scheme 放行，非 http 拒绝
- 链路本地 IP（169.254.x.x）拒绝（云元数据防 SSRF）
- 回环 127.0.0.1 放行（本地 cf_solver）
- 多播/保留 IP 拒绝
- configure_nodes 加载时 SSRF 守卫过滤不安全 URL
"""

from __future__ import annotations


def test_validate_solver_url_http_allowed():
    """http/https URL 放行。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("http://127.0.0.1:8001") is True
    assert validate_solver_url("https://solver.example.com:8001") is True


def test_validate_solver_url_non_http_rejected():
    """非 http/https scheme 拒绝。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("ftp://solver:8001") is False
    assert validate_solver_url("file:///etc/passwd") is False
    assert validate_solver_url("javascript:alert(1)") is False


def test_validate_solver_url_empty_rejected():
    """空/None URL 拒绝。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("") is False
    assert validate_solver_url("   ") is False


def test_validate_solver_url_link_local_rejected():
    """链路本地 169.254.x.x 拒绝（云元数据防 SSRF）。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("http://169.254.169.254:8001") is False  # AWS 元数据
    assert validate_solver_url("http://169.254.1.1:8001") is False


def test_validate_solver_url_loopback_allowed():
    """回环 127.0.0.1 放行（本地 cf_solver）。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("http://127.0.0.1:8001") is True


def test_validate_solver_url_multicast_rejected():
    """多播 IP 拒绝。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("http://224.0.0.1:8001") is False


def test_configure_nodes_filters_ssrf():
    """configure_nodes 加载时 SSRF 守卫过滤不安全 URL。"""
    from api.solver_guard import SolverGuard

    urls = ["http://127.0.0.1:8001", "http://169.254.169.254:8001", "ftp://bad:8001"]
    sg = SolverGuard(urls=urls)
    nodes = sg.get_nodes()
    urls_loaded = {n.url for n in nodes}
    # 只安全 URL 被加载
    assert "http://127.0.0.1:8001" in urls_loaded
    assert "http://169.254.169.254:8001" not in urls_loaded
    assert "ftp://bad:8001" not in urls_loaded


def test_configure_nodes_fallback_on_all_unsafe(monkeypatch):
    """全部 URL 不安全时回退 config.CF_SOLVER_URL（不空池）。"""
    from api import config
    from api.solver_guard import SolverGuard

    monkeypatch.setattr(config, "CF_SOLVER_URL", "http://127.0.0.1:8001")
    sg = SolverGuard(urls=["http://169.254.169.254:8001", "ftp://bad:8001"])
    nodes = sg.get_nodes()
    assert len(nodes) == 1
    assert nodes[0].url == "http://127.0.0.1:8001"


def test_private_ip_internal_allowed():
    """私有网段 10.x/192.168.x 放行（内网部署允许）。"""
    from api.solver_guard import validate_solver_url

    assert validate_solver_url("http://10.0.0.5:8001") is True
    assert validate_solver_url("http://192.168.1.5:8001") is True
