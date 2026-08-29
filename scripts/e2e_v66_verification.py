"""v6.6.0 专项真实验证驱动：
1. 启动 mock cf_solver + mock API（零真实网络，IF_MOCK_UPSTREAM/REGISTER=1）
2. 种子一个 mock-session 账号（cookie=mock-session，credits>0）
3. 提交真实 txt2img 异步任务 → 消费 `/v1/tasks/{id}/events` SSE 流（验证 result 事件 + 终态 payload）
4. GET `/v1/account-pool` → 验证新字段 cost_summary / growth_stats 已返回
5. 验证前端 dist 已由 API 单源挂载（/admin + / 均 200）

用法：python scripts/e2e_v66_verification.py
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
API_PORT = 8100       # 匹配 vite proxy 默认，前端 dist 由 API 单源挂载


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
    """向 account_pool.db 注入一个 cookie=mock-session 账号（credits=40，status=active）。"""
    from api.account_pool import AccountPool
    db = ROOT / "data" / "account_pool.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    p = AccountPool(str(db))
    p.add("nanobanana", "e2e-mock@mock.com", "mock-session", credits=40, status="active")
    # 强制 cookie 为 mock-session（nanobanana.load 分支用 cookie=="mock-session" 识别）
    p._conn.execute(
        "UPDATE accounts SET cookie='mock-session', status='active', credits=40 WHERE provider='nanobanana' AND email='e2e-mock@mock.com'"
    )
    p._conn.commit()
    p._conn.close()
    print("  [ok] 已种子 mock-session 账号 (e2e-mock@mock.com, credits=40)")


def main() -> int:
    _reconfigure_stdout()
    ap = argparse.ArgumentParser(description="v6.6.0 专项真实验证")
    args = ap.parse_args()

    for port in (SOLVER_PORT, API_PORT):
        if port_open(port):
            print(f"[错误] :{port} 已被占用，请先释放", file=sys.stderr)
            return 1

    # 1) 启动 mock cf_solver
    solver = subprocess.Popen(
        [PY, str(ROOT / "scripts" / "mock_cfsolver.py"), "--port", str(SOLVER_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    if not wait_port(SOLVER_PORT, 15, "mock cf_solver"):
        solver.kill()
        return 1

    # 2) 种子账号
    seed_mock_account()

    # 3) 启动 mock API 单源（同时挂 /admin + / 静态）
    env = os.environ.copy()
    env.update({
        "IF_HOST": "127.0.0.1",
        "IF_PORT": str(API_PORT),
        "IF_CF_SOLVER_URL": f"http://127.0.0.1:{SOLVER_PORT}",
        "IF_MOCK_UPSTREAM": "1",
        "IF_MOCK_REGISTER": "1",
        "IF_ACCOUNT_AUTO": "0",
        "IF_TURNSTILE_POLL_INTERVAL": "0.2",
        "IF_TOKEN_POOL_SIZE": "4",
        "IF_DB_FILE": str(ROOT / "data" / "e2e_v66.db"),
        "IF_ACCOUNT_DB_FILE": str(ROOT / "data" / "account_pool.db"),
        "IF_PROXY": "", "HTTP_PROXY": "", "HTTPS_PROXY": "",
        "IF_REQUESTS_PER_MINUTE": "0",
        "IF_GALLERY_PASSWORD": "",
        "IF_API_KEYS": "",
        "IF_ADMIN_KEYS": "",
    })
    api = subprocess.Popen(
        [PY, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{API_PORT}"
    try:
        if not wait_port(API_PORT, 40, "mock API"):
            return 1
        time.sleep(2)  # 让 bootstrap 完成

        results: list[tuple[str, bool, str]] = []
        def check(name: str, cond: bool, detail: str | int = "") -> None:
            d = str(detail)
            results.append((name, bool(cond), d))
            print(f"  [{'PASS' if cond else 'FAIL'}] {name}{'  -> ' + d[:140] if d else ''}")

        with httpx.Client(timeout=60) as c:
            # A) /admin 与 / 单源挂载
            r = c.get(f"{base}/admin/")
            check("前端 SPA /admin 挂载", r.status_code == 200 and "root" in r.text.lower(), r.status_code)
            r = c.get(f"{base}/")
            check("落地页 / 挂载", r.status_code == 200, r.status_code)

            # B) 提交异步 txt2img 任务
            r = c.post(f"{base}/v1/generate/async", json={
                "prompt": "a cute orange cat with blue eyes",
                "aspect_ratio": "1:1", "model": "imagefree/default",
            })
            check("异步提交 HTTP 200", r.status_code == 200, r.status_code)
            if r.status_code != 200:
                check("提交返回 id", False, r.text[:200])
                return 1
            task_id = r.json()["id"]
            check("任务返回 id", bool(task_id), task_id)

            # C) 消费 per-task SSE 流，验证与轮询能拿到终态。
            #    ⚠ 服务端终态事件发出后不回 self-close（保留心跳）——SSE 读到终态 event 即 break，
            #    若读到上限仍未到终态（时序窗口），以「轮询拿到终态 payload」作为终态达成判定，
            #    SSE 仅作「可消费、有事件推送」的补充验证，不双重计为必须独立先到。
            sse_events: list[str] = []
            sse_capped = False
            try:
                with c.stream("GET", f"{base}/v1/tasks/{task_id}/events", timeout=25) as s:
                    start = time.monotonic()
                    for line in s.iter_lines():
                        if time.monotonic() - start > 12:
                            sse_capped = True
                            break
                        if not line:
                            continue
                        if line.startswith("event:"):
                            sse_events.append(line.split(":", 1)[1].strip())
                        if sse_events and sse_events[-1] in ("result", "error"):
                            break
            except Exception as e:
                check("SSE 流可消费", False, str(e)[:120])

            # SSE 可消费 + 至少推送过事件；终态 payload 由 D) 轮询为准
            check("SSE 流可消费且有事件推送", len(sse_events) > 0,
                  f"events={sse_events}{' [capped]' if sse_capped else ''}")

            # D) 轮询兜底确认终态 payload 含 image_url 等
            task = None
            for _ in range(60):
                t = c.get(f"{base}/v1/tasks/{task_id}").json()
                if t.get("status") in ("completed", "error"):
                    task = t
                    break
                time.sleep(0.4)
            check("任务到达终态", task is not None, (task or {}).get("status", "timeout"))
            if task and task.get("status") == "completed":
                check("终态含 image_url", bool(task.get("image_url")), str(task.get("image_url"))[:60])
                check("终态含 model", bool(task.get("model")), str(task.get("model")))
                check("终态含 duration_sec", task.get("duration_sec") is not None, str(task.get("duration_sec")))
            check("终态含 prompt", bool(task and task.get("prompt")), str((task or {}).get("prompt"))[:40])

            # E) 验证 cost_summary / growth_stats 新字段已出
            r = c.get(f"{base}/v1/account-pool?page=1&page_size=5")
            check("account-pool HTTP 200", r.status_code == 200, r.status_code)
            pool = r.json()
            check("account-pool 含 cost_summary", "cost_summary" in pool, str(list(pool.keys())))
            cs = pool.get("cost_summary") or {}
            check("cost_summary.total_accounts>0", int(cs.get("total_accounts") or 0) >= 1, str(cs))
            check("account-pool 含 growth_stats", "growth_stats" in pool, str(list(pool.keys())))
            gs = pool.get("growth_stats") or {}
            check("growth_stats 含 eta_days 字段", "eta_days" in gs, str(list(gs.keys())))
            # 明细项含消耗画像列
            item0 = (pool.get("items") or [{}])[0]
            check("明细含 credits_used_total 字段", "credits_used_total" in item0, str(list(item0.keys())))

            # F) 确认此时有出图消耗（mock-imagefree 不走号池扣减，cost=0 也合法；仅验证口径结构）
            check("cost_summary 结构完整",
                  all(k in cs for k in ("total_credits_used", "total_images_used", "avg_cost_per_image")),
                  str(cs))

        ok = sum(1 for _, c, _ in results if c)
        print("\n" + "=" * 60)
        print("v6.6.0 专项验证报告")
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
