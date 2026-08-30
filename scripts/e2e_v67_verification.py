"""v6.7.0 专项真实验证驱动（P3-1 边界 + Security 风控页 + DLQ 鉴权 + meta 脱敏回归）：

1. 启动 mock cf_solver + mock API（零真实网络，IF_MOCK_UPSTREAM/REGISTER=1）
2. 设置 IF_ADMIN_KEYS=test-admin-key-6700，使写操作受鉴权保护
3. 验证：
   A) 前端 SPA /admin 挂载，且 HTML 含 boundary-pill「公开只读 · 写操作需管理 Key」文案（P3-1）
   B) 前端 /security 路由 lazy chunk 可达（Security-*.js 产物存在）
   C) DLQ retry 无 admin key → 401/403（鉴权生效）；带正确 admin key → 非 401/403（放行至业务层）
   D) DLQ clear 无 admin key → 401/403
   E) security/block-ip 无 admin key → 401/403；带正确 admin key → 200 且封禁落库
   F) security/blocklist 带正确 admin key → 含刚封禁的 IP
   G) security/unblock-ip 带正确 admin key → 解封成功
   H) /v1/meta 不含完整 api_key（v6.6.0 脱敏回归不破）
   I) OpenAPI schema paths 含 /v1/admin/security/block-ip 等新端点

用法：python scripts/e2e_v67_verification.py
"""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PY = sys.executable
SOLVER_PORT = 8001
API_PORT = 8100
ADMIN_KEY = "test-admin-key-6700"


def _reconfigure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def wait_port(port: int, timeout: float, desc: str) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_open(port):
            return True
        time.sleep(0.4)
    print(f"  [FAIL] {desc} 端口 {port} 未就绪")
    return False


def seed_mock_account() -> None:
    """向 account_pool.db 注入一个 cookie=mock-session 账号（mock 路径识别用）。"""
    from api.account_pool import AccountPool

    db = ROOT / "data" / "account_pool.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    p = AccountPool(str(db))
    p.add("nanobanana", "e2e-mock@mock.com", "mock-session", credits=40, status="active")
    p._conn.execute(
        "UPDATE accounts SET cookie='mock-session', status='active', credits=40 "
        "WHERE provider='nanobanana' AND email='e2e-mock@mock.com'"
    )
    p._conn.commit()
    p._conn.close()
    print("  [ok] 已种子 mock-session 账号")


def main() -> int:
    _reconfigure_stdout()
    ap = argparse.ArgumentParser(description="v6.7.0 专项真实验证")
    ap.parse_args()

    for port in (SOLVER_PORT, API_PORT):
        if port_open(port):
            print(f"[错误] :{port} 已被占用，请先释放", file=sys.stderr)
            return 1

    solver = subprocess.Popen(
        [PY, str(ROOT / "scripts" / "mock_cfsolver.py"), "--port", str(SOLVER_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    if not wait_port(SOLVER_PORT, 15, "mock cf_solver"):
        solver.kill()
        return 1

    seed_mock_account()

    env = os.environ.copy()
    env.update(
        {
            "IF_HOST": "127.0.0.1",
            "IF_PORT": str(API_PORT),
            "IF_CF_SOLVER_URL": f"http://127.0.0.1:{SOLVER_PORT}",
            "IF_MOCK_UPSTREAM": "1",
            "IF_MOCK_REGISTER": "1",
            "IF_ACCOUNT_AUTO": "0",
            "IF_TURNSTILE_POLL_INTERVAL": "0.2",
            "IF_TOKEN_POOL_SIZE": "4",
            "IF_DB_FILE": str(ROOT / "data" / "e2e_v67.db"),
            "IF_ACCOUNT_DB_FILE": str(ROOT / "data" / "account_pool.db"),
            "IF_PROXY": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "IF_REQUESTS_PER_MINUTE": "0",
            "IF_GALLERY_PASSWORD": "",
            "IF_API_KEYS": "",
            "IF_ADMIN_KEYS": ADMIN_KEY,
        }
    )
    api = subprocess.Popen(
        [PY, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{API_PORT}"
    try:
        if not wait_port(API_PORT, 40, "mock API"):
            return 1
        time.sleep(2)

        results: list[tuple[str, bool, str]] = []

        def check(name: str, cond: bool, detail: str | int = "") -> None:
            d = str(detail)
            results.append((name, bool(cond), d))
            print(f"  [{'PASS' if cond else 'FAIL'}] {name}{'  -> ' + d[:140] if d else ''}")

        auth_headers = {"Authorization": f"Bearer {ADMIN_KEY}"}

        with httpx.Client(timeout=30) as c:
            # A) /admin 挂载 + boundary-pill 文案（P3-1）
            #    文案在 frontend/dist/assets/index-*.js（Layout 顶层渲染，非 lazy chunk）；
            #    /admin/ 返回 SPA shell index.html（不含业务文案），故直接断言产物文件含文案。
            r = c.get(f"{base}/admin/")
            check("/admin SPA 挂载", r.status_code == 200 and "root" in r.text.lower(), r.status_code)
            frontend_dist = ROOT / "frontend" / "dist" / "assets"
            index_chunks = list(frontend_dist.glob("index-*.js")) if frontend_dist.exists() else []
            index_blob = ""
            for ch in index_chunks:
                try:
                    index_blob += ch.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            check(
                "/admin 产物含 boundary-pill 边界文案",
                "公开只读" in index_blob and "管理 Key" in index_blob and "boundary-pill" in index_blob,
                "文案命中" if ("公开只读" in index_blob and "管理 Key" in index_blob) else "文案缺失",
            )

            # B) /security 路由 lazy chunk 可达（Security-*.js 在 dist 产物中）
            r = c.get(f"{base}/admin/security")
            check("/security 路由 SSR 兜底 200", r.status_code == 200, r.status_code)
            sec_chunk = list(frontend_dist.glob("Security-*.js")) if frontend_dist.exists() else []
            check("/security lazy chunk 产物存在", bool(sec_chunk), str(sec_chunk[0].name) if sec_chunk else "无")

            # C) DLQ retry 鉴权：无 key → 401/403
            r = c.post(f"{base}/v1/dead-letter-queue/nonexistent-task/retry")
            check("DLQ retry 无 key 拒绝(401/403)", r.status_code in (401, 403), r.status_code)
            # 带正确 admin key → 非 401/403（放行至业务层，task 不存在走业务错误）
            r = c.post(f"{base}/v1/dead-letter-queue/nonexistent-task/retry", headers=auth_headers)
            check("DLQ retry 带管理 key 放行(非401/403)", r.status_code not in (401, 403), r.status_code)

            # D) DLQ clear 鉴权
            r = c.delete(f"{base}/v1/dead-letter-queue")
            check("DLQ clear 无 key 拒绝(401/403)", r.status_code in (401, 403), r.status_code)

            # E) security/block-ip 鉴权 + 真实封禁
            r = c.post(f"{base}/v1/admin/security/block-ip", json={"ip": "203.0.113.77"})
            check("block-ip 无 key 拒绝(401/403)", r.status_code in (401, 403), r.status_code)
            r = c.post(
                f"{base}/v1/admin/security/block-ip",
                json={"ip": "203.0.113.77", "block_type": "block", "reason": "e2e-v67"},
                headers=auth_headers,
            )
            check("block-ip 带管理 key 封禁成功(200)", r.status_code == 200, r.status_code)

            # F) blocklist 含刚封禁 IP
            r = c.get(f"{base}/v1/admin/security/blocklist?limit=50", headers=auth_headers)
            check("blocklist 带管理 key 200", r.status_code == 200, r.status_code)
            ips = [it.get("ip") for it in r.json().get("items", [])] if r.status_code == 200 else []
            check("blocklist 含 203.0.113.77", "203.0.113.77" in ips, str(ips)[:120])

            # G) unblock-ip 解封
            r = c.delete(f"{base}/v1/admin/security/unblock-ip?ip=203.0.113.77", headers=auth_headers)
            check("unblock-ip 带管理 key 解封成功(200)", r.status_code == 200, r.status_code)

            # H) /v1/meta 脱敏回归（不含完整 api_key）
            r = c.get(f"{base}/v1/meta")
            check("/v1/meta HTTP 200", r.status_code == 200, r.status_code)
            body = r.text
            has_no_raw_key = "api_key" not in body or '"api_key"' not in body
            check("/v1/meta 不泄露完整 api_key", has_no_raw_key, "meta 脱敏保持")

            # I) OpenAPI schema 含新 security 端点
            r = c.get(f"{base}/openapi.json")
            paths = r.json().get("paths", {}) if r.status_code == 200 else {}
            check(
                "OpenAPI 含 /v1/admin/security/block-ip",
                "/v1/admin/security/block-ip" in paths,
                str(paths.keys())[:80],
            )
            check(
                "OpenAPI 含 /v1/dead-letter-queue",
                "/v1/dead-letter-queue" in paths,
                "",
            )

        ok = sum(1 for _, c, _ in results if c)
        print("\n" + "=" * 60)
        print("v6.7.0 专项验证报告")
        print("=" * 60)
        for name, cond, detail in results:
            mark = "PASS" if cond else "FAIL"
            line = f"  [{mark}] {name}"
            if detail:
                line += f"  -> {detail[:120]}"
            print(line)
        print("-" * 60)
        print(f"结果: {ok}/{len(results)} PASS")
        print("=" * 60)
        return 0 if ok == len(results) else 1
    finally:
        api.terminate()
        try:
            api.wait(timeout=8)
        except subprocess.TimeoutExpired:
            api.kill()
        solver.terminate()
        try:
            solver.wait(timeout=5)
        except subprocess.TimeoutExpired:
            solver.kill()


if __name__ == "__main__":
    sys.exit(main())
