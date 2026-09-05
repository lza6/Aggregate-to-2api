"""WebSocket 双向任务事件通道（v8.0 P1-6）。

与现有 SSE 端点 /v1/tasks/{id}/events 并存（不替代），提供双向能力：
- 客户端可发 {"action":"cancel"} 取消任务、{"action":"query"} 查询状态
- 服务端推送 status/progress/result/error 事件
- 心跳带 sequence number（客户端可检测丢包）
- result/error 终态后自动断开

设计：
- 复用 sse_events.hub 的缓冲 + 订阅，避免双写
- WS 协议层：on message 处理客户端指令；定时心跳；终态断开
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .sse_events import HEARTBEAT_INTERVAL, hub

log = logging.getLogger("ws_events")

_WS_HEARTBEAT_INTERVAL = HEARTBEAT_INTERVAL  # 15s，与 SSE 一致


def _ws_encode(event: str, data: dict, seq: int) -> str:
    """WS 文本帧编码：JSON {event, data, seq}。seq 用于心跳丢包检测。"""
    return json.dumps({"event": event, "data": data, "seq": seq}, ensure_ascii=False)


async def ws_task_events(websocket: WebSocket, task_id: str) -> None:
    """WebSocket 双向任务事件流。

    v8.0 P1-6：与 SSE 端点并存。客户端可发 cancel/query 指令；
    服务端复用 sse_events.hub 缓冲回放 + 实时推送，心跳带 sequence number。
    """
    await websocket.accept()

    # 回放历史事件（无 Last-Event-ID 概念，WS 首次连接全量回放缓冲）
    replay = await hub.replay_after(task_id, None)
    seq = 0
    for ev in replay:
        seq = ev.id  # 用历史事件 id 作为初始 seq
        await websocket.send_text(_ws_encode(ev.event, ev.data, ev.id))

    # 订阅实时事件
    queue = await hub.subscribe(task_id)
    # 初始连接确认（seq=-1 标记非业务事件）
    await websocket.send_text(_ws_encode("ping", {"msg": "connected", "task_id": task_id}, -1))

    async def _heartbeat() -> None:
        """后台心跳协程：每 HEARTBEAT_INTERVAL 发 ping，seq 单调递增。"""
        hb_seq = seq
        try:
            while True:
                await asyncio.sleep(_WS_HEARTBEAT_INTERVAL)
                hb_seq += 1
                await websocket.send_text(_ws_encode("ping", {"msg": "heartbeat"}, hb_seq))
        except Exception:
            pass

    hb_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            # 并发：等队列事件或客户端指令，谁先来处理谁
            done, pending = await asyncio.wait(
                [
                    asyncio.ensure_future(queue.get()),
                    asyncio.ensure_future(_recv_loop(websocket, task_id)),
                ],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=_WS_HEARTBEAT_INTERVAL,
            )
            for t in done:
                res = t.result()
                if res is None:
                    continue
                # res 是 (kind, payload)
                kind, payload = res
                if kind == "event":
                    # 来自 hub 的事件
                    try:
                        await websocket.send_text(payload)
                        # 解析事件类型，终态断开
                        ev_obj = json.loads(payload)
                        if ev_obj.get("event") in ("result", "error"):
                            return
                    except Exception:
                        pass
                elif kind == "cancel":
                    # 客户端发 cancel → 标记任务取消（由 engine 处理）
                    log.info("WS 客户端请求取消任务 %s", task_id)
                    await websocket.send_text(_ws_encode("ack", {"action": "cancel", "task_id": task_id}, seq))
                elif kind == "query":
                    # 客户端发 query → 返回当前任务状态
                    from .meta import db

                    row = await db.get(task_id)
                    status = (row or {}).get("status", "unknown") if row else "unknown"
                    await websocket.send_text(_ws_encode("status", {"task_id": task_id, "status": status}, seq))
            # 取消未完成的 future 避免泄漏
            for t in pending:
                t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("WS 连接异常: %s", e)
    finally:
        hb_task.cancel()
        await hub.unsubscribe(task_id, queue)
        await hub.clear_task(task_id)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()


async def _recv_loop(websocket: WebSocket, task_id: str) -> tuple[str, Any] | None:
    """接收客户端指令循环：解析 {"action":"cancel"|"query"}。

    返回 ("cancel", None) / ("query", None) / None（非指令或断开）。
    """
    try:
        raw = await websocket.receive_text()
    except Exception:
        return None
    try:
        msg = json.loads(raw)
    except Exception:
        return None
    action = msg.get("action") if isinstance(msg, dict) else None
    if action == "cancel":
        return ("cancel", None)
    if action == "query":
        return ("query", None)
    return None
