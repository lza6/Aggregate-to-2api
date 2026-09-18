"""MCP 工具渐进暴露审批端点（指南 v18 P1-3，smart-mcp-proxy 对标）。

端点（均 admin key）：
- GET    /v1/admin/mcp-tools                      工具清单（含 expose 状态）
- POST   /v1/admin/mcp-tools/{name}/expose        审批通过（对新工具对 MCP 客户端可见）
- POST   /v1/admin/mcp-tools/{name}/hide          回收暴露
开关：IF_MCP_TOOL_APPROVAL=1 时 tools/list 过滤 expose=False 且未审批工具（=0 全可见零回归）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import auth
from ..mcp.tools import build_tools, find_tool

router = APIRouter()
log = logging.getLogger("mcp.admin")


@router.get("/v1/admin/mcp-tools")
async def list_mcp_tools(request: Request):
    """工具清单（含 expose 状态与意图），供审批面板。"""
    auth.check_admin_key(request, scope="admin-mcp")
    from ..config import get_settings
    from ..mcp.server import _APPROVED_TOOLS, _tool_visible

    approval = bool(get_settings().if_mcp_tool_approval)
    tools = build_tools()
    return {
        "ok": True,
        "approval_enabled": approval,
        "count": len(tools),
        "items": [
            {
                "name": t.name,
                "description": t.description,
                "intent": t.intent,
                "expose": t.expose,
                "visible": _tool_visible(t, approval),
                "approved": t.name in _APPROVED_TOOLS,
            }
            for t in tools
        ],
    }


@router.post("/v1/admin/mcp-tools/{name}/expose")
async def expose_tool(name: str, request: Request):
    """审批通过：允许工具对 MCP 客户端可见。"""
    auth.check_admin_key(request, scope="admin-mcp")
    if find_tool(build_tools(), name) is None:
        raise HTTPException(status_code=404, detail=f"未知工具: {name}")
    from ..mcp.server import approve_tool_expose

    is_new = approve_tool_expose(name)
    return {"ok": True, "name": name, "approved": True, "changed": is_new}


@router.post("/v1/admin/mcp-tools/{name}/hide")
async def hide_tool(name: str, request: Request):
    """回收暴露。"""
    auth.check_admin_key(request, scope="admin-mcp")
    from ..mcp.server import revoke_tool_expose

    ok = revoke_tool_expose(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"工具未在审批集或不存在: {name}")
    return {"ok": True, "name": name, "approved": False}
