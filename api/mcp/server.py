"""api/mcp/server.py — v12.0.0 P1-M1 MCP JSON-RPC 2.0 端点。

POST /v1/mcp：
- initialize           → protocolVersion/capabilities/serverInfo 握手
- notifications/*      → 202（通知无响应体）
- tools/list           → {tools:[{name,description,inputSchema}]}
- tools/call           → {content:[{type:"text",text}], isError}
- ping                 → {}
- 未知方法             → -32601 method not found
- 参数错误/工具异常    → -32602 invalid params（工具 ValueError 归入此码）
- 解析失败             → -32700 parse error

鉴权：只读工具走 auth.guard_chat_request（per-IP 限流，公益开放）。
开关：IF_MCP_ENABLED=0（默认）→ 404（config 工厂，setenv+reset_settings 后生效）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import auth
from ..errors import AppError, ErrorCodes
from .tools import build_tools, find_tool

router = APIRouter()
log = logging.getLogger("mcp.server")

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "tingfeng-ai-mcp", "version": "12.1.0"}


def mcp_enabled() -> bool:
    """IF_MCP_ENABLED 是否开启（config 工厂，缺省 False）。"""
    try:
        from ..config import get_settings

        return bool(get_settings().if_mcp_enabled)
    except Exception:
        return False


def _jsonrpc_result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# JSON-RPC 2.0 标准错误码
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602


async def _handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    """tools/call：执行工具 → MCP content 信封。工具 ValueError → 业务错误（isError）。"""
    name = str(params.get("name", ""))
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments 必须是 object")
    tool = find_tool(build_tools(), name)
    if tool is None:
        raise KeyError(name)
    try:
        result = await tool.handler(arguments)
        text = str(result)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except ValueError as exc:
        return {"content": [{"type": "text", "text": f"参数错误：{exc}"}], "isError": True}


@router.post("/v1/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 2.0 单端点。"""
    if not mcp_enabled():
        raise AppError(ErrorCodes.NOT_FOUND, "MCP 端点已关闭（IF_MCP_ENABLED=0）", 404)
    # 公益开放 + per-IP 限流（与 chat/DAG 同基线）
    auth.guard_chat_request(request)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(_jsonrpc_error(None, _PARSE_ERROR, "Parse error"), status_code=200)

    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return JSONResponse(
            _jsonrpc_error(payload.get("id") if isinstance(payload, dict) else None, _INVALID_REQUEST, "Invalid Request"),
            status_code=200,
        )

    method = str(payload.get("method", ""))
    req_id = payload.get("id")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # 通知（无 id）：202 无响应体
    if "id" not in payload:
        return JSONResponse(None, status_code=202)

    tools_cache = build_tools()

    if method == "initialize":
        return JSONResponse(
            _jsonrpc_result(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            ),
            status_code=200,
        )

    if method == "ping":
        return JSONResponse(_jsonrpc_result(req_id, {}), status_code=200)

    if method == "tools/list":
        return JSONResponse(
            _jsonrpc_result(
                req_id,
                {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                            "annotations": {"readOnlyHint": t.read_only},
                        }
                        for t in tools_cache
                    ]
                },
            ),
            status_code=200,
        )

    if method == "tools/call":
        try:
            result = await _handle_tools_call(params)
        except KeyError:
            return JSONResponse(
                _jsonrpc_error(req_id, _INVALID_PARAMS, f"Unknown tool: {params.get('name', '')}"),
                status_code=200,
            )
        except Exception as exc:  # noqa: BLE001 — 工具异常收敛为 JSON-RPC 错误，不崩端点
            log.warning("MCP tools/call %s 异常: %s", params.get("name"), exc)
            return JSONResponse(_jsonrpc_error(req_id, _INVALID_PARAMS, f"Tool error: {exc}"), status_code=200)
        return JSONResponse(_jsonrpc_result(req_id, result), status_code=200)

    return JSONResponse(_jsonrpc_error(req_id, _METHOD_NOT_FOUND, f"Method not found: {method}"), status_code=200)


__all__ = ["router", "mcp_enabled"]
