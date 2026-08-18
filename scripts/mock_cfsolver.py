"""本地 mock cf_solver：模拟 Turnstile 求解服务的 HTTP 契约，供 E2E/集成测试零上游消耗验证。

契约对齐真实 cf_solver（见 api/turnstile_client.py）：
  GET /turnstile?url=&sitekey=[&proxy=]  → 202 {task_id, status:"accepted"}
  GET /result?id=<task_id>               → 200 {status:"success", value:<token>, elapsed_time}
                                        → 404 未知 id
                                        → 422 {status:"failed"}（故障注入时）

故障注入（验证熔断/降级路径）：
  POST /__fault?mode=fail       → 之后所有求解返回 422 failed（模拟 cf_solver 故障）
  POST /__fault?mode=ok         → 恢复正常求解
  POST /__fault?mode=down       → 之后 /turnstile 返回 503（模拟服务不可用）

用法：python scripts/mock_cfsolver.py [--port 8001]
"""
import argparse
import asyncio
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

_state = {"fault": "ok"}          # ok | fail | down
_results: dict[str, dict] = {}


@app.get("/turnstile")
async def turnstile(request: Request):
    if _state["fault"] == "down":
        return JSONResponse(status_code=503, content={"error": "mock solver down"})
    task_id = uuid.uuid4().hex
    _results[task_id] = {"id": task_id, "status": "pending", "created": time.time()}
    # 模拟真实求解耗时（异步，不阻塞事件循环）
    asyncio.create_task(_resolve(task_id))
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "accepted"})


async def _resolve(task_id: str) -> None:
    await asyncio.sleep(0.3)  # 模拟 ~300ms 求解耗时
    if _state["fault"] == "fail":
        _results[task_id] = {"id": task_id, "status": "failed", "error": "mock captcha_fail"}
    else:
        _results[task_id] = {
            "id": task_id, "status": "success", "value": f"mock-token-{task_id}",
            "elapsed_time": 0.3,
        }


@app.get("/result")
async def result(id: str):
    r = _results.get(id)
    if r is None:
        return JSONResponse(status_code=404, content={"status": "expired"})
    if r["status"] == "success":
        return JSONResponse(status_code=200, content=r)
    if r["status"] == "failed":
        return JSONResponse(status_code=422, content=r)
    return JSONResponse(status_code=202, content=r)  # pending


@app.post("/__fault")
async def fault(mode: str):
    if mode not in ("ok", "fail", "down"):
        return JSONResponse(status_code=400, content={"error": "mode must be ok|fail|down"})
    _state["fault"] = mode
    return JSONResponse(status_code=200, content={"fault": mode})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"[mock_cfsolver] listening :{args.port} state=ok", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
