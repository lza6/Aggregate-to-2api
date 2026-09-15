"""tests/test_human_inbox_export.py — v14 P1 审批导出/历史测试。

覆盖：
- export(format="csv")：表头 + RFC 4180 转义（note 含逗号/引号）+ UTF-8 BOM + ISO 时间
- export(format="json")：list[dict] 结构 + ISO 时间 + decided_at None
- 非法 format → ValueError
- 端点：export 鉴权（无 Key 403 / 开放模式放行 + Content-Type/Disposition）；
  history 分页 limit/offset/status 过滤正确；非法 limit/offset → 400
- 空库导出仍返回表头（csv）/空数组（json）

付费红线：全程本地文件库（tmp_path），零真实上游调用。
"""

from __future__ import annotations

import csv
import io
import json

import pytest


@pytest.fixture(autouse=True)
def _cfg_reset(monkeypatch, tmp_path):
    """每用例：reset Settings + 全局单例指到 tmp 库，避免污染磁盘 data/。

    v14 修复：改 _DEFAULT_DB 后必须 reset_human_inbox() 重建全局单例（否则
    单例已在旧 _DEFAULT_DB 时 new 过，export/history 端点读的全局单例指向旧库，
    跨用例残留上一用例数据——memory 踩坑#1 同源）。
    """
    from api.agent.human_inbox import reset_human_inbox
    from api.config import reset_settings

    reset_settings()
    monkeypatch.setattr("api.agent.human_inbox._DEFAULT_DB", str(tmp_path / "human_inbox.db"))
    reset_human_inbox()
    yield
    reset_human_inbox()
    reset_settings()


@pytest.fixture()
def inbox(tmp_path):
    """独立 HumanInbox 实例（tmp 库，与全局单例隔离）。"""
    from api.agent.human_inbox import HumanInbox

    return HumanInbox(str(tmp_path / "export.db"))


@pytest.fixture()
def client(monkeypatch):
    """端点专用 TestClient（app 由 conftest lifespan 装配）。"""
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


# ── export() 方法 ─────────────────────────────────────────
class TestExportMethod:
    def test_csv_header_and_bom(self, inbox):
        """空库导出仍返回 UTF-8 BOM + 表头。"""
        out = inbox.export("csv")
        assert out.startswith("﻿")
        header = out.lstrip("﻿").split("\r\n")[0]
        assert header == "req_id,run_id,node_id,prompt,status,note,created_at,decided_at"

    def test_csv_rfc4180_escaping(self, inbox):
        """note 含逗号/引号 → RFC 4180 转义（字段整体加引号 + 引号翻倍）。"""
        req = inbox.create("run-e", "n1", "确认发布？")
        inbox.decide(req.req_id, "approve", note='含逗号,引号"和"混排')

        out = inbox.export("csv")
        rows = list(csv.reader(io.StringIO(out.lstrip("﻿"))))
        assert rows[0][0] == "req_id"
        data = [r for r in rows[1:] if r]
        assert len(data) == 1
        row = data[0]
        assert row[5] == '含逗号,引号"和"混排'  # csv.reader 解析回原文
        # 原始行含引号转义：字段被引号包裹，内部引号翻倍
        assert row[5].startswith("含逗号") and '""' in out

    def test_csv_iso_timestamps(self, inbox):
        """created_at/decided_at 导出为 ISO 8601（UTC）。"""
        req = inbox.create("run-t", "n1", "x")
        inbox.decide(req.req_id, "approve")
        out = inbox.export("csv")
        rows = list(csv.reader(io.StringIO(out.lstrip("﻿"))))
        data = [r for r in rows[1:] if r][0]
        assert data[6].endswith("+00:00") and "T" in data[6]
        assert data[7].endswith("+00:00") and "T" in data[7]

    def test_json_structure(self, inbox):
        """json 导出为 list[dict]，字段齐全，decided_at None 保留。"""
        r1 = inbox.create("run-j", "n1", "待审")
        r2 = inbox.create("run-j", "n2", "已批")
        inbox.decide(r2.req_id, "reject", note="no")
        out = inbox.export("json")
        parsed = json.loads(out)
        assert isinstance(parsed, list) and len(parsed) == 2
        by_req = {d["req_id"]: d for d in parsed}
        assert set(by_req[r1.req_id]) == {
            "req_id",
            "run_id",
            "node_id",
            "prompt",
            "status",
            "note",
            "created_at",
            "decided_at",
        }
        assert by_req[r1.req_id]["status"] == "pending" and by_req[r1.req_id]["decided_at"] is None
        assert by_req[r2.req_id]["status"] == "rejected" and by_req[r2.req_id]["note"] == "no"
        assert by_req[r2.req_id]["created_at"].endswith("+00:00")

    def test_invalid_format_raises(self, inbox):
        """非法 format → ValueError。"""
        with pytest.raises(ValueError):
            inbox.export("xml")

    def test_export_all_history_sorted(self, tmp_path):
        """导出包含全部历史（重启后从 SQLite 重建的旧记录也在内）。"""
        from api.agent.human_inbox import HumanInbox

        db = tmp_path / "all.db"
        inbox1 = HumanInbox(str(db))
        inbox1.create("run-1", "n1", "旧")
        inbox2 = HumanInbox(str(db))  # 重启实例
        inbox2.create("run-2", "n2", "新")
        parsed = json.loads(inbox2.export("json"))
        assert len(parsed) == 2


# ── export 端点 ───────────────────────────────────────────
class TestExportEndpoint:
    def test_export_without_key_403(self, client, monkeypatch):
        """无管理 Key（且未开开放模式）→ 403。"""
        monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
        monkeypatch.delenv("IF_ADMIN_KEY_OPEN", raising=False)
        from api.config import reset_settings

        reset_settings()
        r = client.get("/v1/agent/human-inbox/export?format=csv")
        assert r.status_code == 403

    def test_export_open_mode_csv(self, client, monkeypatch, inbox):
        """开放模式放行：csv Content-Type + attachment + BOM 表头。"""
        monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
        from api.config import reset_settings

        reset_settings()
        r = client.get("/v1/agent/human-inbox/export?format=csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.text.startswith("﻿")

    def test_export_open_mode_json(self, client, monkeypatch, inbox):
        """开放模式放行：json Content-Type + list 结构。"""
        monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
        from api.config import reset_settings

        reset_settings()
        r = client.get("/v1/agent/human-inbox/export?format=json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == []

    def test_export_invalid_format_400(self, client, monkeypatch):
        """非法 format → 400。"""
        monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
        from api.config import reset_settings

        reset_settings()
        r = client.get("/v1/agent/human-inbox/export?format=xml")
        assert r.status_code == 400

    def test_export_with_admin_key_ok(self, client, monkeypatch, inbox):
        """配置 IF_ADMIN_KEYS + 携带管理 Key → 放行。"""
        monkeypatch.setenv("IF_ADMIN_KEYS", "adminkey1")
        monkeypatch.delenv("IF_ADMIN_KEY_OPEN", raising=False)
        from api.config import reset_settings

        reset_settings()
        req = inbox.create("run-k", "n1", "确认？")
        inbox.decide(req.req_id, "approve")
        r = client.get("/v1/agent/human-inbox/export?format=csv", headers={"X-API-Key": "adminkey1"})
        assert r.status_code == 200
        assert "req_id,run_id,node_id,prompt" in r.text


# ── history 端点 ──────────────────────────────────────────
class TestHistoryEndpoint:
    def test_history_without_key_403(self, client, monkeypatch):
        """无管理 Key → 403。"""
        monkeypatch.delenv("IF_ADMIN_KEYS", raising=False)
        monkeypatch.delenv("IF_ADMIN_KEY_OPEN", raising=False)
        from api.config import reset_settings

        reset_settings()
        r = client.get("/v1/agent/human-inbox/history")
        assert r.status_code == 403

    def test_history_pagination(self, client, monkeypatch):
        """limit/offset 分页：count=本页条数，total=过滤后总数。"""
        monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
        from api.config import reset_settings

        reset_settings()
        from api.agent.human_inbox import human_inbox

        for i in range(5):
            human_inbox.create("run-p", f"n{i}", f"p{i}")
        r = client.get("/v1/agent/human-inbox/history?limit=2&offset=0")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2 and body["total"] == 5 and len(body["items"]) == 2
        r2 = client.get("/v1/agent/human-inbox/history?limit=2&offset=4")
        body2 = r2.json()
        assert body2["count"] == 1 and body2["total"] == 5  # 末页余 1 条

    def test_history_status_filter(self, client, monkeypatch):
        """status 过滤：仅返回匹配状态。"""
        monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
        from api.config import reset_settings

        reset_settings()
        from api.agent.human_inbox import human_inbox

        r1 = human_inbox.create("run-s", "n1", "a")
        human_inbox.create("run-s", "n2", "b")
        human_inbox.decide(r1.req_id, "approve")
        r = client.get("/v1/agent/human-inbox/history?status=approved")
        body = r.json()
        assert body["total"] == 1 and body["items"][0]["status"] == "approved"

    def test_history_invalid_params_400(self, client, monkeypatch):
        """非法分页参数 → 400。"""
        monkeypatch.setenv("IF_ADMIN_KEY_OPEN", "1")
        from api.config import reset_settings

        reset_settings()
        r = client.get("/v1/agent/human-inbox/history?limit=0")
        assert r.status_code == 400
        r2 = client.get("/v1/agent/human-inbox/history?offset=-1")
        assert r2.status_code == 400
