"""E2E 验收测试 — v11.0.0 深化层（DAG 条件分支/RAG/多模态/限流）。

前置：uvicorn:8100 已起（IF_ACCOUNT_AUTO=0 + mock solver + IF_DAG_REQUESTS_PER_MINUTE=3）。
"""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8100"


def _req(method: str, path: str, body: dict | None = None, timeout: float = 30.0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def _wait_run(run_id: str, timeout: float = 90.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, data = _req("GET", f"/v1/agent/dag/{run_id}")
        if code == 200 and data.get("status") in ("succeeded", "failed"):
            return data
        time.sleep(1.5)
    raise TimeoutError(f"run {run_id} 未在 {timeout}s 内终态")


def test_conditional_run() -> list[str]:
    errs = []
    body = {
        "name": "v11 条件分支+深化",
        "nodes": [
            {"id": "A", "kind": "llm", "prompt": "第一步执行成功"},
            {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A contains 成功"},
            {"id": "R", "kind": "retrieval", "prompt": "电商主图素材"},
            {"id": "I", "kind": "image", "prompt": "日落图"},
            {"id": "H", "kind": "human_input", "prompt": "请确认图稿"},
        ],
        "fail_fast": False,
        "max_parallel": 3,
    }
    code, data = _req("POST", "/v1/agent/dag/run", body)
    if code != 200:
        errs.append(f"run 提交失败 {code}: {data}")
        return errs
    run = _wait_run(data["run_id"])
    if run.get("status") != "succeeded":
        errs.append(f"run 终态异常: {run.get('status')} {run.get('error_summary')}")
        return errs
    states = {n["id"]: n["status"] for n in run["nodes"]}
    for nid, exp in [("A", "succeeded"), ("B", "succeeded"), ("R", "succeeded"),
                     ("I", "succeeded"), ("H", "succeeded")]:
        if states.get(nid) != exp:
            errs.append(f"{nid} 应 {exp} 实际 {states.get(nid)}")
    code, lst = _req("GET", "/v1/agent/dag?limit=10")
    if code != 200 or not any(x.get("run_id") == data["run_id"] for x in lst.get("items", [])):
        errs.append("列表未包含该 run")
    return errs


def test_condition_false_skips() -> list[str]:
    errs = []
    body = {
        "name": "条件假跳过",
        "nodes": [
            {"id": "A", "kind": "llm", "prompt": "结果无异常"},
            {"id": "C", "kind": "llm", "depends_on": ["A"], "condition": "A contains 失败"},
        ],
    }
    code, data = _req("POST", "/v1/agent/dag/run", body)
    if code != 200:
        return [f"提交失败 {code}: {data}"]
    run = _wait_run(data["run_id"])
    states = {n["id"]: n["status"] for n in run["nodes"]}
    if states.get("C") != "skipped":
        errs.append(f"条件假下游 C 应 skipped 实际 {states.get('C')}")
    return errs


def test_invalid_condition_422() -> list[str]:
    errs = []
    body = {"name": "非法条件", "nodes": [
        {"id": "A", "kind": "llm"},
        {"id": "B", "kind": "llm", "depends_on": ["A"], "condition": "A regex 'x'"},
    ]}
    code, data = _req("POST", "/v1/agent/dag/run", body)
    if code != 422:
        errs.append(f"非法条件应 422 实际 {code}: {data}")
    return errs


def test_plan_mock() -> list[str]:
    errs = []
    code, data = _req("POST", "/v1/agent/dag/plan", {"prompt": "画一张电商主图"})
    if code != 200 or not data.get("nodes"):
        errs.append(f"plan Mock 异常 {code}: {data}")
    return errs


def test_dag_rate_limit() -> list[str]:
    errs = []
    body = {"name": "限流", "nodes": [{"id": "A", "kind": "llm"}]}
    statuses = []
    for _ in range(4):
        code, _ = _req("POST", "/v1/agent/dag/run", body)
        statuses.append(code)
    if 429 not in statuses:
        errs.append(f"DAG 限流应触发 429，实际状态序列 {statuses}")
    return errs


def run_all() -> int:
    print("=" * 55)
    print("  E2E v11.0.0 深化层验收")
    print("=" * 55)
    all_errors = []
    sections = [
        ("DAG 条件真+检索+图像+人机", test_conditional_run),
        ("DAG 条件假跳过", test_condition_false_skips),
        ("DAG 非法条件 422", test_invalid_condition_422),
        ("DAG plan Mock", test_plan_mock),
        ("DAG 限流(4次触发429)", test_dag_rate_limit),
    ]
    for name, func in sections:
        print(f"  [{name}]", flush=True)
        t0 = time.time()
        errs = func()
        elapsed = time.time() - t0
        if errs:
            print(f"  FAIL ({elapsed:.1f}s) - {len(errs)} issues:")
            for e in errs:
                print(f"     - {e}")
            all_errors.extend(errs)
        else:
            print(f"  PASS ({elapsed:.1f}s)", flush=True)
        print()
    if all_errors:
        print(f"FAILED: {len(all_errors)} issues:")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print(f"ALL {len(sections)} E2E v11 tests PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_all())
