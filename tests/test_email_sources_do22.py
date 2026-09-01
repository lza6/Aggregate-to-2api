"""Do22Source / TempMailSource 单元测试（P0-2 覆盖率补强，mock httpx 不发真实请求）。

覆盖：
- Do22Source.new_address：白名单域名命中/15 次重试耗尽抛错/非 200 重试/token 获取。
- Do22Source.fetch_mails：无 token 空返回/列表+详情聚合/详情失败回退原 item/非 200/异常吞掉。
- TempMailSource（tempmail.py）核心分支。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.email_sources.do22 import Do22Source
from api.email_sources.tempmail import TempMailSource


def _mock_response(status_code: int = 200, payload: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = lambda: payload or {}
    return resp


# ── Do22Source.new_address ───────────────────────────────────


@pytest.fixture
def do22() -> Do22Source:
    src = Do22Source()
    src.session = MagicMock()
    src.session.post = AsyncMock()
    return src


@pytest.mark.asyncio
async def test_do22_new_address_whitelist_hit(do22):
    """create 返回白名单域名 → 登录+applyToken → 返回 (address, state)。"""
    do22.session.post.side_effect = [
        _mock_response(200, {"data": {"email": "abc@tnbeta.com"}}),
        _mock_response(200),  # login
        _mock_response(200, {"data": {"token": "tok-1"}}),  # applyToken
    ]
    address, state = await do22.new_address()
    assert address == "abc@tnbeta.com"
    assert state["source"] == "22.do"
    assert state["email"] == "abc@tnbeta.com"
    assert state["token"] == "tok-1"
    assert do22.session.post.call_count == 3


@pytest.mark.asyncio
async def test_do22_new_address_retries_then_success(do22):
    """前几次返回非白名单域名/非 200 → 重试直到命中。"""
    do22.session.post.side_effect = [
        _mock_response(500),
        _mock_response(200, {"data": {"email": "bad@evil.com"}}),  # 非白名单
        _mock_response(200, {"data": {}}),  # 空 email
        _mock_response(200, {"data": {"email": "ok@colaname.com"}}),
        _mock_response(200),  # login
        _mock_response(200, {"data": {"token": "t"}}),
    ]
    address, state = await do22.new_address()
    assert address == "ok@colaname.com"
    assert state["token"] == "t"


@pytest.mark.asyncio
async def test_do22_new_address_exhausted_raises(do22):
    """15 次全部失败 → RuntimeError。"""
    do22.session.post.side_effect = [_mock_response(500)] * 15
    with pytest.raises(RuntimeError, match="22.do"):
        await do22.new_address()


@pytest.mark.asyncio
async def test_do22_new_address_token_empty_ok(do22):
    """applyToken 失败 → token 为空串但不抛（建箱成功即可）。"""
    do22.session.post.side_effect = [
        _mock_response(200, {"data": {"email": "x@usdtbeta.com"}}),
        _mock_response(200),
        _mock_response(200, {"data": {}}),  # 无 token
    ]
    address, state = await do22.new_address()
    assert address == "x@usdtbeta.com"
    assert state["token"] == ""


# ── Do22Source.fetch_mails ───────────────────────────────────


@pytest.mark.asyncio
async def test_do22_fetch_no_token_returns_empty(do22):
    assert await do22.fetch_mails("a@tnbeta.com", state={}) == []
    assert await do22.fetch_mails("a@tnbeta.com", state=None) == []


@pytest.mark.asyncio
async def test_do22_fetch_detail_success(do22):
    """列表 2 封 → 详情成功 1 封（content 聚合）、详情缺 id 回退原 item。"""
    listing = [
        {"id": "m1", "subject": "s1"},
        {"subject": "no-id"},  # 无 id → 原样返回
    ]
    do22.session.post.side_effect = [
        _mock_response(200, {"data": listing}),
        _mock_response(200, {"data": {"content": "<b>hello</b>"}}),  # m1 详情
    ]
    mails = await do22.fetch_mails("a@tnbeta.com", state={"email": "a@tnbeta.com", "token": "t"})
    assert len(mails) == 2
    assert mails[0]["id"] == "m1"
    assert mails[0]["bodyHtml"] == "<b>hello</b>"
    assert mails[1]["subject"] == "no-id"


@pytest.mark.asyncio
async def test_do22_fetch_detail_fails_fallback_to_item(do22):
    """详情请求 500 → 回退原 item（不丢邮件）。"""
    do22.session.post.side_effect = [
        _mock_response(200, {"data": [{"id": "m2", "subject": "keep"}]}),
        _mock_response(500),
    ]
    mails = await do22.fetch_mails("a@tnbeta.com", state={"token": "t"})
    assert mails == [{"id": "m2", "subject": "keep"}]


@pytest.mark.asyncio
async def test_do22_fetch_list_non_200(do22):
    do22.session.post.side_effect = [_mock_response(503)]
    assert await do22.fetch_mails("a@tnbeta.com", state={"token": "t"}) == []


@pytest.mark.asyncio
async def test_do22_fetch_list_data_not_list(do22):
    do22.session.post.side_effect = [_mock_response(200, {"data": "weird"})]
    assert await do22.fetch_mails("a@tnbeta.com", state={"token": "t"}) == []


@pytest.mark.asyncio
async def test_do22_fetch_exception_swallowed(do22):
    do22.session.post.side_effect = ConnectionError("network down")
    assert await do22.fetch_mails("a@tnbeta.com", state={"token": "t"}) == []


@pytest.mark.asyncio
async def test_do22_fetch_detail_uses_state_email_over_arg(do22):
    """state.email 优先于 address 参数。"""
    do22.session.post.side_effect = [
        _mock_response(200, {"data": []}),
    ]
    await do22.fetch_mails("arg@x.com", state={"email": "state@tnbeta.com", "token": "t"})
    body = do22.session.post.call_args_list[0].kwargs["json"]
    assert body["email"] == "state@tnbeta.com"


# ── TempMailSource（tempmail.py）─────────────────────────────


@pytest.fixture
def tempmail() -> TempMailSource:
    src = TempMailSource()
    src.session = MagicMock()
    src.session.post = AsyncMock()
    src.session.get = AsyncMock()
    src._last_create = 0.0
    return src


@pytest.mark.asyncio
async def test_tempmail_new_address_success(tempmail):
    tempmail.session.post.return_value = _mock_response(
        200, {"mailbox": "user@dcpa.net", "token": "tk"}
    )
    address, state = await tempmail.new_address()
    assert address == "user@dcpa.net"
    assert state == {"source": "temp-mail", "token": "tk"}
    assert tempmail._last_create > 0


@pytest.mark.asyncio
async def test_tempmail_new_address_429_marks_failure(tempmail):
    tempmail.session.post.return_value = _mock_response(429)
    with pytest.raises(RuntimeError, match="429"):
        await tempmail.new_address()
    assert tempmail.failure_count == 1
    assert tempmail.cooldown_until > 0  # 退避冷却已生效


@pytest.mark.asyncio
async def test_tempmail_new_address_other_status_raises(tempmail):
    tempmail.session.post.return_value = _mock_response(500)
    with pytest.raises(RuntimeError, match="500"):
        await tempmail.new_address()


@pytest.mark.asyncio
async def test_tempmail_new_address_invalid_payload_raises(tempmail):
    tempmail.session.post.return_value = _mock_response(200, {"mailbox": "no-at-sign", "token": ""})
    with pytest.raises(RuntimeError, match="异常"):
        await tempmail.new_address()


@pytest.mark.asyncio
async def test_tempmail_fetch_no_token_empty(tempmail):
    assert await tempmail.fetch_mails("a@dcpa.net", state={}) == []


@pytest.mark.asyncio
async def test_tempmail_fetch_list_with_detail(tempmail):
    tempmail.session.get.side_effect = [
        _mock_response(200, [{"_id": "m1", "subject": "s"}]),
        _mock_response(200, {"subject": "detail-subj", "bodyHtml": "<p>x</p>"}),
    ]
    mails = await tempmail.fetch_mails("a@dcpa.net", state={"token": "t"})
    assert len(mails) == 1
    assert mails[0]["id"] == "m1"
    assert mails[0]["subject"] == "detail-subj"
    assert mails[0]["bodyHtml"] == "<p>x</p>"


@pytest.mark.asyncio
async def test_tempmail_fetch_dict_payload_messages_key(tempmail):
    """响应为 dict 时按 messages/data/mailbox 键提取列表。"""
    tempmail.session.get.side_effect = [
        _mock_response(200, {"messages": [{"id": "m2"}]}),
        _mock_response(500),  # 详情失败 → 回退原 item
    ]
    mails = await tempmail.fetch_mails("a@dcpa.net", state={"token": "t"})
    assert mails == [{"id": "m2"}]


@pytest.mark.asyncio
async def test_tempmail_fetch_list_fail_or_exception(tempmail):
    tempmail.session.get.side_effect = [_mock_response(502)]
    assert await tempmail.fetch_mails("a@dcpa.net", state={"token": "t"}) == []
    tempmail.session.get.side_effect = OSError("boom")
    assert await tempmail.fetch_mails("a@dcpa.net", state={"token": "t"}) == []
