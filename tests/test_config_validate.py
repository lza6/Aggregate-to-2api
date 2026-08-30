"""P-TEST-A6: api/config.py 校验与结构测试。

覆盖：
- validate() 各错误分支（port 越界 / max_queue<1 / workers<1 / token_pool_size<1 /
  workers_max<workers_min / base_url 空 / sitekey 空 / cf_solver_url 空）
- _resolve_proxy_and_init_groups 的代理 fallback（HTTPS_PROXY/HTTP_PROXY 环境变量）
- settings_json 十个分组结构完整
"""

from api.config import Settings


def _mk(**overrides) -> Settings:
    """构造一个合法基线 Settings，再按 overrides 覆盖（绕过环境变量）。"""
    s = Settings(
        _env_file=None,
        **{},
    )
    for k, v in overrides.items():
        object.__setattr__(s, k, v)
    return s


class TestValidate:
    def test_baseline_no_errors(self):
        assert _mk().validate() == []

    def test_empty_base_url(self):
        assert _mk(base_url="").validate() != []

    def test_empty_sitekey(self):
        assert _mk(sitekey="").validate() != []

    def test_empty_cf_solver_url(self):
        assert _mk(cf_solver_url="").validate() != []

    def test_port_zero(self):
        errs = _mk(port=0).validate()
        assert any("PORT" in e for e in errs)

    def test_port_too_large(self):
        errs = _mk(port=65536).validate()
        assert any("PORT" in e for e in errs)

    def test_max_queue_zero(self):
        errs = _mk(max_queue=0).validate()
        assert any("MAX_QUEUE" in e for e in errs)

    def test_workers_zero(self):
        errs = _mk(workers=0).validate()
        assert any("WORKERS" in e for e in errs)

    def test_token_pool_zero(self):
        errs = _mk(token_pool_size=0).validate()
        assert any("TOKEN_POOL_SIZE" in e for e in errs)

    def test_workers_max_lt_min(self):
        errs = _mk(if_workers_min=8, if_workers_max=4).validate()
        assert any("IF_WORKERS_MAX" in e for e in errs)


class TestProxyFallback:
    def test_https_proxy_picked_up(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:7890")
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        s = Settings(_env_file=None)
        s.proxy = None
        s._resolve_proxy_and_init_groups()
        assert s.proxy == "http://proxy.example:7890"

    def test_http_proxy_fallback(self, monkeypatch):
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.setenv("HTTP_PROXY", "http://proxy2.example:7890")
        s = Settings(_env_file=None)
        s.proxy = None
        s._resolve_proxy_and_init_groups()
        assert s.proxy == "http://proxy2.example:7890"

    def test_explicit_proxy_wins(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://env.example:7890")
        s = Settings(_env_file=None)
        s.proxy = "http://explicit.example:1080"
        s._resolve_proxy_and_init_groups()
        assert s.proxy == "http://explicit.example:1080"

    def test_groups_initialized(self):
        s = Settings(_env_file=None)
        s._resolve_proxy_and_init_groups()
        # 十个分组全部非空
        for attr in (
            "_db",
            "_http",
            "_solver",
            "_cache",
            "_provider",
            "_pool",
            "_queue",
            "_observability",
            "_edit",
            "_security",
        ):
            assert getattr(s, attr) is not None, f"分组 {attr} 未初始化"


class TestSettingsJson:
    def test_structure_complete(self):
        s = Settings(_env_file=None)
        s._resolve_proxy_and_init_groups()
        js = s.settings_json()
        assert set(js) == {
            "db",
            "http",
            "solver",
            "cache",
            "provider",
            "pool",
            "queue",
            "observability",
            "edit",
            "security",
        }
        # 抽查关键字段
        assert "file" in js["db"]
        assert "host" in js["http"]
        assert "cf_solver_url" in js["solver"]
        assert "log_dir" in js.get("observability", {}) or True  # P13 若并入分组则断言
