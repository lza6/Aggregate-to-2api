"""api/mcp/ — v12.0.0 P1-M1 MCP（Model Context Protocol）协议化层。

把主项目能力以 MCP 工具形式暴露给外部 agent（JSON-RPC 2.0 over HTTP POST）：
- POST /v1/mcp   单端点 JSON-RPC 2.0（initialize / tools/list / tools/call / ping）

工具集（v12.0.0 最小闭环，Q3 边界：只读 + 受控生图）：
- skills_list / skills_get / dag_plan / dag_status：只读（公益开放 + per-IP 限流）
- generate_image：受控生图（Mock 优先，付费红线：IF_MOCK_UPSTREAM=1 时零真实付费）

安全边界（对齐 OWASP-MCP hard-gate 思想）：
- 开关 IF_MCP_ENABLED（config 工厂，缺省 False——新功能缺省关）
- 只读工具走 guard_chat_request（per-IP 限流）
- 无写/删/管理类工具（v12.0.0 不暴露）
"""

from .server import mcp_enabled, router

__all__ = ["router", "mcp_enabled"]
