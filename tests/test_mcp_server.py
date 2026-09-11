"""tests/test_mcp_server.py — v12.0.0 P1-M1 MCP 协议化端点测试（TDD）。

覆盖（JSON-RPC 2.0 契约 + 工具白名单 + 开关）：
- IF_MCP_ENABLED=0（默认）→ 404
- initialize 握手：protocolVersion + capabilities + serverInfo
- tools/list：5 工具白名单 + inputSchema + readOnlyHint
- tools/call skills_list / dag_plan（Mock）→ content text + isError=False
- tools/call 未知工具 → -32602
- 未知方法 → -32601；非法 jsonrpc → -32600；坏 JSON → -32700
- 通知（无 id）→ 202
付费红线：dag_plan/generate_image 均在 IF_MOCK_UPSTREAM=1 下验证，零真实付费。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def mcp_client(monkeypatch):
    """IF_MCP_ENABLED=1 + IF_MOCK_UPSTREAM=1 的 TestClient（付费红线：全 Mock）。"""
    from api.config import reset_settings

    monkeypatch.setenv("IF_MCP_ENABLED", "1")
    monkeypatch.setenv("IF_MOCK_UPSTREAM", "1")
    reset_settings()
    from api.main import app

    with TestClient(app) as c:
        yield c
    monkeypatch.setenv("IF_MCP_ENABLED", "0")
    reset_settings()


def _rpc(method: str, params: dict | None = None, req_id: int | str = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


class TestSwitch:
    def test_disabled_by_default_404(self, monkeypatch):
        """IF_MCP_ENABLED 缺省 False → 404（新功能缺省关）。"""
        from api.config import reset_settings

        monkeypatch.setenv("IF_MCP_ENABLED", "0")
        reset_settings()
        from api.main import app

        with TestClient(app) as c:
            resp = c.post("/v1/mcp", json=_rpc("initialize", {}))
            assert resp.status_code == 404


class TestHandshake:
    def test_initialize_returns_protocol_and_server_info(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", json=_rpc("initialize", {}))
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0" and data["id"] == 1
        result = data["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "tingfeng-ai-mcp"


class TestToolsList:
    def test_tools_list_whitelist(self, mcp_client: TestClient):
        """v12.0.0 工具白名单：4 只读 + 1 受控生图，均带 inputSchema。"""
        resp = mcp_client.post("/v1/mcp", json=_rpc("tools/list"))
        tools = resp.json()["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {"skills_list", "skills_get", "dag_plan", "dag_status", "generate_image"}
        for t in tools:
            assert "inputSchema" in t and t["inputSchema"]["type"] == "object"
        by_name = {t["name"]: t for t in tools}
        assert by_name["skills_list"]["annotations"]["readOnlyHint"] is True
        assert by_name["generate_image"]["annotations"]["readOnlyHint"] is False


class TestToolsCall:
    def test_call_skills_list(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", json=_rpc("tools/call", {"name": "skills_list", "arguments": {}}))
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        assert "ecommerce-visual-copywriting" in result["content"][0]["text"]

    def test_call_skills_get(self, mcp_client: TestClient):
        resp = mcp_client.post(
            "/v1/mcp",
            json=_rpc("tools/call", {"name": "skills_get", "arguments": {"name": "ppt-outline-gen"}}),
        )
        result = resp.json()["result"]
        assert result["isError"] is False
        assert "叙事" in result["content"][0]["text"]

    def test_call_dag_plan_mock(self, mcp_client: TestClient):
        """dag_plan：IF_MOCK_UPSTREAM=1 → Mock 规划（付费红线）。"""
        resp = mcp_client.post(
            "/v1/mcp",
            json=_rpc("tools/call", {"name": "dag_plan", "arguments": {"prompt": "画一只猫"}}),
        )
        result = resp.json()["result"]
        assert result["isError"] is False
        assert '"mock"' in result["content"][0]["text"] or "nodes" in result["content"][0]["text"]

    def test_call_unknown_tool_invalid_params(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", json=_rpc("tools/call", {"name": "rm_rf_slash"}))
        err = resp.json()["error"]
        assert err["code"] == -32602
        assert "Unknown tool" in err["message"]

    def test_call_missing_required_param_is_error_content(self, mcp_client: TestClient):
        """缺 name → 工具内 ValueError → content isError=True（业务错误不炸协议）。"""
        resp = mcp_client.post("/v1/mcp", json=_rpc("tools/call", {"name": "skills_get", "arguments": {}}))
        result = resp.json()["result"]
        assert result["isError"] is True


class TestProtocolErrors:
    def test_unknown_method_32601(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", json=_rpc("resources/list"))
        assert resp.json()["error"]["code"] == -32601

    def test_invalid_jsonrpc_32600(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", json={"id": 1, "method": "ping"})
        assert resp.json()["error"]["code"] == -32600

    def test_bad_json_32700(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", content=b"{not json", headers={"Content-Type": "application/json"})
        assert resp.json()["error"]["code"] == -32700

    def test_notification_202(self, mcp_client: TestClient):
        """通知（无 id）→ 202 无响应体。"""
        resp = mcp_client.post("/v1/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp.status_code == 202

    def test_ping(self, mcp_client: TestClient):
        resp = mcp_client.post("/v1/mcp", json=_rpc("ping"))
        assert resp.json()["result"] == {}
