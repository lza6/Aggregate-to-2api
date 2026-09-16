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
        """v12.0.0 工具白名单 + v16 P0-1 task_status：5 原工具 + 异步任务状态轮询。"""
        resp = mcp_client.post("/v1/mcp", json=_rpc("tools/list"))
        tools = resp.json()["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {
            "skills_list",
            "skills_get",
            "dag_plan",
            "dag_status",
            "generate_image",
            "task_status",
        }
        for t in tools:
            assert "inputSchema" in t and t["inputSchema"]["type"] == "object"
        by_name = {t["name"]: t for t in tools}
        assert by_name["skills_list"]["annotations"]["readOnlyHint"] is True
        assert by_name["generate_image"]["annotations"]["readOnlyHint"] is False
        assert by_name["task_status"]["annotations"]["readOnlyHint"] is True


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
        """未知方法 → -32601（v16 后 resources/list/prompts/list 已是合法方法，用无此方法名验证）。"""
        resp = mcp_client.post("/v1/mcp", json=_rpc("no_such_method"))
        assert resp.json()["error"]["code"] == -32601

    def test_resources_list(self, mcp_client: TestClient):
        """v16 P0-1：resources/list 返回只读资源（memory/audit/skills）。"""
        resp = mcp_client.post("/v1/mcp", json=_rpc("resources/list"))
        result = resp.json()["result"]
        assert result["resources"]
        uris = {r["uri"] for r in result["resources"]}
        assert "memory://latest" in uris and "skills://index" in uris

    def test_prompts_list(self, mcp_client: TestClient):
        """v16 P0-1：prompts/list 返回提示词模板（image-from-prompt 等）。"""
        resp = mcp_client.post("/v1/mcp", json=_rpc("prompts/list"))
        result = resp.json()["result"]
        names = {p["name"] for p in result["prompts"]}
        assert "image-from-prompt" in names and "cost-review" in names

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


class TestStreamableHTTP:
    """v16 P0-1：Streamable HTTP——Accept: text/event-stream → SSE 分帧；DELETE → 会话结束。"""

    def test_accept_sse_returns_event_stream(self, mcp_client: TestClient):
        """Accept: text/event-stream 时 initialize 走 SSE 分帧（event: message + data: <json>）。"""
        resp = mcp_client.post(
            "/v1/mcp",
            json=_rpc("initialize", {}),
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        body = resp.text
        assert body.startswith("event: message\ndata: ")
        # 分帧内 JSON 可解析且含 capabilities.resources
        import json as _json

        data_line = body.split("\ndata: ", 1)[1].rsplit("\n\n", 1)[0]
        payload = _json.loads(data_line)
        assert payload["result"]["capabilities"]["resources"] == {}

    def test_accept_json_keeps_single_response(self, mcp_client: TestClient):
        """仅 Accept: application/json 时保持单响应 JSON（向后兼容既有调用方）。"""
        resp = mcp_client.post(
            "/v1/mcp",
            json=_rpc("initialize", {}),
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/json")
        assert resp.json()["result"]["capabilities"]["tools"] == {}

    def test_delete_ends_session_200(self, mcp_client: TestClient):
        """Streamable HTTP 会话结束：DELETE /v1/mcp → 200（无状态会话）。"""
        resp = mcp_client.delete("/v1/mcp")
        assert resp.status_code == 200

    def test_generate_image_async_then_task_status(self, mcp_client: TestClient):
        """v16 P0-1：generate_image 异步任务形态 → task_status 轮询收敛（Mock 级幂等）。"""
        # 提交生图（Mock）：返回 {task_id, status: queued}
        submit = mcp_client.post(
            "/v1/mcp",
            json=_rpc("tools/call", {"name": "generate_image", "arguments": {"prompt": "一只猫"}}),
        )
        result = submit.json()["result"]
        content = result["content"][0]["text"]
        assert result["isError"] is False
        assert "task_id" in content and "queued" in content
        # 解析 task_id（MCP content 为 str(dict) 文本——与既有 dag_plan 同格式，用 literal_eval 安全解析）
        import ast

        data = ast.literal_eval(content)
        task_id = data["task_id"]
        assert task_id
        # 轮询 task_status（幂等 3 次收敛到 completed）
        for _ in range(3):
            poll = mcp_client.post(
                "/v1/mcp",
                json=_rpc("tools/call", {"name": "task_status", "arguments": {"task_id": task_id}}),
            )
            poll_result = poll.json()["result"]
            assert poll_result["isError"] is False
            text = poll_result["content"][0]["text"]
            # MCP content 为 str(dict)（repr 单引号）：completed 标记以 'completed' 形式出现
            if "'completed'" in text or '"completed"' in text:
                break
        else:
            raise AssertionError("task_status 3 轮未收敛到 completed")
