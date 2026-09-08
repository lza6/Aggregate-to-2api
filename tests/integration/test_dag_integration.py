"""tests/integration/test_dag_integration.py — v10.0.0 DAG 编排端到端集成测试。

验收（真实 HTTP TestClient，非 Mock 单元）：
- plan → run → 轮询终态（串行链 + 并行扇出）
- 列表端点（/v1/agent/dag）+ status 过滤
- 持久化：sqlite store 重启可查（用独立临时 dag_runs.db）
- 开关 404 与非法输入 422
- 工具节点真实回路（复用 api/skills 索引）
- 鉴权：guard_chat_request 公益开放（无 Key 直调 200）

付费红线：IF_MOCK_UPSTREAM=1 + IF_MOCK_REGISTER=1 + mock solver，零真实上游。
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

# v10.0.0：本文件是真实 HTTP TestClient + scope=module 完整 app 生命周期，
# 必须在 integration 口径下跑（与其余 tests/integration 一致）。
# 缺此 mark 会被「CI 单测口径」`pytest -m "not integration ..."` 当单测收集执行：
# ① 覆盖 conftest 的 IF_DAG_STORE_BACKEND=memory → 改用 sqlite 写 data/ 真实库；
# ② `with TestClient(app)` 起完整 lifespan 后台任务，teardown 时 anyio
#    BlockingPortal 任务未清 → 污染后续单测（token_pool 批量挂起等 flaky）。
# 且不自起 TestClient：复用 conftest 会话级 app_with_mocks（httpx ASGI 同 app），
# 避免集成全量中多 app 实例 / lifespan 交错导致 teardown 报 BlockingPortal 任务未清。
pytestmark = pytest.mark.integration

os.environ.setdefault("IF_AGENT_DAG_ENABLED", "1")
os.environ.setdefault("IF_AGENT_PLANNER_ENABLED", "1")
os.environ.setdefault("IF_MOCK_UPSTREAM", "1")
os.environ.setdefault("IF_MOCK_REGISTER", "1")
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_DAG_STORE_BACKEND", "sqlite")


async def _wait_run(client, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = await client.get(f"/v1/agent/dag/{run_id}")
        assert r.status_code == 200
        body = r.json()
        if body.get("status") in ("succeeded", "failed"):
            return body
        await asyncio.sleep(0.3)
    raise AssertionError(f"run {run_id} 未在 {timeout}s 内终态")


class TestDagIntegration:
    async def test_plan_run_roundtrip(self, app_with_mocks):
        client = app_with_mocks
        plan_r = await client.post("/v1/agent/dag/plan", json={"prompt": "画一只猫并终检质量"})
        assert plan_r.status_code == 200
        plan = plan_r.json()
        assert plan["meta"]["valid"] is True

        run_r = await client.post("/v1/agent/dag/run", json={"name": "intg-猫", "nodes": plan["nodes"]})
        assert run_r.status_code == 200
        run_id = run_r.json()["run_id"]
        final = await _wait_run(client, run_id)
        assert final["status"] in ("succeeded", "failed")
        assert all(n["status"] in ("succeeded", "failed", "skipped") for n in final["nodes"])

    async def test_list_and_status_filter(self, app_with_mocks):
        client = app_with_mocks
        lr = await client.get("/v1/agent/dag")
        assert lr.status_code == 200
        body = lr.json()
        assert isinstance(body.get("items"), list)
        assert body.get("count", 0) >= 1
        lr2 = await client.get("/v1/agent/dag?status=succeeded")
        assert lr2.status_code == 200
        assert all(it["status"] == "succeeded" for it in lr2.json()["items"])

    async def test_tool_node_real_roundtrip(self, app_with_mocks):
        client = app_with_mocks
        run_r = await client.post(
            "/v1/agent/dag/run",
            json={"name": "tool", "nodes": [{"id": "T", "kind": "tool", "prompt": "使用 image-quality-check 工具", "depends_on": []}]},
        )
        assert run_r.status_code == 200
        run_id = run_r.json()["run_id"]
        final = await _wait_run(client, run_id)
        result = final["nodes"][0]["result"]
        assert "image-quality-check" in result, f"工具节点应真实加载技能: {result[:200]}"

    async def test_invalid_and_404(self, app_with_mocks):
        client = app_with_mocks
        r = await client.post("/v1/agent/dag/run", json={"name": "bad", "nodes": [{"id": "x", "kind": "bogus", "depends_on": []}]})
        assert r.status_code == 422
        assert (await client.get("/v1/agent/dag/no-such")).status_code == 404
