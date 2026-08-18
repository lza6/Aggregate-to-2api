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