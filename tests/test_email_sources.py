"""v6.9.1: 邮箱池上游源只读端点 /v1/email-sources 验证。

覆盖：
- 端点返回 { items, count }，items 含各 source 的 name/base_url/priority/available/
  success_count/failure_count/last_error；
- 各字段类型与 email_pool.get_sources() 一致；
- custom-imap 无 BASE 常量 → base_url 为 None（不展示官网链接）；
- 纯只读：不触发建箱/收件，不修改 email_pool 状态。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import main as _main  # noqa: F401  (触发 app 装配)
from api.main import app
from api.email_pool import email_pool


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_email_sources_returns_items_and_count(client):
    r = client.get("/v1/email-sources")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "count" in body
    assert body["count"] == len(body["items"])
    assert body["count"] >= 1


def test_email_sources_item_shape(client):
    r = client.get("/v1/email-sources")
    items = r.json()["items"]
    expected_names = {s.name for s in email_pool.get_sources()}
    got_names = {it["name"] for it in items}
    assert got_names == expected_names, f"端点源集合与 email_pool 不一致: {got_names ^ expected_names}"
    for it in items:
        assert set(it.keys()) >= {
            "name", "base_url", "priority", "available",
            "success_count", "failure_count", "last_error",
        }, f"{it.get('name')} 字段不全: {set(it.keys())}"
        assert isinstance(it["name"], str)
        assert isinstance(it["priority"], int)
        assert isinstance(it["available"], bool)
        assert isinstance(it["success_count"], int)
        assert isinstance(it["failure_count"], int)
        assert it["last_error"] is None or isinstance(it["last_error"], str)


def test_custom_imap_has_null_base_url(client):
    """custom-imap 无独立官网 → base_url 必须为 null（前端据此不渲染官网直达）。"""
    items = client.get("/v1/email-sources").json()["items"]
    imap = next((it for it in items if it["name"] == "custom-imap"), None)
    assert imap is not None, "邮箱池必须含 custom-imap 源"
    assert imap["base_url"] is None, f"custom-imap base_url 应为 null，实际 {imap['base_url']!r}"


def test_known_sources_have_home_url(client):
    """已知独立官网的源（mail.tm/mail.gw/22.do 等）base_url 必须非空。"""
    items = client.get("/v1/email-sources").json()["items"]
    by_name = {it["name"]: it for it in items}
    for name in ("linshi-email", "mail.tm", "mail.gw", "22.do", "guerrillamail",
                 "temp-mail", "temp-mail.io", "temp.tf"):
        assert by_name[name]["base_url"], f"{name} base_url 不能为空"
        assert by_name[name]["base_url"].startswith("http"), f"{name} base_url 非合法 URL"


def test_email_sources_readonly_no_state_change(client):
    """/v1/email-sources 纯只读：调用前后 email_pool 各源 success/failure 计数不变。"""
    before = {s.name: (s.success_count, s.failure_count) for s in email_pool.get_sources()}
    client.get("/v1/email-sources")
    client.get("/v1/email-sources")
    after = {s.name: (s.success_count, s.failure_count) for s in email_pool.get_sources()}
    assert before == after, f"只读端点修改了 email_pool 状态: before={before} after={after}"
