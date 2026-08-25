"""本地 mock cf_solver：模拟 Turnstile 求解服务的 HTTP 契约，供 E2E/集成测试零上游消耗验证。

契约对齐真实 cf_solver（见 api/turnstile_client.py 与 deploy/cf_solver/api_server.py）：
  GET /turnstile?url=&sitekey=[&proxy=]  → 202 {task_id, status:"accepted"}
  GET /result?id=<task_id>               → 200 {status:"success", value:<token>, elapsed_time}
                                        → 202 {status:"process"}（求解中）
                                        → 404 未知 id 或 expired
                                        → 408 {status:"error", value:"timeout"}（超时）
                                        → 422 {status:"error", value:"captcha_fail"}（求解失败）

增强特性：
  - 支持自定义延时模式（--delay / POST /__config?delay=...）
  - 支持多节点 Mock 启动（--node-id / --port），便于本地验证多求解器联邦轮询/集群负载均衡
  - 故障注入（验证熔断/降级/重试路径）:
    POST /__fault?mode=fail       → 求解失败 (422 captcha_fail)
    POST /__fault?mode=timeout    → 模拟超时 (408 timeout)
    POST /__fault?mode=down       → /turnstile 返回 503
    POST /__fault?mode=ok         → 恢复正常

用法：
  python scripts/mock_cfsolver.py [--port 8001] [--node-id node-1] [--delay 0.1]
"""
import argparse
import asyncio
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Mock Turnstile Solver")

_state = {
    "fault": "ok",          # ok | fail | timeout | down
    "delay": 0.2,           # 默认模拟求解延迟（秒）
    "node_id": "node-default"
}
_results: dict[str, dict] = {}


@app.get("/turnstile")
async def turnstile(request: Request, url: str = "", sitekey: str = "", proxy: str = None):
    if _state["fault"] == "down":
        return JSONResponse(status_code=503, content={"error": f"mock solver ({_state['node_id']}) down"})
    task_id = str(uuid.uuid4())
    start_time = time.time()
    _results[task_id] = {
        "status": "process",
        "message": "solving turnstile",
        "start_time": start_time,
        "node_id": _state["node_id"]
    }
    # 模拟真实求解耗时（异步并发，不阻塞事件循环）
    asyncio.create_task(_resolve(task_id, start_time))
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "accepted"})


async def _resolve(task_id: str, start_time: float) -> None:
    delay = float(_state.get("delay", 0.2))
    if delay > 0:
        await asyncio.sleep(delay)

    elapsed = round(time.time() - start_time, 3)
    fault = _state["fault"]

    if fault == "fail":
        _results[task_id] = {
            "status": "error",
            "elapsed_time": elapsed,
            "value": "captcha_fail",
            "node_id": _state["node_id"]
        }
    elif fault == "timeout":
        _results[task_id] = {
            "status": "error",
            "elapsed_time": elapsed,
            "value": "timeout",
            "message": "Tugas timeout",
            "node_id": _state["node_id"]
        }
    else:
        _results[task_id] = {
            "status": "success",
            "value": f"mock-token-{_state['node_id']}-{task_id[:8]}",
            "elapsed_time": elapsed,
            "node_id": _state["node_id"]
        }


@app.get("/result")
async def result(id: str):
    if not id or id not in _results:
        return JSONResponse(status_code=404, content={"status": "error", "message": "task_id tidak valid atau sudah expired"})

    res = _results.get(id)
    if res.get("status") == "process":
        return JSONResponse(status_code=202, content=res)

    # 终态取走（与部署版 api_server.py get_result 行为一致）
    res = _results.pop(id)
    if res.get("status") == "success":
        return JSONResponse(status_code=200, content=res)
    elif res.get("value") == "timeout":
        return JSONResponse(status_code=408, content=res)
    else:
        return JSONResponse(status_code=422, content=res)


@app.post("/__fault")
async def set_fault(mode: str):
    if mode not in ("ok", "fail", "timeout", "down"):
        return JSONResponse(status_code=400, content={"error": "mode must be ok|fail|timeout|down"})
    _state["fault"] = mode
    return JSONResponse(status_code=200, content={"fault": mode, "node_id": _state["node_id"]})


@app.post("/__config")
async def set_config(delay: float = None, node_id: str = None):
    if delay is not None:
        _state["delay"] = max(0.0, float(delay))
    if node_id is not None:
        _state["node_id"] = str(node_id)
    return JSONResponse(status_code=200, content={"status": "ok", "state": _state})


@app.get("/__status")
async def get_status():
    return JSONResponse(status_code=200, content={"state": _state, "pending_count": len(_results)})


def main():
    ap = argparse.ArgumentParser(description="Mock Cloudflare Turnstile Solver Server")
    ap.add_argument("--port", type=int, default=8001, help="Port to listen on (default: 8001)")
    ap.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    ap.add_argument("--delay", type=float, default=0.2, help="Simulated solving delay in seconds (default: 0.2)")
    ap.add_argument("--node-id", type=str, default="node-1", help="Mock Node Identifier (default: node-1)")
    args = ap.parse_args()

    _state["delay"] = args.delay
    _state["node_id"] = args.node_id

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"[mock_cfsolver] node={args.node_id} delay={args.delay}s listening http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
