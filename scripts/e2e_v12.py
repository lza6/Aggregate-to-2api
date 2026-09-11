"""scripts/e2e_v12.py — v12.0.0 真实 E2E 验收（付费红线：全程 IF_MOCK_UPSTREAM=1）。

一体化探针：启动 mock cf_solver + uvicorn → wait_port → 真实 HTTP 断言 → 清理进程。
覆盖端点：
1. GET  /healthz                       基础健康
2. GET  /openapi.json                  openapi version == 12.0.0（版本全链）
3. GET  /v1/agent/skills               技能清单含 ecommerce/ppt 新场景
4. GET  /v1/agent/skills/{name}        单技能详情（v12.0.0 新增）
5. POST /v1/mcp initialize             MCP 握手（v12.0.0 新增）
6. POST /v1/mcp tools/list             5 工具白名单
7. POST /v1/mcp tools/call skills_list / dag_plan / generate_image（Mock）
8. POST /v1/agent/dag/plan             Mock 规划（含 critic 终检节点）
9. POST /v1/agent/dag/run + 轮询       真实 DAG run 至终态 succeeded
10. POST /v1/mcp 未知工具 -32602        协议错误路径
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

ROOT = r"C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\imagefree-2ai"
API_PORT = 8103
SOLVER_PORT = 8002
BASE = f"http://127.0.0.1:{API_PORT}"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(f"{name}{(': ' + detail) if detail and not cond else ''}")
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name}" + (f" -- {detail}" if detail and not cond else ""))


def wait_port(port: int, timeout: float = 30.0) -> bool:
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> int:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "IF_MOCK_UPSTREAM": "1",  # 付费红线：全程 Mock
            "IF_MCP_ENABLED": "1",  # E2E 显式开启 MCP（默认关）
            "IF_AGENT_DAG_ENABLED": "1",
            "IF_AGENT_SKILLS_ENABLED": "1",
            "IF_REQUESTS_PER_MINUTE": "0",  # E2E 关闭 per-IP 限流
            "IF_DAG_REQUESTS_PER_MINUTE": "0",
            "IF_DB_FILE": os.path.join(ROOT, "data", "e2e_v12.db"),
        }
    )
    solver = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "scripts", "mock_cfsolver.py"), "--port", str(SOLVER_PORT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ok = wait_port(SOLVER_PORT) and wait_port(API_PORT)
        print(f"[e2e-v12] solver:8002={wait_port(SOLVER_PORT)} api:8103={wait_port(API_PORT)}")
        if not ok:
            print("[e2e-v12] 服务启动超时")
            return 1
        client = httpx.Client(base_url=BASE, timeout=30.0)

        # 1. 健康与版本全链
        r = client.get("/v1/healthz")
        check("1 /v1/healthz 200", r.status_code == 200)
        r = client.get("/openapi.json")
        ver = r.json().get("info", {}).get("version", "")
        check("2 openapi version==12.0.0", ver == "12.0.0", f"got {ver}")

        # 3-4. skills 可发现性
        r = client.get("/v1/agent/skills")
        data = r.json()
        names = {i["name"] for g in data["items"].values() for i in g}
        check(
            "3 skills 清单含新场景",
            "ecommerce-visual-copywriting" in names and "ppt-outline-gen" in names,
            f"names={sorted(names)}",
        )
        r = client.get("/v1/agent/skills/ecommerce-visual-copywriting")
        check("4 单技能详情 200+body", r.status_code == 200 and "转化驱动力" in r.json().get("body", ""))

        # 5-7. MCP
        r = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        ok5 = r.status_code == 200 and r.json()["result"]["serverInfo"]["version"] == "12.0.0"
        check("5 mcp initialize", ok5)
        r = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"] for t in r.json()["result"]["tools"]}
        check(
            "6 mcp tools/list 白名单",
            tools == {"skills_list", "skills_get", "dag_plan", "dag_status", "generate_image"},
            f"got {tools}",
        )
        r = client.post(
            "/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "dag_plan", "arguments": {"prompt": "画一只赛博猫"}},
            },
        )
        ok7 = r.status_code == 200 and r.json()["result"]["isError"] is False
        check("7 mcp tools/call dag_plan(mock)", ok7)

        # 8. DAG plan
        r = client.post("/v1/agent/dag/plan", json={"prompt": "生成一张电商主图", "scene": "ecommerce"})
        plan = r.json()
        kinds = [n["kind"] for n in plan["nodes"]]
        check(
            "8 dag/plan mock 含 critic",
            r.status_code == 200 and plan["meta"]["mock"] and "critic" in kinds,
            f"kinds={kinds}",
        )

        # 9. DAG run 真实执行至终态
        r = client.post(
            "/v1/agent/dag/run",
            json={
                "name": "e2e-v12",
                "fail_fast": False,
                "nodes": [
                    {"id": "s1", "kind": "scene", "depends_on": [], "prompt": "电商主图"},
                    {"id": "g1", "kind": "llm", "depends_on": ["s1"], "prompt": "生成主图"},
                    {"id": "c1", "kind": "critic", "depends_on": ["g1"], "prompt": "终检"},
                ],
            },
        )
        run_id = r.json().get("run_id", "")
        check("9a dag/run 提交", bool(run_id), f"resp={r.json()}")
        final = None
        for _ in range(40):
            time.sleep(0.5)
            g = client.get(f"/v1/agent/dag/{run_id}").json()
            if g.get("status") in ("succeeded", "failed", "partial"):
                final = g
                break
        node_status = {n["id"]: n["status"] for n in (final or {}).get("nodes", [])}
        check("9b dag/run 全节点 succeeded", (final or {}).get("status") == "succeeded", f"{node_status}")

        # 10. 协议错误路径
        r = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "nope"}})
        check("10 mcp 未知工具 -32602", r.json().get("error", {}).get("code") == -32602)

        # MCP generate_image mock
        r = client.post(
            "/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": "generate_image", "arguments": {"prompt": "测试"}},
            },
        )
        ok11 = r.status_code == 200 and "image-mock" in r.json()["result"]["content"][0]["text"]
        check("11 mcp generate_image mock 占位", ok11)

        client.close()
    finally:
        for p in (api, solver):
            p.terminate()
        for p in (api, solver):
            try:
                p.wait(timeout=8)
            except Exception:
                p.kill()

    print(f"\n[e2e-v12] PASS={len(PASS)} FAIL={len(FAIL)}")
    for f in FAIL:
        print("  FAILED:", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
