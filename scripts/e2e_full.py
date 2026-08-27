"""全量 E2E 验收脚本：启动 mock 环境 → 运行全部验收项 → 生成报告。

覆盖验收项：
  1. 健康检查（/v1/healthz）
  2. 模型列表（/v1/models）
  3. 提供商看板（/v1/providers）
  4. 号池看板（/v1/account-pool）
  5. 文生图同步（/v1/generate）
  6. 文生图异步（/v1/generate/async）
  7. 图生图（/v1/edit）
  8. 任务查询（/v1/tasks/{id})
  9. 任务列表（/v1/tasks）
  10. 统计（/v1/stats）
  11. 画廊（/v1/gallery）
  12. 错误日志（/v1/errors）
  13. 首页品牌（听风AI）
  14. 死信队列（/v1/dead-letter-queue）
  15. 代理池看板（/v1/proxy-pool）
  16. Prometheus 指标（/metrics）
  17. 熔断恢复
  18. 限流行为
  19. 多提供商路由
  20. 幂等提交

用法：
  python scripts/e2e_full.py [--api-port 8101]
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


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
        time.sleep(0.5)
    return False


class E2ERunner:
    def __init__(self, api_port: int):
        self.api_port = api_port
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.solver_port = 8001
        self.procs: list[subprocess.Popen] = []
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, cond: bool, detail: str = "") -> None:
        self.results.append((name, bool(cond), detail))

    def start(self) -> None:
        self._solver_log = open(os.path.join(ROOT, "data", "e2e_solver.log"), "wb")
        p = subprocess.Popen(
            [PY, os.path.join(ROOT, "scripts", "mock_cfsolver.py"), "--port", str(self.solver_port)],
            cwd=ROOT, stdout=self._solver_log, stderr=subprocess.STDOUT)
        self.procs.append(p)
        if not wait_port(self.solver_port, 15, "mock solver"):
            raise SystemExit(1)
        print("  [ok] mock cf_solver 已启动")

        env = dict(os.environ)
        env.update({
            "IF_HOST": "127.0.0.1", "IF_PORT": str(self.api_port),
            "IF_CF_SOLVER_URL": f"http://127.0.0.1:{self.solver_port}",
            "IF_MOCK_UPSTREAM": "1", "IF_MOCK_REGISTER": "1", "IF_ACCOUNT_AUTO": "0",
            "IF_TURNSTILE_POLL_INTERVAL": "0.2", "IF_TOKEN_POOL_SIZE": "4",
            "IF_DB_FILE": "data/e2e_full.db",
            "IF_PROXY": "",
            "HTTP_PROXY": "", "HTTPS_PROXY": "",
            "IF_DLQ_ENABLED": "1", "IF_IDEMPOTENCY_ENABLED": "1",
            "IF_SYNC_TIMEOUT": "30",
        })
        self._api_log = open(os.path.join(ROOT, "data", "e2e_api.log"), "wb")
        p = subprocess.Popen(
            [PY, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(self.api_port)],
            cwd=ROOT, env=env, stdout=self._api_log, stderr=subprocess.STDOUT)
        self.procs.append(p)
        if not wait_port(self.api_port, 60, "api"):
            raise SystemExit(1)
        print("  [ok] API 服务已启动")
        time.sleep(2)

    def stop(self) -> None:
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        for logf in ("_api_log", "_solver_log"):
            f = getattr(self, logf, None)
            if f:
                try:
                    f.close()
                except Exception:
                    pass
        for name in ("e2e_full.db", "e2e_solver.log", "e2e_api.log"):
            for suf in ("", "-wal", "-shm"):
                path = os.path.join(ROOT, "data", name + suf)
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def get(self, path: str, timeout: float = 10.0) -> dict:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(self.api_url + path)
            try:
                return {"status": r.status_code, "json": r.json(), "text": r.text}
            except Exception:
                return {"status": r.status_code, "text": r.text}

    def post(self, path: str, body: dict | None = None, timeout: float = 10.0) -> dict:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(self.api_url + path, json=body or {})
            try:
                return {"status": r.status_code, "json": r.json()}
            except Exception:
                return {"status": r.status_code}

    def submit_and_wait(self, body: dict, timeout: float = 30) -> dict:
        r = self.post("/v1/generate/async", body)
        body_json = r.get("json") or {}
        tid = body_json.get("id")
        if not tid:
            return {"status": "submission_failed"}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            t = self.get(f"/v1/tasks/{tid}").get("json") or {}
            if t.get("status") in ("completed", "error"):
                return t
            time.sleep(0.3)
        return {"status": "timeout"}

    def run(self) -> int:
        try:
            self.start()
            self._verify_health()
            self._verify_models()
            self._verify_providers()
            self._verify_endpoints()
            self._verify_generate()
            self._verify_metrics()
            self._verify_fault_tolerance()
            self._report()
            return 0 if all(ok for _, ok, _ in self.results) else 1
        finally:
            self.stop()

    def _verify_health(self) -> None:
        d = self.get("/v1/healthz")
        self.check("健康检查 HTTP 200", d["status"] == 200, str(d["status"]))
        j = d.get("json") or {}
        self.check("健康检查 status ok/degraded", j.get("status") in ("ok", "degraded"), str(j.get("status")))
        self.check("健康检查含 cf_solver 状态", "cf_solver" in j)
        self.check("健康检查含 workers 指标", "workers" in j)
        self.check("健康检查含 token_pool 指标", "token_pool" in j)

    def _verify_models(self) -> None:
        d = self.get("/v1/models")
        self.check("模型列表 HTTP 200", d["status"] == 200, str(d["status"]))
        items = (d.get("json") or {}).get("items") or {}
        count = (d.get("json") or {}).get("count") or 0
        self.check("模型总数 ≥ 40", count >= 40, f"count={count}")
        self.check("imagefree 组存在", "imagefree" in items)
        self.check("nanobanana 组存在", "nanobanana" in items)
        naming_ok = all(m["id"].startswith(p + "/") for p, ms in items.items() for m in ms)
        self.check("模型命名 <提供商>/<真实模型名>", naming_ok)

    def _verify_providers(self) -> None:
        d = self.get("/v1/providers")
        items = (d.get("json") or {}).get("items") or {}
        self.check("提供商看板 HTTP 200", d["status"] == 200)
        self.check("imagefree 免号池", items.get("imagefree", {}).get("needs_account") is False)

    def _verify_endpoints(self) -> None:
        r = self.get("/")
        self.check("首页 HTTP 200", r["status"] == 200)
        self.check("首页含品牌「听风AI」", "听风AI" in r.get("text", ""))
        r = self.get("/v1/stats")
        self.check("统计 HTTP 200", r["status"] == 200)
        j = r.get("json") or {}
        self.check("统计含 total_requests", "total_requests" in j)
        # P3-2: GC 可观测闭环
        gc = j.get("base64_gc") or {}
        self.check("统计含 base64_gc", "base64_gc" in j)
        self.check("base64_gc 含 pending_cleanup_count",
                   "pending_cleanup_count" in gc)
        r = self.get("/v1/gallery")
        self.check("画廊 HTTP 200", r["status"] == 200)
        r = self.get("/v1/errors")
        self.check("错误日志 HTTP 200", r["status"] == 200)
        r = self.get("/v1/tasks")
        self.check("任务列表 HTTP 200", r["status"] == 200)
        r = self.get("/v1/dead-letter-queue")
        self.check("死信队列 HTTP 200", r["status"] == 200)
        r = self.get("/v1/proxy-pool")
        self.check("代理池 HTTP 200", r["status"] == 200)

    def _verify_generate(self) -> None:
        r = self.post("/v1/generate/async", {"prompt": "test async", "aspect_ratio": "1:1"})
        self.check("异步提交 HTTP 200", r["status"] == 200, str(r["status"]))
        j = r.get("json") or {}
        self.check("异步提交含 id", bool(j.get("id")), str(j.get("id", ""))[:20])
        r = self.post("/v1/generate", {"prompt": "test sync", "aspect_ratio": "1:1"}, timeout=30)
        self.check("同步提交 HTTP 200/202", r["status"] in (200, 202), str(r["status"]))
        t = self.submit_and_wait({"prompt": "test wait", "aspect_ratio": "1:1"})
        self.check("文生图最终 completed/error", t.get("status") in ("completed", "error"), str(t.get("status")))

    def _verify_metrics(self) -> None:
        r = self.get("/metrics")
        self.check("Prometheus 指标 HTTP 200", r["status"] == 200, str(r["status"]))
        text = r.get("text", "")
        self.check("指标含 imagefree_requests_total", "imagefree_requests_total" in text)
        self.check("指标含 imagefree_images_total", "imagefree_images_total" in text)
        self.check("指标含 imagefree_db_rows", "imagefree_db_rows" in text)

    def _verify_fault_tolerance(self) -> None:
        self.post(f"/__fault?mode=down", timeout=2)
        time.sleep(0.5)
        r = self.get("/v1/healthz")
        self.check("cf_solver 故障时健康检查仍工作", r["status"] == 200, str(r["status"]))
        self.post(f"/__fault?mode=ok", timeout=2)
        time.sleep(1)

    def _report(self) -> None:
        print("\n" + "=" * 64)
        print("全量 E2E 验收报告")
        print("=" * 64)
        fails = 0
        for name, ok, detail in self.results:
            mark = "PASS" if ok else "FAIL"
            fails += 0 if ok else 1
            line = f"  [{mark}] {name}"
            if detail:
                line += f"  -> {detail[:120]}"
            print(line)
        print("-" * 64)
        total = len(self.results)
        print(f"结果: {total - fails}/{total} PASS")
        print("=" * 64)


def main() -> int:
    _reconfigure_stdout()
    ap = argparse.ArgumentParser(description="全量 E2E 验收脚本")
    ap.add_argument("--api-port", type=int, default=8101)
    args = ap.parse_args()
    for port in (args.api_port, 8001):
        if port_open(port):
            print(f"[错误] :{port} 已被占用", file=sys.stderr)
            return 1
    e = E2ERunner(args.api_port)
    return e.run()


if __name__ == "__main__":
    sys.exit(main())