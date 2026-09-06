"""SecuritySettings 子配置。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SecuritySettings(BaseModel):
    """安全 / 鉴权配置组。"""

    gallery_password: str = ""
    ip_whitelist: str = Field("", validation_alias="IF_IP_WHITELIST")
    trusted_proxies: str = Field("127.0.0.1,::1", validation_alias="IF_TRUSTED_PROXIES")
    auto_block_enabled: bool = Field(True, validation_alias="IF_AUTO_BLOCK_ENABLED")
    auto_block_threshold: int = Field(3, validation_alias="IF_AUTO_BLOCK_THRESHOLD")
    auto_block_window_seconds: int = Field(300, validation_alias="IF_AUTO_BLOCK_WINDOW_SECONDS")
    auto_block_ttl_seconds: int = Field(3600, validation_alias="IF_AUTO_BLOCK_TTL_SECONDS")
    cors_origins: str = Field("*", validation_alias="IF_CORS_ORIGINS")
    # P3-3: 生产安全响应头注入开关（默认开启；关闭=最小回滚，不注入任何安全头）。
    # 仅当 True 时 SecurityHeadersMiddleware 注入 X-Content-Type-Options / X-Frame-Options /
    # Referrer-Policy / Strict-Transport-Security（仅 HTTPS）。
    security_headers_enabled: bool = Field(True, validation_alias="IF_SECURITY_HEADERS_ENABLED")
    # P3-3: 宽松 CSP 响应头开关（默认关闭，避免误杀管理面板/画廊 CDN 图片与内联脚本）。
    csp_enabled: bool = Field(False, validation_alias="IF_CSP_ENABLED")
    # v4.4: 全局 API Key 保护（防滥用）。逗号分隔多个 Key；空列表 = 开放。
    api_keys: list[str] = Field(default_factory=list, validation_alias="IF_API_KEYS")
    # v4.4: 聊天端点每分钟限流（0 = 不限）
    chat_requests_per_minute: int = Field(60, validation_alias="IF_CHAT_RATE_LIMIT")

    @classmethod
    def from_settings(cls, s: Any) -> SecuritySettings:
        """从 Settings 实例提取字段构造 SecuritySettings。"""
        return cls(
            gallery_password=s.if_gallery_password,
            ip_whitelist=s.if_ip_whitelist,
            trusted_proxies=s.if_trusted_proxies,
            auto_block_enabled=s.if_auto_block_enabled,
            auto_block_threshold=s.if_auto_block_threshold,
            auto_block_window_seconds=s.if_auto_block_window_seconds,
            auto_block_ttl_seconds=s.if_auto_block_ttl_seconds,
            cors_origins=s.if_cors_origins,
            security_headers_enabled=s.if_security_headers_enabled,
            csp_enabled=s.if_csp_enabled,
            api_keys=[k.strip() for k in (s.if_api_keys or "").split(",") if k.strip()],
            chat_requests_per_minute=s.if_chat_rate_limit,
        )

    def to_env(self) -> dict[str, Any]:
        """导出 env 风格大写键（IP_WHITELIST / TRUSTED_PROXIES / ...）。

        `model_dump()` 输出 pydantic 字段名下划线小写（如 if_ip_whitelist），而
        /v1/meta 消费方与 env.example 期望大写风格。此处按 validation_alias 输出并剥掉
        IF_ 前缀（无 alias 字段用字段名全大写），得到 IP_WHITELIST / TRUSTED_PROXIES /
        CORS_ORIGINS / SECURITY_HEADERS_ENABLED / CSP_ENABLED / API_KEYS / CHAT_RATE_LIMIT / ...
        """
        out: dict[str, Any] = {}
        for name, field in type(self).model_fields.items():
            alias = getattr(field, "validation_alias", None)
            if isinstance(alias, str) and alias.startswith("IF_"):
                key = alias[len("IF_") :]
            else:
                key = name.upper()
            out[key] = getattr(self, name)
        return out
