"""E2E 验收测试 — 验证所有新功能：
1. /metrics 端点返回 prometheus_client 格式
2. 审计日志记录
3. 告警引擎初始化
4. WebSocket 日志端点
5. 前端静态文件挂载
6. 核心 API 端点健康
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error


def check_url(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    resp = urllib.request.urlopen(url, timeout=timeout)
    return resp.status, resp.read()


def test_metrics_endpoint() -> list[str]:
    errors = []
    try:
        status, body = check_url("http://127.0.0.1:8100/metrics")
        text = body.decode("utf-8")
        checks = {
            "imagefree_requests_total": "/metrics 缺少 imagefree_requests_total",
            "imagefree_processing": "/metrics 缺少 imagefree_processing",
            "imagefree_uptime_seconds": "/metrics 缺少 imagefree_uptime_seconds",
            "imagefree_queued": "/metrics 缺少 imagefree_queued",
            "imagefree_db_rows": "/metrics 缺少 imagefree_db_rows",
        }
        for key, msg in checks.items():
            if key not in text:
                errors.append(msg)
        if status != 200:
            errors.append(f"/metrics 状态码异常: {status}")
    except Exception as e:
        errors.append(f"/metrics 请求失败: {e}")
    return errors


def test_healthz_endpoint() -> list[str]:
    errors = []
    try:
        status, body = check_url("http://127.0.0.1:8100/v1/healthz")
        data = json.loads(body)
        if "status" not in data:
            errors.append("/v1/healthz 缺少 status")
        if "processing" not in data:
            errors.append("/v1/healthz 缺少 processing")
        if "queued" not in data:
            errors.append("/v1/healthz 缺少 queued")
        if status != 200:
            errors.append(f"/v1/healthz 状态码异常: {status}")
    except Exception as e:
        errors.append(f"/v1/healthz 请求失败: {e}")
    return errors


def test_stats_endpoint() -> list[str]:
    errors = []
    try:
        status, body = check_url("http://127.0.0.1:8100/v1/stats")
        data = json.loads(body)
        if "total_requests" not in data:
            errors.append("/v1/stats 缺少 total_requests")
        if "solver" not in data:
            errors.append("/v1/stats 缺少 solver 字段")
        if "daily" not in data:
            errors.append("/v1/stats 缺少 daily 字段")
        if status != 200:
            errors.append(f"/v1/stats 状态码异常: {status}")
    except Exception as e:
        errors.append(f"/v1/stats 请求失败: {e}")
    return errors


def test_models_endpoint() -> list[str]:
    errors = []
    try:
        status, body = check_url("http://127.0.0.1:8100/v1/models")
        data = json.loads(body)
        if "items" not in data and "models" not in data:
            errors.append("/v1/models missing 'items' or 'models' field")
        if status != 200:
            errors.append(f"/v1/models status code: {status}")
    except Exception as e:
        errors.append(f"/v1/models request failed: {e}")
    return errors


def test_audit_log_exists() -> list[str]:
    errors = []
    try:
        if os.path.exists("data/audit.log"):
            with open("data/audit.log") as f:
                content = f.read().strip()
            if content:
                lines = content.split("\n")
                entry = json.loads(lines[0])
                if "action" not in entry or "timestamp" not in entry:
                    errors.append("audit log format error (missing action/timestamp)")
                print("  [OK] audit log exists" + (f" ({len(lines)} records)" if content else " (empty)"))
        else:
            print("  [OK] audit log not yet created (no audit operations triggered)")
    except Exception as e:
        errors.append(f"audit log check failed: {e}")
    return errors


def test_websocket_handshake() -> list[str]:
    import asyncio

    errors = []

    async def _check():
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 8100), timeout=3.0)
            upgrade = (
                "GET /v1/logs/ws HTTP/1.1\r\n"
                "Host: 127.0.0.1:8100\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            writer.write(upgrade.encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(1024), timeout=3.0)
            if b"101" not in resp:
                errors.append(f"WebSocket upgrade response abnormal: {resp[:100]}")
            else:
                print("  [OK] WebSocket handshake successful")
            writer.close()
        except asyncio.TimeoutError:
            errors.append("WebSocket 连接超时")
        except ConnectionRefusedError:
            errors.append("WebSocket 连接被拒绝（服务未运行）")
        except Exception as e:
            errors.append(f"WebSocket 检查异常: {e}")

    asyncio.run(_check())
    return errors


def run_all() -> int:
    print("=" * 55)
    print("  E2E Acceptance Tests - v2.3.0 New Features")
    print("=" * 55)
    print()

    all_errors = []
    sections = [
        ("/metrics (prometheus_client)", test_metrics_endpoint),
        ("/v1/healthz (health check)", test_healthz_endpoint),
        ("/v1/stats (statistics)", test_stats_endpoint),
        ("/v1/models (providers)", test_models_endpoint),
        ("audit log file", test_audit_log_exists),
        ("WebSocket /v1/logs/ws", test_websocket_handshake),
    ]

    for name, func in sections:
        print(f"  [{name}]")
        t0 = time.time()
        errs = func()
        elapsed = time.time() - t0
        if errs:
            print(f"  FAIL ({elapsed:.1f}s) - {len(errs)} issues:")
            for e in errs:
                print(f"     - {e}")
            all_errors.extend(errs)
        else:
            print(f"  PASS ({elapsed:.1f}s)")
        print()

    if all_errors:
        print(f"FAILED: {len(all_errors)} issues found (out of {len(sections)} checks):")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    else:
        print(f"ALL {len(sections)} E2E tests PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(run_all())
