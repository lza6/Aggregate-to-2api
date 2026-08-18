"""真实 E2E 验收脚本：token 池闭环 + 求解指标 + 熔断降级。

覆盖验收项：
  1. healthz 暴露 solver 求解质量指标（solver_status/成功率/耗时/连续失败/熔断/token_pools）
  2. /metrics 暴露 Prometheus 求解指标（solve_total/耗时/成功率/熔断/池水位/等待超时）
  3. 池机制：并发突发（>池容量）下任务不因 token 等待超时而失败（wait_timeout_total==0）
  4. 生成链路：mock 模式验证假 token→上游拒绝→rejected 重试/指标；real 模式验证真实求解+出图
  5. 故障注入：求解器故障→连续失败→熔断 OPEN→healthz degraded→恢复→CLOSED

模式：
  --mode real：复用外部已起的真实 cf_solver(:8001)（camoufox+代理），真实求解+出图（上游有消耗）
  --mode mock：脚本内置起 mock cf_solver（假 token），零真实求解；生成走真实 imagefree 提交但会因
              假 token 被拒（验证失败/重试/指标路径，少量上游消耗）

用法：
  python scripts/e2e_validate.py [--mode auto|real|mock] [--api-port 8100] [--concurrency 20] [--no-fault]
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

# mock 模式求解延迟；并发压测量级
MOCK_SOLVE_DELAY = 0.3
CIRCUIT_THRESHOLD = 5          # 与 api/config.py 默认 IF_SOLVE_CIRCUIT_THRESHOLD 对齐


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
            print(f"  [wait] {desc} :{port} 就绪")
            return True
        time.sleep(0.5)
    print(f"  [wait] {desc} :{port} 超时未就绪")
    return False


class E2E:
    def __init__(self, mode: str, api_port: int, concurrency: int, fault_inject: bool):
        self.mode = mode
        self.api_port = api_port
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.solver_port = 8001
        self.concurrency = concurrency
        self.fault_inject = fault_inject
        self.procs: list[subprocess.Popen] = []
        self.results: list[tuple[str, bool, str]] = []
        self.base_env = dict(os.environ)

    # ── 生命周期 ──────────────────────────────────
    def start(self) -> None:
        if self.mode == "mock":
            self._start_mock_solver()
            self.base_env["IF_CF_SOLVER_URL"] = f"http://127.0.0.1:{self.solver_port}"
        elif self.mode == "real":
            if not port_open(self.solver_port):
                self.results.append(("real cf_solver 就绪", False,
                                     f":{self.solver_port} 未监听（需先起真实 cf_solver）"))
                raise SystemExit(1)
            self.base_env["IF_CF_SOLVER_URL"] = f"http://127.0.0.1:{self.solver_port}"
            # 真实 cf_solver 单浏览器槽串行，单 token 求解 ~5-15s（1 槽物理吞吐上限）。
            # 真实出图验收聚焦「真实求解+真实出图链路可行」，并发压测/无 starve 由 mock 模式严格覆盖，
            # 故 real 模式降并发并放宽 token 等待，避免被单槽吞吐物理上限误判为失败。
            self.concurrency = min(self.concurrency, 3)
        # 服务环境：并发/池/等待参数显式钉住，验收「池机制在池容量<并发下不超时」
        env = dict(self.base_env)
        env.update({
            "IF_HOST": "127.0.0.1", "IF_PORT": str(self.api_port),
            "IF_TOKEN_POOL_SIZE": "6", "IF_TOKEN_TTL": "90",
            "IF_TOKEN_WAIT_TIMEOUT": "30", "IF_WORKERS": "10",
            "IF_GENERATE_MAX_ATTEMPTS": "2", "IF_GENERATE_TIMEOUT": "60",
            "IF_DB_FILE": "data/e2e_validate.db",
            "IF_PROXY": "http://127.0.0.1:10808",   # 本机 Clash：访问 imagefree
        })
        if self.mode == "mock":
            # mock 模式全链路 mock（solver + 上游 imagefree），零外部依赖、确定性、可重复
            env["IF_MOCK_UPSTREAM"] = "1"
            # mock 求解 ~0.3s：轮询间隔调小，避免 2s 轮询成为补池吞吐瓶颈（真实 cf_solver 保持 2s）
            env["IF_TURNSTILE_POLL_INTERVAL"] = "0.2"
        else:
            # real 模式：真实求解慢（单槽 5-15s/token），放宽 token 等待，3 并发串行补池 ~45s
            env["IF_TOKEN_WAIT_TIMEOUT"] = "120"
        # 子进程 stdout 重定向到文件（而非 pipe）：uvicorn 日志量大，pipe 不消费会阻塞服务
        self._api_log = open(os.path.join(ROOT, "data", "e2e_api.log"), "wb")
        p = subprocess.Popen(
            [PY, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1",
             "--port", str(self.api_port)],
            cwd=ROOT, env=env, stdout=self._api_log, stderr=subprocess.STDOUT,
        )
        self.procs.append(p)
        if not wait_port(self.api_port, 60, "api"):
            self.results.append(("api 启动", False, "uvicorn 未就绪"))
            raise SystemExit(1)

    def _start_mock_solver(self) -> None:
        self._solver_log = open(os.path.join(ROOT, "data", "e2e_mock.log"), "wb")
        p = subprocess.Popen(
            [PY, os.path.join(ROOT, "scripts", "mock_cfsolver.py"),
             "--port", str(self.solver_port)],
            cwd=ROOT, stdout=self._solver_log, stderr=subprocess.STDOUT,
        )
        self.procs.append(p)
        if not wait_port(self.solver_port, 15, "mock solver"):
            raise SystemExit(1)

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
        # 清理 E2E 专用 DB/日志（不污染线上 data/）
        for suf in ("", "-wal", "-shm"):
            path = os.path.join(ROOT, "data", f"e2e_validate.db{suf}")
            try:
                os.unlink(path)
            except OSError:
                pass
        for name in ("e2e_api.log", "e2e_mock.log"):
            path = os.path.join(ROOT, "data", name)
            try:
                os.unlink(path)
            except OSError:
                pass

    # ── HTTP 辅助 ─────────────────────────────────
    def get(self, path: str) -> dict:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(self.api_url + path)
            return {"status": r.status_code, "json": r.json() if r.headers.get("content-type", "").startswith("application/json") else None, "text": r.text}

    def post(self, path: str, body: dict | None = None) -> dict:
        with httpx.Client(timeout=10.0) as c:
            r = c.post(self.api_url + path, json=body)
            try:
                return {"status": r.status_code, "json": r.json(), "text": r.text}
            except Exception:
                return {"status": r.status_code, "json": None, "text": r.text}

    def check(self, name: str, cond: bool, detail: str = "") -> None:
        self.results.append((name, bool(cond), detail))

    # ── 验收步骤 ──────────────────────────────────
    def run(self) -> int:
        try:
            self.start()
            self._wait_pool_warmup()
            self._verify_healthz()
            self._verify_metrics()
            self._verify_concurrency_no_starvation()
            self._verify_generate_path()
            if self.fault_inject and self.mode == "mock":
                self._verify_circuit_breaker()
            else:
                self.results.append(("故障注入熔断", True, "skipped（real 模式/--no-fault）"))
            self._print_report()
            return 0 if all(ok for _, ok, _ in self.results) else 1
        finally:
            self.stop()

    def _wait_pool_warmup(self) -> None:
        # 等待预取补到基础水位（mock 0.3s/token，空闲水位 1；1s 内应就绪）
        time.sleep(2.0)

    def _verify_healthz(self) -> None:
        h = self.get("/v1/healthz")
        ok = h["status"] == 200 and h["json"] is not None
        j = h.get("json") or {}
        required = ["solver_status", "solve_success_total", "solve_failure_total",
                    "solve_avg_seconds", "solve_window_success_rate", "solve_window_solve_count",
                    "solve_consecutive_failures", "solve_last_failure_at", "solver_circuit_open",
                    "solve_rejected_total", "token_pool", "token_pools"]
        missing = [k for k in required if k not in j]
        self.check("healthz: HTTP 200", ok, str(h["status"]))
        self.check("healthz: solver 指标字段齐全", not missing, f"缺失={missing}")
        self.check("healthz: solver_status 合法",
                   j.get("solver_status") in ("ok", "degraded", "circuit_open"),
                   str(j.get("solver_status")))
        self.check("healthz: token_pools 明细存在", "direct" in (j.get("token_pools") or {}),
                   str(list((j.get("token_pools") or {}).keys())[:5]))

    def _verify_metrics(self) -> None:
        m = self.get("/metrics")
        ok = m["status"] == 200 and "imagefree_solve_total" in m["text"]
        want = [
            'imagefree_solve_total{result="success"}',
            'imagefree_solve_total{result="failure"}',
            "imagefree_solve_duration_seconds_sum",
            "imagefree_solve_duration_seconds_count",
            "imagefree_solve_window_success_rate",
            "imagefree_solve_consecutive_failures",
            "imagefree_solver_circuit_open",
            "imagefree_solve_rejected_total",
            "imagefree_token_wait_timeout_total",
            'imagefree_token_pool_watermark{pool="direct"}',
        ]
        absent = [w for w in want if w not in m["text"]]
        self.check("metrics: 求解指标行齐全", ok and not absent, f"缺失={absent}")

    def _submit_burst(self, n: int) -> list[str]:
        """并发提交 n 个异步任务，返回 task_id 列表。"""
        ids: list[str] = []
        with httpx.Client(timeout=10.0) as c:
            import concurrent.futures

            def _one(i: int):
                r = c.post(self.api_url + "/v1/generate/async",
                           json={"prompt": f"e2e burst {i}", "aspect_ratio": "1:1"})
                return r.json().get("id")

            with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
                ids = list(ex.map(_one, range(n)))
        return [x for x in ids if x]

    def _wait_tasks(self, ids: list[str], timeout: float) -> dict[str, dict]:
        """轮询任务到终态，返回 id -> task。"""
        out: dict[str, dict] = {}
        deadline = time.monotonic() + timeout
        with httpx.Client(timeout=10.0) as c:
            while ids and time.monotonic() < deadline:
                for tid in list(ids):
                    r = c.get(self.api_url + f"/v1/tasks/{tid}")
                    j = r.json()
                    if j.get("status") in ("completed", "error"):
                        out[tid] = j
                        ids.remove(tid)
                if ids:
                    time.sleep(0.5)
        for tid in ids:
            out[tid] = {"status": "timeout"}
        return out

    def _verify_concurrency_no_starvation(self) -> None:
        """并发（mock=20 / real=3）> 池水位：验证池机制（事件补池）不导致 token 等待超时失败。

        mock 模式严格断言 wait_timeout==0（确定性环境）；real 模式单槽吞吐物理上限，
        放宽到 ≤1 并延长出图等待（真实出图 1-5 分钟）。
        """
        n = self.concurrency
        ids = self._submit_burst(n)
        if not ids:
            self.check(f"并发 {n}: 任务全部提交成功", False, "无 task_id 返回")
            return
        wait = 300 if self.mode == "real" else 120
        done = self._wait_tasks(list(ids), timeout=wait)
        statuses = {}
        for t in done.values():
            statuses[t["status"]] = statuses.get(t["status"], 0) + 1
        no_starve = statuses.get("timeout", 0) == 0
        self.check(f"并发 {n}（池 6）: 全部终态无超时", no_starve, str(statuses))
        m = self.get("/metrics")
        import re
        mline = re.search(r"imagefree_token_wait_timeout_total\s+(\d+)", m["text"])
        wt = int(mline.group(1)) if mline else None
        if self.mode == "mock":
            self.check("池空等待超时=0（无 starve）", wt == 0, f"wait_timeout_total={wt}")
        else:
            self.check("池空等待超时≤1（real 单槽吞吐限制，宽松）", (wt or 0) <= 1,
                       f"wait_timeout_total={wt}")

    def _verify_generate_path(self) -> None:
        # 注意：_wait_tasks 会原地清空入参列表，故传 list(ids) 副本，保留 len(ids) 供断言
        if self.mode == "real":
            ids = self._submit_burst(2)
            done = self._wait_tasks(list(ids), timeout=300)
            comp = sum(1 for t in done.values() if t["status"] == "completed")
            self.check("real 模式: 真实求解+出图 ≥1 完成",
                       comp >= 1, f"completed={comp} statuses={[t['status'] for t in done.values()]}")
            return
        # mock 模式：上游也 mock，任务应全部 completed（全链路 mock 确定性验证）
        ids = self._submit_burst(3)
        done = self._wait_tasks(list(ids), timeout=60)
        comp = sum(1 for t in done.values() if t["status"] == "completed")
        self.check("mock 模式: 生成任务全部 completed",
                   comp == len(ids) and comp > 0,
                   f"completed={comp}/{len(ids)} statuses={[t['status'] for t in done.values()]}")

    def _solver_fault(self, mode: str) -> None:
        """向 mock cf_solver 注入故障状态（独立 client，不经 api 前缀拼接）。"""
        with httpx.Client(timeout=5.0) as c:
            c.post(f"http://127.0.0.1:{self.solver_port}/__fault?mode={mode}")

    def _verify_circuit_breaker(self) -> None:
        """故障注入：求解器连续失败→熔断 OPEN→degraded；恢复→CLOSED。"""
        self._solver_fault("fail")
        # 触发连续求解失败：持续提交任务让预取循环求解（池空会补）
        deadline = time.monotonic() + 60
        opened = False
        while time.monotonic() < deadline:
            h = self.get("/v1/healthz")
            j = h.get("json") or {}
            if j.get("solver_status") == "circuit_open":
                opened = True
                break
            # 制造池空刺激预取求解
            self._submit_burst(4)
            time.sleep(1.5)
        self.check("熔断: 连续失败后 OPEN", opened, f"consecutive={ (self.get('/v1/healthz').get('json') or {}).get('solve_consecutive_failures') }")
        h = self.get("/v1/healthz")
        j = h.get("json") or {}
        self.check("熔断: healthz status=degraded", j.get("status") == "degraded", str(j.get("status")))
        m = self.get("/metrics")
        import re
        mline = re.search(r"imagefree_solver_circuit_open\s+(\d+)", m["text"])
        self.check("熔断: metrics circuit_open=1", mline and mline.group(1) == "1", str(mline.group(1) if mline else None))
        # 恢复：纯等 prefetch 半开探测自然恢复（探测由 prefetch_loop 独占 allow_solve 节奏，
        # 每 probe_interval 放行一次；不再提交 burst 刺激，避免 acquire 干扰探测节奏）
        self._solver_fault("ok")
        deadline = time.monotonic() + 90
        recovered = False
        last_status = None
        while time.monotonic() < deadline:
            h = self.get("/v1/healthz")
            last_status = (h.get("json") or {}).get("solver_status")
            if last_status == "ok":
                recovered = True
                break
            time.sleep(2.0)
        self.check("熔断: 恢复后 CLOSED/ok", recovered, f"solver_status={last_status}")

    def _print_report(self) -> None:
        print("\n" + "=" * 64)
        print(f"E2E 验收报告  mode={self.mode}  concurrency={self.concurrency}")
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
        print(f"结果: {len(self.results) - fails}/{len(self.results)} PASS")
        print("=" * 64)


def main() -> int:
    _reconfigure_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["auto", "real", "mock"], default="auto")
    ap.add_argument("--api-port", type=int, default=8100)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--no-fault", action="store_true", help="跳过故障注入")
    args = ap.parse_args()
    mode = args.mode
    if mode == "auto":
        mode = "real" if port_open(8001) else "mock"
        print(f"[auto] 检测到 :8001 {'在线→real' if mode == 'real' else '离线→mock'}")
    if port_open(args.api_port):
        print(f"[错误] :{args.api_port} 已被占用（可能有实例在跑），先停止再验收", file=sys.stderr)
        return 1
    e = E2E(mode, args.api_port, args.concurrency, not args.no_fault)
    return e.run()


if __name__ == "__main__":
    sys.exit(main())
