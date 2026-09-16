"""tests/test_admin_export_tasks.py — P1-8 历史任务批量导出（后端）单元测试。

覆盖：
- 鉴权：open 模式（IF_ADMIN_KEY_OPEN=1）放行；无管理 Key 且非 open → 403
- csv：UTF-8 BOM + 中文表头 + 数据行（提供商由 model 前缀派生、时间格式化）
- json：完整字段 rows + meta{total}
- 过滤：start_ts/end_ts 时间段生效；provider/model/status 过滤
- 截断：超 _EXPORT_MAX_ROWS 时 X-Truncated: true + 只返回上限行

策略：复用 conftest.tmp_db，monkeypatch `api.routes.admin.query.db` 指向本用例独立 DB
（query.py 以 `from ...meta import db` 在 import 期绑定，须按名换对象）；直接调端点函数，
不启 TestClient lifespan（同 test_gallery_crud 策略）。
"""

from __future__ import annotations

import json

import pytest
from fastapi import Request

from api.errors import AppError
from api.routes.admin import query as admin_query


async def _seed_task(tmp_db, task_id: str, *, status: str = "completed", model: str = "imagefree/default", created_at: float, prompt: str = "测试提示词", error: str | None = None):
    """直接插一行任务记录（含终态字段，供导出读取）。"""
    _, conn, conn_lock = await tmp_db._get_write_conn()
    async with conn_lock:
        await conn.execute(
            "INSERT INTO requests (id, prompt, status, model, aspect_ratio, created_at, finished_at, duration_sec, error, client_ip)"
            " VALUES (?, ?, ?, ?, '1:1', ?, ?, 2.5, ?, '203.0.113.7')",
            (task_id, prompt, status, model, created_at, created_at + 30.0, error),
        )
        await conn.commit()


class _Handler:
    """临时审计日志落盘重定向（避免测试写 data/audit.log）。"""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, *args, **kwargs) -> None:  # 不落盘，仅记录
        self.records.append({"args": args, "kwargs": kwargs})


def _req() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "url": "http://test/v1/admin/export/tasks",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1),
        }
    )


@pytest.mark.asyncio
async def test_export_tasks_forbidden_without_admin_open(tmp_db, monkeypatch):
    """无管理 Key 且非开放模式（IF_ADMIN_KEY_OPEN=0）→ 403。"""
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "0")
    monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
    monkeypatch.delenv("IF_API_KEYS", raising=False)
    from api.config import reset_settings

    reset_settings()
    # 指向测试 DB（非 open 也先配好，避免 403 以外的变量干扰）
    monkeypatch.setattr(admin_query, "db", tmp_db)
    with pytest.raises(AppError) as ei:
        await admin_query.export_tasks(
            request=_req(), format="csv", start_ts=None, end_ts=None, provider=None, model=None, status=None
        )
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_export_tasks_csv_bom_chinese_header_and_rows(tmp_db, monkeypatch):
    """open 模式放行；csv 含 UTF-8 BOM + 中文表头 + 数据行。"""
    monkeypatch.setattr(admin_query, "db", tmp_db)
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
    monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
    monkeypatch.delenv("IF_API_KEYS", raising=False)
    from api.config import reset_settings

    reset_settings()
    now = 1_800_000_000.0
    await _seed_task(tmp_db, "t1", model="imagefree/default", created_at=now)
    # 审计日志重定向（不污染 data/audit.log）
    monkeypatch.setattr(admin_query, "audit_log", _Handler())

    resp = await admin_query.export_tasks(
        request=_req(), format="csv", start_ts=None, end_ts=None, provider=None, model=None, status=None
    )
    assert resp.media_type.startswith("text/csv")
    body = resp.body.decode("utf-8-sig")  # utf-8-sig 剥离 BOM
    assert resp.body.startswith(b"\xef\xbb\xbf"), "csv 须以 UTF-8 BOM 开头（Excel 中文识别）"
    lines = body.strip("\r\n").split("\r\n")
    header = lines[0].split(",")
    assert header == ["ID", "提示词", "状态", "模型", "提供商", "比例", "创建时间", "完成时间", "耗时秒", "错误", "IP"]
    assert len(lines) == 2  # 表头 + 1 数据行
    data = dict(zip(header, lines[1].split(",")))
    assert data["ID"] == "t1"
    assert data["状态"] == "completed"
    assert data["提供商"] == "imagefree"  # model 前缀派生
    assert data["提示词"] == "测试提示词"
    assert data["创建时间"] != "" and data["完成时间"] != ""


@pytest.mark.asyncio
async def test_export_tasks_json_full_fields_and_meta(tmp_db, monkeypatch):
    """json 格式：rows 完整字段 + meta{total}。"""
    monkeypatch.setattr(admin_query, "db", tmp_db)
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
    monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
    monkeypatch.delenv("IF_API_KEYS", raising=False)
    from api.config import reset_settings

    reset_settings()
    await _seed_task(tmp_db, "t1", created_at=1_800_000_000.0)
    await _seed_task(tmp_db, "t2", status="archived", model="nanobanana/banana", created_at=1_700_000_000.0, error="上游超时")
    monkeypatch.setattr(admin_query, "audit_log", _Handler())

    resp = await admin_query.export_tasks(
        request=_req(), format="json", start_ts=None, end_ts=None, provider=None, model=None, status=None
    )
    assert resp.media_type.startswith("application/json")
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["meta"]["total"] == 2
    assert payload["meta"]["truncated"] is False
    rows = payload["rows"]
    assert {r["id"] for r in rows} == {"t1", "t2"}
    # 完整字段：含导出所需全部键，且 archived 冷历史可导出
    row_t2 = next(r for r in rows if r["id"] == "t2")
    for key in ("id", "prompt", "status", "model", "aspect_ratio", "created_at", "finished_at", "duration_sec", "error", "client_ip"):
        assert key in row_t2
    assert row_t2["status"] == "archived" and row_t2["error"] == "上游超时"


@pytest.mark.asyncio
async def test_export_tasks_time_range_and_filters(tmp_db, monkeypatch):
    """start_ts/end_ts 时间段过滤 + provider/model/status 过滤生效。"""
    monkeypatch.setattr(admin_query, "db", tmp_db)
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
    monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
    monkeypatch.delenv("IF_API_KEYS", raising=False)
    from api.config import reset_settings

    reset_settings()
    # 三条不同时间/提供商/状态
    await _seed_task(tmp_db, "old-free", model="imagefree/default", created_at=1_600_000_000.0)
    await _seed_task(tmp_db, "mid-free", model="imagefree/default", created_at=1_700_000_000.0)
    await _seed_task(tmp_db, "new-banana", model="nanobanana/banana", created_at=1_800_000_000.0)
    monkeypatch.setattr(admin_query, "audit_log", _Handler())

    def _ids(resp) -> list[str]:
        payload = json.loads(resp.body.decode("utf-8"))
        return [r["id"] for r in payload["rows"]]

    # 时间段：1_650_000_000 ~ 1_750_000_000 → 仅 mid-free
    resp = await admin_query.export_tasks(
        request=_req(), format="json",
        start_ts=1_650_000_000.0, end_ts=1_750_000_000.0,
        provider=None, model=None, status=None,
    )
    assert _ids(resp) == ["mid-free"]

    # provider=nanobanana → only new-banana
    resp = await admin_query.export_tasks(
        request=_req(), format="json",
        start_ts=None, end_ts=None, provider="nanobanana", model=None, status=None,
    )
    assert _ids(resp) == ["new-banana"]

    # status=completed → 全部（三条都 completed，除非另有）
    resp = await admin_query.export_tasks(
        request=_req(), format="json",
        start_ts=None, end_ts=None, provider=None, model="imagefree/default", status="completed",
    )
    assert set(_ids(resp)) == {"old-free", "mid-free"}


@pytest.mark.asyncio
async def test_export_tasks_truncation_header(tmp_db, monkeypatch):
    """行数超上限 → X-Truncated: true + 只返回上限行。"""
    monkeypatch.setattr(admin_query, "db", tmp_db)
    monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
    monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
    monkeypatch.delenv("IF_API_KEYS", raising=False)
    from api.config import reset_settings

    reset_settings()
    monkeypatch.setattr(admin_query, "_EXPORT_MAX_ROWS", 2)
    for i in range(3):
        await _seed_task(tmp_db, f"t{i}", created_at=1_800_000_000.0 + i)
    monkeypatch.setattr(admin_query, "audit_log", _Handler())

    resp = await admin_query.export_tasks(
        request=_req(), format="json", start_ts=None, end_ts=None, provider=None, model=None, status=None
    )
    assert resp.headers.get("X-Truncated") == "true"
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["meta"]["total"] == 2 and payload["meta"]["truncated"] is True
    assert len(payload["rows"]) == 2
