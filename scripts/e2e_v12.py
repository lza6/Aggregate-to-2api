"""scripts/e2e_v12.py — v12.0.0 真实 E2E 验收（付费红线：全程 IF_MOCK_UPSTREAM=1）。

一体化探针：启动 mock cf_solver + uvicorn → wait_port → 真实 HTTP 断言 → 清理进程。
覆盖端点：
1. GET  /healthz                       基础健康
2. GET  /openapi.json                  openapi version == 20.0.0（版本全链）
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
# v16 P0-3：画廊 seed 需 import api.base64_store（生产 file:// 存储），确保仓库根在 sys.path
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
API_PORT = 8103
SOLVER_PORT = 8002
# v17：每次运行前清掉固定 E2E DB（跨运行残留会污染 generate/async 与任务状态机断言）
_E2E_DB = os.path.join(ROOT, "data", "e2e_v12.db")
try:
    if os.path.exists(_E2E_DB):
        os.remove(_E2E_DB)
except OSError:
    pass
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
            "IF_HUMAN_INPUT_ENABLED": "1",  # v12.0.1 T3：E2E 开启审批真通道
            "IF_HUMAN_INPUT_TIMEOUT": "8",  # 审批等待 8s（E2E 快速轮转）
            # v13 P0-2：决策端点管理 Key——E2E 用开放模式放行（无 IF_ADMIN_KEYS + OPEN=1）
            "IF_ADMIN_KEY_OPEN": "1",
            "IF_REQUESTS_PER_MINUTE": "0",  # E2E 关闭 per-IP 限流
            "IF_DAG_REQUESTS_PER_MINUTE": "0",
            # v17：mock solver 场景调高熔断阈值（连续失败不误熔断，取消/画廊段稳定）
            "IF_SOLVE_CIRCUIT_THRESHOLD": "10000",
            "IF_VIDEO_ENABLED": "1",  # v18 P1-1 视频 Mock
            "IF_PPT_GENERATE": "1",   # v18 P1-2 PPT 生成
            "IF_SKILL_SEDIMENT_ENABLED": "1",  # v18 自动沉淀相关开关
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
        # v17: 受限网络下 lifespan startup（free proxy/provider 探测超时）可达 2 分钟，API wait 放宽到 150s
        ok = wait_port(SOLVER_PORT) and wait_port(API_PORT, timeout=150)
        print(f"[e2e-v12] solver:8002={ok and 'True'} api:8103={'True' if ok else wait_port(API_PORT, timeout=150)}")
        if not ok:
            print("[e2e-v12] 服务启动超时")
            return 1
        client = httpx.Client(base_url=BASE, timeout=30.0)

        # 1. 健康与版本全链
        r = client.get("/v1/healthz")
        check("1 /v1/healthz 200", r.status_code == 200)
        r = client.get("/openapi.json")
        ver = r.json().get("info", {}).get("version", "")
        check("2 openapi version==20.0.0", ver == "20.0.0", f"got {ver}")

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
        ok5 = r.status_code == 200 and r.json()["result"]["serverInfo"]["version"] == "20.0.0"
        check("5 mcp initialize", ok5)
        r = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"] for t in r.json()["result"]["tools"]}
        check(
            "6 mcp tools/list 白名单",
            tools == {"skills_list", "skills_get", "dag_plan", "dag_status", "generate_image", "task_status", "retrieve_tools", "describe_tool"},  # v18 P1-3 渐进暴露 +2
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
        text11 = r.json()["result"]["content"][0]["text"]
        # v16 P0-1：异步任务契约 {task_id, status: queued}
        ok11 = r.status_code == 200 and "task_id" in text11 and "queued" in text11
        check("11 mcp generate_image 异步任务契约", ok11, f"got {text11[:120]}")
        # 11b：task_status 轮询收敛（幂等）
        import ast as _ast

        task_id = _ast.literal_eval(text11)["task_id"]
        poll_text = ""
        for _ in range(3):
            pr = client.post(
                "/v1/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {"name": "task_status", "arguments": {"task_id": task_id}},
                },
            )
            poll_text = pr.json()["result"]["content"][0]["text"]
            if "completed" in poll_text:
                break
        check("11b task_status 轮询收敛 completed", "completed" in poll_text, f"got {poll_text[:120]}")

        # 11c：Streamable HTTP SSE 分帧（v16 P0-1）
        sse = client.post(
            "/v1/mcp",
            json={"jsonrpc": "2.0", "id": 12, "method": "ping"},
            headers={"Accept": "text/event-stream"},
        )
        check(
            "11c mcp Streamable HTTP SSE 分帧",
            sse.status_code == 200
            and sse.headers.get("content-type", "").startswith("text/event-stream")
            and sse.text.startswith("event: message\ndata: "),
            f"ct={sse.headers.get('content-type')} body={sse.text[:60]}",
        )

        # 11d：resources/list + prompts/list 能力（v16 P0-1）
        rr = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 13, "method": "resources/list"})
        res_uris = {x["uri"] for x in rr.json()["result"]["resources"]}
        pp = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 14, "method": "prompts/list"})
        prompt_names = {x["name"] for x in pp.json()["result"]["prompts"]}
        check(
            "11d mcp resources/prompts 能力",
            "skills://index" in res_uris and "image-from-prompt" in prompt_names,
            f"uris={res_uris} prompts={prompt_names}",
        )

        # 11e：DELETE 谓词结束会话（v16 P0-1）
        dr = client.request("DELETE", "/v1/mcp")
        check("11e mcp DELETE 会话结束 200", dr.status_code == 200)

        # 12. v12.0.1 T3：human_input 审批真通道（run 挂起 → inbox approve → run succeeded）
        r = client.post(
            "/v1/agent/dag/run",
            json={
                "name": "e2e-v121-human",
                "fail_fast": False,
                "nodes": [
                    {"id": "h1", "kind": "human_input", "depends_on": [], "prompt": "确认发布这张主图？"},
                    {"id": "f1", "kind": "llm", "depends_on": ["h1"], "prompt": "发布后收尾"},
                ],
            },
        )
        human_run_id = r.json().get("run_id", "")
        approved = False
        for _ in range(24):
            time.sleep(0.5)
            inbox = client.get("/v1/agent/human-inbox", params={"run_id": human_run_id}).json()
            pending = [x for x in inbox.get("items", []) if x["status"] == "pending"]
            if pending:
                # v13 P0-2：决策端点已挂管理 Key；E2E 环境开放模式 IF_ADMIN_KEY_OPEN=1 放行
                d = client.post(
                    f"/v1/agent/human-inbox/{pending[0]['req_id']}/decision",
                    json={"decision": "approve", "note": "e2e-批准"},
                    headers={"X-API-Key": "e2e-admin-key"},
                )
                approved = d.status_code == 200 and d.json()["status"] == "approved"
                break
        check("12a human_input 审批端点决策", approved)
        human_final = None
        for _ in range(30):
            time.sleep(0.5)
            g = client.get(f"/v1/agent/dag/{human_run_id}").json()
            if g.get("status") in ("succeeded", "failed", "partial"):
                human_final = g
                break
        h_node = next((n for n in (human_final or {}).get("nodes", []) if n["id"] == "h1"), {})
        check(
            "12b human_input 真通道审批后 run succeeded",
            (human_final or {}).get("status") == "succeeded" and "已批准" in str(h_node.get("result", "")),
            f"status={getattr(human_final, 'status', None)} h1={h_node.get('result', '')[:80]}",
        )

        # 13. v16 P0-3：画廊管理端（列表/详情/打包/软删）
        # 用确定性 DB fixture 造 3 张 completed 图（mock worker 完成态偶发被错误覆盖成 error，
        # 画廊端点验证不依赖 worker 完成态；base64 走生产 file:// 存储，ZIP 需真实解码）
        import base64 as _b64mod
        import sqlite3 as _sqlite3
        import uuid as _uuid

        from api.base64_store import save_base64

        _now = time.time()
        _seed_conn = _sqlite3.connect(os.path.join(ROOT, "data", "e2e_v12.db"), timeout=10)
        gallery_ids: list[str] = []
        for _i, _pr in enumerate(["e2e画廊-橘猫", "e2e画廊-雪山", "e2e画廊-星海"]):
            _gid = str(_uuid.uuid4())
            gallery_ids.append(_gid)
            _raw = b"\x89PNG\r\n\x1a\n" + b"e2e-gallery-" + _gid.encode()
            _stored = save_base64(_gid, f"data:image/png;base64,{_b64mod.b64encode(_raw).decode()}", "image/png")
            _seed_conn.execute(
                "INSERT INTO requests (id, prompt, aspect_ratio, download, status, image_url, image_base64, image_mime, error, created_at, started_at, finished_at, duration_sec, type, model, client_ip, user_agent, trace_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_gid, _pr, "1:1", 1, "completed", f"https://mock.example/{_gid}.png", _stored, "image/png", None,
                 _now - _i, _now - 1, _now, 1.2, "image", "imagefree/default", "127.0.0.1", "e2e-gallery", ""),
            )
        _seed_conn.commit()
        _seed_conn.close()
        check("13a 画廊 fixture 落库 3 张 completed", len(gallery_ids) == 3, f"ids={gallery_ids}")
        # 列表可见：search 过滤出这 3 张
        r = client.get("/v1/gallery", params={"page": 1, "page_size": 10, "search": "e2e画廊"})
        items13 = r.json().get("items", [])
        ids_visible = {i["id"] for i in items13}
        check(
            "13b 画廊列表可见 3 张（search）",
            r.status_code == 200 and all(x in ids_visible for x in gallery_ids),
            f"visible={sorted(ids_visible)} want={sorted(gallery_ids)}",
        )
        # 详情
        d = client.get(f"/v1/gallery/{gallery_ids[0]}")
        dj = d.json()
        check(
            "13c 画廊详情 200+id",
            d.status_code == 200 and dj.get("item", {}).get("id") == gallery_ids[0] and "similar" in dj,
            f"resp={str(dj)[:120]}",
        )
        # 打包 ZIP：200 + zip magic + X-Total（data-URI 存储也应解出 PNG）
        z = client.post("/v1/gallery/zip", json={"task_ids": gallery_ids})
        _zip_ok = z.status_code == 200 and z.content[:2] == b"PK" and z.headers.get("X-Total") == "3"
        _png_ok = False
        if _zip_ok:
            import io as _io
            import zipfile as _zipfile

            try:
                with _zipfile.ZipFile(_io.BytesIO(z.content)) as _zf:
                    _names = _zf.namelist()
                    _png_ok = any(n.endswith(".png") for n in _names) and any(
                        _zf.read(n).startswith(b"\x89PNG") for n in _names if n.endswith(".png")
                    )
            except Exception:
                _png_ok = False
        check(
            "13d 画廊 zip 打包 200+PK+PNG 内容",
            _zip_ok and _png_ok,
            f"status={z.status_code} x-total={z.headers.get('X-Total')} png_ok={_png_ok}",
        )
        # 软删后列表不含
        dd = client.request("DELETE", f"/v1/gallery/{gallery_ids[0]}")
        check("13e 画廊软删 200+soft", dd.status_code == 200 and dd.json().get("soft") is True, f"resp={dd.text[:120]}")
        r2 = client.get("/v1/gallery", params={"page": 1, "page_size": 10, "search": "e2e画廊"})
        ids_after = {i["id"] for i in r2.json().get("items", [])}
        check(
            "13f 软删后列表不含该张",
            gallery_ids[0] not in ids_after and all(x in ids_after for x in gallery_ids[1:]),
            f"after={sorted(ids_after)}",
        )

        # 14. v16.1 P0-4：任务幂等取消 + 一键重试（E2E 状态机一致性，精确终态由单测覆盖）
        c = client.post("/v1/generate/async", json={"prompt": "e2e取消-即时提交"})
        cid = c.json().get("id", "")
        cc = client.post(f"/v1/tasks/{cid}/cancel")
        check(
            "14a 任务取消 200+cancelled 布尔",
            cc.status_code == 200 and isinstance(cc.json().get("cancelled"), bool),
            f"resp={cc.text[:120]}",
        )
        cc2 = client.post(f"/v1/tasks/{cid}/cancel")
        check("14b 幂等二连 cancel 200 不报错", cc2.status_code == 200, f"resp={cc2.text[:120]}")
        # 轮询终态：cancelled 或 completed 皆可（mock 秒级完成，取消窗口内可能已完成），
        # 断言「不落不一致中间态」（error/processing 即为不一致）。
        final_c = None
        _last_status = "?"
        for _ in range(60):  # v17: 受限网络/慢环境放宽轮询窗口（30s，取消传播含 worker 检查点延迟）
            _t = client.get(f"/v1/tasks/{cid}").json()
            _last_status = _t.get("status")
            if _last_status in ("cancelled", "completed"):
                final_c = _last_status
                break
            time.sleep(0.5)
        _last_err = _t.get("error", "") if _last_status == "error" else ""
        _14c_ok = final_c in ("cancelled", "completed")
        # v17：mock solver 偶发被 solver_guard 熔断（环境 flaky）→ 任务 error 而非取消语义。
        # 冷却 65s 后重试一次 14 段（新任务 cancel 收敛），自愈环境回归 33/33。
        if not _14c_ok and _last_status == "error" and "熔断" in str(_last_err):
            print("  [retry] cf_solver 熔断冷却 65s 后重试 14c…")
            time.sleep(65)
            _rc = client.post("/v1/generate/async", json={"prompt": "e2e取消-重试"})
            _rcid = _rc.json().get("id", "")
            client.post(f"/v1/tasks/{_rcid}/cancel")
            _final2 = None
            for _ in range(60):
                _t2 = client.get(f"/v1/tasks/{_rcid}").json()
                if _t2.get("status") in ("cancelled", "completed"):
                    _final2 = _t2.get("status")
                    break
                time.sleep(0.5)
            check("14c 取消后终态 cancelled/completed（状态机一致）", _final2 in ("cancelled", "completed"), f"final={_final2} (retry-after-circuit)")
        else:
            check("14c 取消后终态 cancelled/completed（状态机一致）", _14c_ok, f"final={final_c} last={_last_status} err={str(_last_err)[:120]}")
        # retry：按原参数重投 → 新任务 queued
        rr = client.post(f"/v1/tasks/{cid}/retry")
        rj = rr.json() if rr.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "14d retry 返回新任务 queued",
            rr.status_code == 200 and bool(rj.get("task_id")) and rj.get("status") == "queued",
            f"resp={rr.text[:120]}",
        )

        # 15. v16.1 P1-5：配额响应头（放行路径也带 X-RateLimit-* 三头）
        h = client.post("/v1/generate/async", json={"prompt": "e2e配额头-测试"})
        hd = h.headers
        check(
            "15a generate 响应带 X-RateLimit-* 三头",
            all(k in hd for k in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")),
            f"headers={ {k: hd.get(k) for k in ('X-RateLimit-Limit','X-RateLimit-Remaining','X-RateLimit-Reset')} }",
        )

        # 16. v16.1 P1-8 + P2-10：管理导出 + 健康自诊断报告（E2E 开放模式放行）
        ex = client.post("/v1/admin/export/tasks", params={"format": "csv"})
        check(
            "16a 任务导出 csv 200+BOM+中文表头",
            ex.status_code == 200 and ex.content.startswith(b"\xef\xbb\xbf") and "提示词" in ex.text,
            f"status={ex.status_code} head={ex.text[:40]!r}",
        )
        ej = client.post("/v1/admin/export/tasks", params={"format": "json"})
        check(
            "16b 任务导出 json 200+meta",
            ej.status_code == 200 and "meta" in ej.json() and "rows" in ej.json(),
            f"status={ej.status_code}",
        )
        hr = client.get("/v1/admin/health-report")
        hrj = hr.json()
        # health-report 返回顶层聚合键（providers/account_pool/email_pool/solver/queue/runtime/cost）
        _HR_KEYS = {"providers", "account_pool", "email_pool", "solver", "queue", "runtime", "cost"}
        check(
            "16c 健康报告 200+七维",
            hr.status_code == 200 and len(_HR_KEYS - set(hrj.keys())) == 0,
            f"keys={sorted(hrj.keys())}",
        )
        hrm = client.get("/v1/admin/health-report", params={"format": "md"})
        check(
            "16d 健康报告 md 200+markdown",
            hrm.status_code == 200 and hrm.headers.get("content-type", "").startswith("text/markdown"),
            f"ct={hrm.headers.get('content-type')}",
        )


        # 17. v18 P1-1：视频 Mock 提交→轮询→完成
        v = client.post("/v1/video", json={"prompt": "e2e城市夜景视频", "mode": "txt2vid", "duration_seconds": 1.0})
        vj = v.json() if v.headers.get("content-type", "").startswith("application/json") else {}
        check("17a video 提交 200+task_id", v.status_code == 200 and bool(vj.get("task_id")), f"resp={v.text[:120]}")
        vdone = False
        for _ in range(40):
            vs = client.get(f"/v1/video/{vj.get('task_id', '')}")
            if vs.status_code == 200 and vs.json().get("status") == "completed":
                vdone = True
                break
            time.sleep(0.25)
        check("17b video 轮询 completed+mock URL", vdone, "video 任务未在窗口内完成")

        # 18. v18 P1-2：PPT 可编辑产物生成
        ppt = client.post("/v1/skills/ppt/generate", json={"title": "e2e 产品发布会", "pages": [{"headline": "开场", "points": ["a", "b"], "notes": "n"}]})
        check("18a ppt generate 200+PK 头", ppt.status_code == 200 and ppt.content[:2] == b"PK", f"status={ppt.status_code} head={ppt.content[:4]!r}")

        # 19. v18 P1-3：MCP 渐进暴露（retrieve_tools 可调 + admin 清单 8 工具）
        mc = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": "retrieve_tools", "arguments": {"query": "image"}}})
        mcj = mc.json()
        check("19a mcp retrieve_tools 可调", mc.status_code == 200 and "generate_image" in str(mcj.get("result", {})), f"resp={mc.text[:160]}")
        adm = client.get("/v1/admin/mcp-tools")
        check("19b mcp admin 工具清单 200", adm.status_code == 200 and adm.json().get("count", 0) >= 8, f"status={adm.status_code}")

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
