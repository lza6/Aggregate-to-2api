"""api/mcp/server.py — v12.0.0 P1-M1 MCP JSON-RPC 2.0 端点（v16 P0-1 升级 Streamable HTTP）。

POST /v1/mcp：
- initialize           → protocolVersion/capabilities/serverInfo 握手（capabilities.resources/prompts/tools）
- notifications/*      → 202（通知无响应体）
- tools/list           → {tools:[{name,description,inputSchema,annotations}]}
- tools/call           → {content:[{type:"text",text}], isError}
- resources/list       → 只读资源（memory://latest、audit://today、skills://index）
- prompts/list         → 提示词模板（image-from-prompt/dag-explore/cost-review）
- ping                 → {}
- 未知方法             → -32601 method not found
- 参数错误/工具异常    → -32602 invalid params（工具 ValueError 归入此码）
- 解析失败             → -32700 parse error
- 预算超限（P1-9）     → -32000 Budget exceeded（enforce 模式 tools/call 拦截，不抛 500）

Streamable HTTP（v16 P0-1）：
- Accept: application/json, text/event-stream → 响应体按 SSE 分帧（event: message / data: {...}），
  客户端仅 Accept: application/json 时保持单响应 JSON（向后兼容既有调用方）。
- Mcp-Session-Id 会话头：可选无状态会话；缺省不强制（兼容 Keep-alive）。DELETE 谓词结束会话（返回 200）。
- capabilities 声明 resources/prompts/tools（tools 保持向下兼容）。
- 零事件时降级为当前单响应（不破坏既有 5 工具调用方与 SDK）。

鉴权：只读工具走 auth.guard_chat_request（per-IP 限流，公益开放）。
开关：IF_MCP_ENABLED=0（默认）→ 404（config 工厂，setenv+reset_settings 后生效）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .. import auth
from ..errors import AppError, ErrorCodes
from .tools import build_tools, find_tool, tool_annotations

# v18 P1-3：渐进暴露审批状态（内存集；重启后重置为注册表默认——审批流属运行期护栏，
# 持久化可后置为 SQLite（如需跨重启保留）。基础工具 expose=True 恒可见，不受此集影响。
_APPROVED_TOOLS: set[str] = set()


def approve_tool_expose(name: str) -> bool:
    """审批通过：允许该工具对 MCP 客户端可见。返回是否新增。"""
    tool = find_tool(build_tools(), name)
    if tool is None:
        return False
    was = name in _APPROVED_TOOLS
    _APPROVED_TOOLS.add(name)
    return not was


def revoke_tool_expose(name: str) -> bool:
    """回收暴露：隐藏该工具。返回是否命中。"""
    if name not in _APPROVED_TOOLS:
        return False
    _APPROVED_TOOLS.discard(name)
    return True


def _tool_visible(tool, approval_enabled: bool) -> bool:
    """开关关（缺省 0）= 全部工具可见（旧客户端零回归）；开=基础工具 + 已审批新工具。"""
    if not approval_enabled:
        return True
    return bool(tool.expose) or tool.name in _APPROVED_TOOLS

router = APIRouter()
log = logging.getLogger("mcp.server")

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "tingfeng-ai-mcp", "version": "20.3.4"}
_MCP_SESSION_HEADER = "Mcp-Session-Id"


def mcp_enabled() -> bool:
    """IF_MCP_ENABLED 是否开启（config 工厂，缺省 False）。"""
    try:
        from ..config import get_settings

        return bool(get_settings().if_mcp_enabled)
    except Exception:
        return False


def mcp_streamable_enabled() -> bool:
    """IF_MCP_STREAMABLE 是否开启（缺省 True；仅影响 Accept: text/event-stream 时的响应形态，不影响 JSON-RPC 语义）。"""
    try:
        from ..config import get_settings

        return bool(getattr(get_settings(), "if_mcp_streamable", True))
    except Exception:
        return True


# ── v16 P0-1：resources / prompts 能力（只读、零副作用、Mock/聚合信源）──────────


async def _resources_list(_params: dict[str, Any]) -> dict[str, Any]:
    from ..skills.loader import skill_index

    skills = skill_index.all()
    count = len(skills)
    return {
        "resources": [
            {"uri": "memory://latest", "name": "最近记忆（L1/L2 摘要）", "mimeType": "text/markdown"},
            {"uri": "audit://today", "name": "今日审计日志摘要", "mimeType": "text/plain"},
            {"uri": "skills://index", "name": f"技能索引（{count} 个）", "mimeType": "text/plain"},
        ]
    }


async def _prompts_list(_params: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompts": [
            {
                "name": "image-from-prompt",
                "description": "把一句自然语言描述转成生图提示词并生成图片（受控，Mock 优先）",
            },
            {
                "name": "dag-explore",
                "description": "把目标任务拆成 DAG 执行计划（Mock LLM 优先，零付费）",
            },
            {
                "name": "cost-review",
                "description": "回顾今日用量与成本预测，给出节流建议",
            },
        ]
    }


def _jsonrpc_result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# JSON-RPC 2.0 标准错误码
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
# P1-9 预算超限业务码（enforce 模式；约定 -32000 区间为 server 业务错误）
_BUDGET_EXCEEDED = -32000


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
        from ..agent.budget_guard import BudgetExceededError
        from .tools import guard_and_run

        result = await guard_and_run(tool, arguments)
        text = str(result)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except BudgetExceededError as exc:
        raise exc
    except ValueError as exc:
        return {"content": [{"type": "text", "text": f"参数错误：{exc}"}], "isError": True}


def _sse_frame(payload: dict[str, Any]) -> bytes:
    """Streamable HTTP SSE 分帧（2025-06-18）：event: message + data: <json> + 空行。"""
    import json as _json

    data = _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: message\ndata: {data}\n\n".encode()


def _json_response(payload: dict[str, Any], req_id: Any, *, want_stream: bool) -> Response:
    """按客户端 Accept 选择响应形态：SSE 分帧或单响应 JSON（向后兼容）。"""
    if want_stream and mcp_streamable_enabled():
        return StreamingResponse(
            iter([_sse_frame(payload)]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return JSONResponse(payload, status_code=200)


def _wants_sse(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept


@router.post("/v1/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 2.0 单端点（Streamable HTTP：JSON 或 SSE 响应形态）。"""
    if not mcp_enabled():
        raise AppError(ErrorCodes.NOT_FOUND, "MCP 端点已关闭（IF_MCP_ENABLED=0）", 404)
    # 公益开放 + per-IP 限流（与 chat/DAG 同基线）
    auth.guard_chat_request(request)

    want_stream = _wants_sse(request)

    try:
        payload = await request.json()
    except Exception:
        return _json_response(_jsonrpc_error(None, _PARSE_ERROR, "Parse error"), None, want_stream=want_stream)

    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        resp = _jsonrpc_error(
            payload.get("id") if isinstance(payload, dict) else None, _INVALID_REQUEST, "Invalid Request"
        )
        # 通知（无 id）：202 无响应体（即使 want_stream 也保持 202）
        if isinstance(payload, dict) and "id" not in payload:
            return Response(status_code=202)
        return _json_response(resp, payload.get("id") if isinstance(payload, dict) else None, want_stream=want_stream)

    method = str(payload.get("method", ""))
    req_id = payload.get("id")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # 通知（无 id）：202 无响应体
    if "id" not in payload:
        return Response(status_code=202)

    tools_cache = build_tools()

    if method == "initialize":
        return _json_response(
            _jsonrpc_result(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {},
                    },
                    "serverInfo": SERVER_INFO,
                },
            ),
            req_id,
            want_stream=want_stream,
        )

    if method == "ping":
        return _json_response(_jsonrpc_result(req_id, {}), req_id, want_stream=want_stream)

    if method == "resources/list":
        result = await _resources_list(params)
        return _json_response(_jsonrpc_result(req_id, result), req_id, want_stream=want_stream)

    if method == "prompts/list":
        result = await _prompts_list(params)
        return _json_response(_jsonrpc_result(req_id, result), req_id, want_stream=want_stream)

    if method == "tools/list":
        approval_enabled = False
        try:
            from ..config import get_settings

            approval_enabled = bool(get_settings().if_mcp_tool_approval)
        except Exception:  # noqa: BLE001
            approval_enabled = False
        return _json_response(
            _jsonrpc_result(
                req_id,
                {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                            # P1-7：intent 映射完整 annotations（readOnlyHint 兼容旧客户端）
                            "annotations": tool_annotations(t),
                        }
                        for t in tools_cache
                        if _tool_visible(t, approval_enabled)
                    ]
                },
            ),
            req_id,
            want_stream=want_stream,
        )

    if method == "tools/call":
        try:
            from ..agent.budget_guard import BudgetExceededError

            result = await _handle_tools_call(params)
        except BudgetExceededError as exc:
            # P1-9：enforce 超预算 → MCP JSON-RPC 错误（-32000 业务码 + 402 语义；不抛 500）
            log.warning("MCP tools/call %s 预算拦截（402）: %s", params.get("name"), exc.message)
            return _json_response(
                _jsonrpc_error(req_id, _BUDGET_EXCEEDED, f"Budget exceeded: {exc.message}"),
                req_id,
                want_stream=want_stream,
            )
        except KeyError:
            return _json_response(
                _jsonrpc_error(req_id, _INVALID_PARAMS, f"Unknown tool: {params.get('name', '')}"),
                req_id,
                want_stream=want_stream,
            )
        except Exception as exc:  # noqa: BLE001 — 工具异常收敛为 JSON-RPC 错误，不崩端点
            log.warning("MCP tools/call %s 异常: %s", params.get("name"), exc)
            return _json_response(
                _jsonrpc_error(req_id, _INVALID_PARAMS, f"Tool error: {exc}"),
                req_id,
                want_stream=want_stream,
            )
        return _json_response(_jsonrpc_result(req_id, result), req_id, want_stream=want_stream)

    return _json_response(
        _jsonrpc_error(req_id, _METHOD_NOT_FOUND, f"Method not found: {method}"),
        req_id,
        want_stream=want_stream,
    )


@router.delete("/v1/mcp")
async def mcp_endpoint_delete(request: Request):
    """Streamable HTTP 会话结束（2025-06-18）：DELETE 谓词，返回 200。"""
    if not mcp_enabled():
        raise AppError(ErrorCodes.NOT_FOUND, "MCP 端点已关闭（IF_MCP_ENABLED=0）", 404)
    auth.guard_chat_request(request)
    # 无状态会话：收到 DELETE 即视为会话结束，无需清理；保留 request 引用防未用告警
    _ = request
    return Response(status_code=200)


__all__ = ["router", "mcp_enabled"]
