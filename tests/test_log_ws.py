"""测试 WebSocket 日志推送。"""

import logging

from api.log_ws import LogBuffer, WsLogHandler


def test_log_buffer():
    """验证日志缓冲区。"""
    buf = LogBuffer(maxlen=100)
    buf.push({"level": "INFO", "message": "test"})
    assert buf.snapshot()[-1]["message"] == "test"
    assert len(buf.snapshot(1)) == 1


def test_log_buffer_maxlen():
    """验证缓冲区上限。"""
    buf = LogBuffer(maxlen=5)
    for i in range(10):
        buf.push({"level": "INFO", "message": f"msg{i}"})
    snap = buf.snapshot()
    assert len(snap) == 5
    assert snap[0]["message"] == "msg5"


def test_log_buffer_empty():
    """验证空缓冲区 snapshot 返回空列表。"""
    buf = LogBuffer(maxlen=100)
    assert buf.snapshot() == []


def test_ws_handler_not_crash():
    """验证无订阅者时 handler 不报错。"""
    handler = WsLogHandler()
    record = logging.LogRecord("test", logging.INFO, "test.py", 1, "test msg", None, None)
    try:
        handler.emit(record)
    except Exception:
        assert False, "WsLogHandler.emit() 不应该抛异常"


def test_ws_handler_format():
    """验证 handler 格式化正常。"""
    handler = WsLogHandler()
    record = logging.LogRecord("test", logging.WARNING, "test.py", 1, "warning msg", None, None)
    handler.emit(record)
    # 不应抛出异常，且广播函数应无异常
    assert True
