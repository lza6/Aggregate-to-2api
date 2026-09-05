"""测试审计日志模块。"""

import json
import os
import tempfile

from api.audit import AuditLog


def test_audit_record():
    """验证审计日志写入。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        audit.record("dlq.clear", "127.0.0.1", "dlq", "清空死信队列")
        with open(path) as f:
            line = json.loads(f.readline())
        assert line["action"] == "dlq.clear"
        assert line["actor"] == "127.0.0.1"
        assert line["target"] == "dlq"
        assert "timestamp" in line
    finally:
        os.unlink(path)


def test_audit_append_only():
    """验证审计日志仅追加，不修改已有记录。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        audit.record("action1", "actor1", "target1")
        audit.record("action2", "actor2", "target2")
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])
        assert entry1["action"] == "action1"
        assert entry2["action"] == "action2"
    finally:
        os.unlink(path)


def test_audit_recent_limit_and_corrupt_line_skipped():
    """recent(limit) 只返回最近 N 条；损坏 JSON 行跳过不抛。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        for i in range(5):
            audit.record(f"act{i}", "actor", "target")
        with open(path, "a", encoding="utf-8") as f:
            f.write("{{{not-json\n")  # 损坏行
        entries = audit.recent(limit=3)
        # limit=3 取末 3 行 = [act3, act4, 损坏行] → 损坏行跳过后剩 act3/act4
        assert [e["action"] for e in entries] == ["act3", "act4"]
        # limit 覆盖全部 → 5 条合法条目全部返回（损坏行被跳过）
        assert len(audit.recent(limit=100)) == 5
    finally:
        os.unlink(path)


def test_audit_recent_missing_file_returns_empty(tmp_path):
    audit = AuditLog(str(tmp_path / "not_exist.log"))
    assert audit.recent() == []


def test_audit_record_with_trace_id_passthrough():
    """显式传 trace_id 时写入该值（B2 链路串联）。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        audit.record("block.ip", "admin", "1.2.3.4", detail="test", trace_id="trace-xyz")
        entry = json.loads(open(path).readline())
        assert entry["trace_id"] == "trace-xyz"
        assert entry["detail"] == "test"
    finally:
        os.unlink(path)


def test_audit_record_trace_id_defaults_from_context_or_empty():
    """不传 trace_id 时从请求上下文取（无上下文 → 空串，不抛）。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        audit = AuditLog(path)
        audit.record("act", "actor", "target")
        entry = json.loads(open(path).readline())
        assert entry["trace_id"] == ""  # 测试环境无活跃请求上下文
    finally:
        os.unlink(path)


def test_audit_record_oserror_swallowed(tmp_path, monkeypatch):
    """写入 OSError → warning 不抛（审计失败不阻塞主流程）。"""
    audit = AuditLog(str(tmp_path / "a.log"))
    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")),
    )
    audit.record("act", "actor", "target")  # 不应抛异常
