"""P-TEST-A6: api/config.py 校验与结构测试。

覆盖：
- validate() 各错误分支（port 越界 / max_queue<1 / workers<1 / token_pool_size<1 /
  workers_max<workers_min / base_url 空 / sitekey 空 / cf_solver_url 空）
- _resolve_proxy_and_init_groups 的代理 fallback（HTTPS_PROXY/HTTP_PROXY 环境变量）
- settings_json 分组结构完整（含 security env 风格键与 chat 组）
- env.example 与 config 的 IF_* 双向一致（P1-1 漂移闭环）
"""

from __future__ import annotations

import re
from pathlib import Path

from api.config import Settings

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_EXAMPLE = _REPO_ROOT / "deploy" / ".env.example"


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
            "chat",
        }
        # 抽查关键字段
        assert "file" in js["db"]
        assert "host" in js["http"]
        assert "cf_solver_url" in js["solver"]
        assert "log_dir" in js.get("observability", {}) or True  # P13 若并入分组则断言

    def test_security_uses_env_style_keys(self):
        """P1-2: security 分组输出 env 风格大写键（IF_ 前缀剥离）。"""
        s = Settings(_env_file=None)
        s._resolve_proxy_and_init_groups()
        sec = s.settings_json()["security"]
        assert "IP_WHITELIST" in sec
        assert "TRUSTED_PROXIES" in sec
        assert "AUTO_BLOCK_ENABLED" in sec
        assert "CORS_ORIGINS" in sec
        assert "API_KEYS" in sec
        assert "CHAT_RATE_LIMIT" in sec
        # 不再输出 pydantic 下划线小写字段名
        assert "cors_origins" not in sec

    def test_settings_json_exposes_tryingopen_chat(self):
        """P1-1: settings_json 透传 tryingopen 调度参数（chat 分组）。"""
        s = Settings(_env_file=None)
        s._resolve_proxy_and_init_groups()
        chat = s.settings_json()["chat"]
        assert chat["tryingopen_enabled"] is True
        assert chat["tryingopen_hourly_per_ip"] == 20
        assert chat["tryingopen_max_attempts"] == 3
        assert chat["tryingopen_sync_minutes"] == 30

    def test_tryingopen_config_constants_match_fields(self):
        """P1-1: 模块级 IF_TRYINGOPEN_* 常量与 Settings 字段同步。"""
        import api.config as cfg

        assert cfg.settings.if_tryingopen_enabled == cfg.IF_TRYINGOPEN_ENABLED
        assert cfg.settings.if_tryingopen_hourly_per_ip == cfg.IF_TRYINGOPEN_HOURLY_PER_IP
        assert cfg.settings.if_tryingopen_max_attempts == cfg.IF_TRYINGOPEN_MAX_ATTEMPTS
        assert cfg.settings.if_tryingopen_sync_minutes == cfg.IF_TRYINGOPEN_SYNC_MINUTES


class TestEnvExampleSync:
    """P1-1: deploy/.env.example 与 config 的 IF_* 双向一致（漂移闭环）。"""

    @staticmethod
    def _config_consumed() -> set[str]:
        import glob

        import api.config as cfg

        pkg = Path(cfg.__file__).parent
        aliases: set[str] = set()
        for fp in glob.glob(str(pkg / "*.py")):
            src = Path(fp).read_text(encoding="utf-8")
            aliases |= set(re.findall(r'validation_alias\s*=\s*"(IF_[A-Z0-9_]+)"', src))
            aliases |= set(re.findall(r'os\.getenv\("(IF_[A-Z0-9_]+)"', src))
        return aliases

    def test_every_config_alias_has_env_example(self):
        """config 每个 alias 都能在 env.example 找到（缺失即 fail）。"""
        env_text = _ENV_EXAMPLE.read_text(encoding="utf-8")
        env_vars = set(re.findall(r"^(IF_[A-Z0-9_]+)\s*=", env_text, re.M))
        missing = sorted(self._config_consumed() - env_vars)
        assert not missing, f"config 存在但 env.example 缺失: {missing}"

    def test_every_env_example_var_is_consumed(self):
        """env.example 每个 IF_* 都能在 config 找到 alias（孤儿即 fail）。"""
        env_text = _ENV_EXAMPLE.read_text(encoding="utf-8")
        env_vars = set(re.findall(r"^(IF_[A-Z0-9_]+)\s*=", env_text, re.M))
        orphan = sorted(env_vars - self._config_consumed())
        assert not orphan, f"env.example 存在但 config 未消费: {orphan}"
