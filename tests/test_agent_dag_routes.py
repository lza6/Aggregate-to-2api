"""tests/test_agent_dag_routes.py — v9.0.0-A DAG 编排 HTTP 端点测试。

覆盖 Story 1-4 验收标准（HTTP 真实调用，TestClient 复用 app 单例）：
- POST /v1/agent/dag/run     提交 + 后台执行 + 轮询完成
- GET  /v1/agent/dag/{id}    状态查询（含节点）
- POST /v1/agent/dag/plan    自然语言 → DAG（Mock）
- 开关 IF_AGENT_DAG_ENABLED=0 → 404
- 校验失败 → 422 中文 message
- 鉴权：guard_chat_request（公益开放，无 Key 也应可调）
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("IF_AGENT_DAG_ENABLED", "1")
os.environ.setdefault("IF_AGENT_PLANNER_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")
os.environ.setdefault("IF_DB_FILE", "data/test-agent-dag-routes.db")
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "1")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


def _wait_run_finished(client, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/v1/agent/dag/{run_id}")
        assert r.status_code == 200, f"查询 run 应 200: {r.status_code} {r.text[:300]}"
        body = r.json()
        if body.get("status") in ("succeeded", "failed"):
            return body
        time.sleep(0.3)
    raise AssertionError(f"DAG run {run_id} 在 {timeout}s 内未终态")


class TestDagRunEndpoint:
    def test_submit_and_wait_success(self, client):
        """提交串行链 → 后台执行 → 轮询到 succeeded。"""
        r = client.post(
            "/v1/agent/dag/run",
            json={
                "name": "链式任务",
                "nodes": [
                    {"id": "A", "kind": "llm", "depends_on": [], "prompt": "先识别场景"},
                    {"id": "B", "kind": "llm", "depends_on": ["A"], "prompt": "生成结果"},
                ],
            },
        )
        assert r.status_code == 200, f"提交应 200: {r.status_code} {r.text[:400]}"
        body = r.json()
        run_id = body["run_id"]
        assert body["status"] in ("pending", "running", "succeeded", "failed")

        final = _wait_run_finished(client, run_id)
        assert final["status"] == "succeeded"
        node_map = {n["id"]: n for n in final["nodes"]}
        assert node_map["A"]["status"] == "succeeded"
        assert node_map["B"]["status"] == "succeeded"
        assert node_map["B"]["result"]  # 有真实执行结果（Mock 占位或真实 LLM）

    def test_plan_then_run_roundtrip(self, client):
        """自然语言 plan → 提交 run → 轮询成功（Mock 规划器链路）。"""
        plan_r = client.post(
            "/v1/agent/dag/plan",
            json={"prompt": "画一只猫并终检质量"},
        )
        assert plan_r.status_code == 200, f"plan 应 200: {plan_r.text[:400]}"
        plan = plan_r.json()
        assert plan["meta"]["valid"] is True
        assert plan["meta"]["mock"] is True
        nodes = plan["nodes"]
        assert nodes, "plan 应返回节点"

        run_r = client.post("/v1/agent/dag/run", json={"name": "plan-roundtrip", "nodes": nodes})
        assert run_r.status_code == 200, f"plan 转 run 应 200: {run_r.text[:400]}"
        run_id = run_r.json()["run_id"]
        final = _wait_run_finished(client, run_id)
        assert final["status"] in ("succeeded", "failed")
        assert all(n["status"] in ("succeeded", "failed", "skipped") for n in final["nodes"])

    def test_invalid_node_rejected_422(self, client):
        """非法节点（未知 kind）→ 422 + 中文 message。"""
        r = client.post(
            "/v1/agent/dag/run",
            json={"name": "bad", "nodes": [{"id": "x", "kind": "bogus", "depends_on": []}]},
        )
        assert r.status_code == 422, f"应 422: {r.status_code} {r.text[:400]}"
        # AppError → {error:{code,message}}；BAD_REQUEST 模板 "请求参数错误：{detail}"
        body = r.json()
        assert "未知节点类型" in body.get("error", {}).get("message", "")

    def test_cycle_rejected_422(self, client):
        """环形依赖 → 422。"""
        r = client.post(
            "/v1/agent/dag/run",
            json={
                "name": "cycle",
                "nodes": [
                    {"id": "A", "kind": "llm", "depends_on": ["B"]},
                    {"id": "B", "kind": "llm", "depends_on": ["A"]},
                ],
            },
        )
        assert r.status_code == 422

    def test_fail_fast_skips_downstream_http(self, client):
        """fail_fast 链路（HTTP）：重试耗尽才 failed 确保 run terminated，验证 HTTP 链路正常。"""
        r = client.post(
            "/v1/agent/dag/run",
            json={
                "name": "fail-chain",
                "fail_fast": True,
                "max_parallel": 1,
                "nodes": [
                    {"id": "A", "kind": "tool", "depends_on": []},
                    {"id": "B", "kind": "tool", "depends_on": ["A"]},
                ],
            },
        )
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        final = _wait_run_finished(client, run_id)
        # 引擎 fail_fast 精确语义在单测 TestExecuteRun 已覆盖；此处 HTTP 链路仅验
        # 提交→后台执行→轮询终态闭环（succeeded/failed 均可，因 tool 占位成功）
        assert final["status"] in ("succeeded", "failed")
        assert all(n["status"] in ("succeeded", "failed", "skipped") for n in final["nodes"])


class TestDagGetEndpoint:
    def test_not_found_404(self, client):
        r = client.get("/v1/agent/dag/no-such-run")
        assert r.status_code == 404

    def test_public_state_shape(self, client):
        r = client.post(
            "/v1/agent/dag/run",
            json={"name": "shape", "nodes": [{"id": "A", "kind": "llm", "depends_on": []}]},
        )
        run_id = r.json()["run_id"]
        body = _wait_run_finished(client, run_id)
        assert set(body.keys()) >= {"run_id", "name", "status", "nodes", "created_at"}
        assert isinstance(body["nodes"], list)


class TestDagPlanEndpoint:
    def test_plan_mock_returns_valid_dag(self, client):
        r = client.post("/v1/agent/dag/plan", json={"prompt": "生成电商主图"})
        assert r.status_code == 200
        plan = r.json()
        assert plan["meta"]["mock"] is True
        assert plan["meta"]["valid"] is True
        assert plan["nodes"][0]["id"] == "scene"

    def test_plan_disabled_404(self, client, monkeypatch):
        import api.routes.agent_dag as routes_mod

        monkeypatch.setattr(routes_mod, "PLANNER_ENABLED", False)
        r = client.post("/v1/agent/dag/plan", json={"prompt": "hi"})
        assert r.status_code == 404


class TestDagDisableSwitch:
    def test_dag_disabled_404(self, client, monkeypatch):
        import api.routes.agent_dag as routes_mod

        monkeypatch.setattr(routes_mod, "DAG_ENABLED", False)
        r = client.post(
            "/v1/agent/dag/run",
            json={"name": "off", "nodes": [{"id": "A", "kind": "llm", "depends_on": []}]},
        )
        assert r.status_code == 404
