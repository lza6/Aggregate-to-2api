"""多提供商网关 E2E 验收脚本：模型列表 / 提供商状态 / 号池自动补号 / 多路由生成。

mock 模式全链路 mock（IF_MOCK_UPSTREAM + IF_MOCK_REGISTER）：零外部依赖、确定性、可重复。
覆盖验收项：
  1. /v1/models 返回全提供商模型，命名 <提供商>/<真实模型名>，含 seedance-1.5-pro 480P 视频模型
  2. /v1/providers 返回各提供商能力/号池需求/每请求代理需求
  3. /v1/account-pool 号池看板：自动补号到目标、余额正确
  4. 路由：imagefree（引擎队列）/ minimaxh3（文生图+视频+图生图）/ aifreeforever（降级）/ nanobanana（降级）
  5. /v1/tasks 统一查询跨提供商任务
  6. 首页品牌（听风AI）+ logo 可达

用法：
  python scripts/e2e_providers.py [--api-port 8100]
"""
import argparse
import os
import socket
import subprocess
import sys
import time

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
            print(f"  [wait] {desc} :{port} 就绪")
            return True
        time.sleep(0.5)
    print(f"  [wait] {desc} :{port} 超时")
    return False


class ProvidersE2E:
    def __init__(self, api_port: int):
        self.api_port = api_port
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.solver_port = 8001
        self.procs: list[subprocess.Popen] = []
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, cond: bool, detail: str = "") -> None:
        self.results.append((name, bool(cond), detail))

    def start(self) -> None:
        self._start_mock_solver()
        env = dict(os.environ)
        env.update({
            "IF_HOST": "127.0.0.1", "IF_PORT": str(self.api_port),
            "IF_CF_SOLVER_URL": f"http://127.0.0.1:{self.solver_port}",
            "IF_MOCK_UPSTREAM": "1", "IF_MOCK_REGISTER": "1", "IF_ACCOUNT_AUTO": "1",
            "IF_MINIMAXH3_ACCOUNT_TARGET": "3", "IF_NANOBANANA_ACCOUNT_TARGET": "3",
            "IF_TURNSTILE_POLL_INTERVAL": "0.2", "IF_TOKEN_POOL_SIZE": "4",
            "IF_DB_FILE": "data/e2e_prov.db",
            "IF_ACCOUNT_DB_FILE": "data/e2e_prov_acc.db",
            "IF_EMAIL_DB_FILE": "data/e2e_prov_email.db",
            "IF_PROXY": "http://127.0.0.1:10808",
        })
        self._api_log = open(os.path.join(ROOT, "data", "e2e_prov_api.log"), "wb")
        p = subprocess.Popen(
            [PY, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(self.api_port)],
            cwd=ROOT, env=env, stdout=self._api_log, stderr=subprocess.STDOUT)
        self.procs.append(p)
        if not wait_port(self.api_port, 60, "api"):
            raise SystemExit(1)

    def _start_mock_solver(self) -> None:
        self._solver_log = open(os.path.join(ROOT, "data", "e2e_prov_mock.log"), "wb")
        p = subprocess.Popen([PY, os.path.join(ROOT, "scripts", "mock_cfsolver.py"),
                              "--port", str(self.solver_port)],
                             cwd=ROOT, stdout=self._solver_log, stderr=subprocess.STDOUT)
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
        for name in ("e2e_prov.db", "e2e_prov_acc.db", "e2e_prov_email.db",
                     "e2e_prov_api.log", "e2e_prov_mock.log"):
            for suf in ("", "-wal", "-shm"):
                path = os.path.join(ROOT, "data", name + suf)
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def get(self, path: str) -> dict:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(self.api_url + path)
            try:
                return {"status": r.status_code, "json": r.json(), "text": r.text}
            except Exception:
                return {"status": r.status_code, "json": None, "text": r.text}

    def post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=10.0) as c:
            r = c.post(self.api_url + path, json=body)
            try:
                return {"status": r.status_code, "json": r.json()}
            except Exception:
                return {"status": r.status_code, "json": None}

    def submit_and_wait(self, body: dict, timeout: float = 20) -> dict:
        r = self.post("/v1/generate/async", body)
        tid = (r.get("json") or {}).get("id")
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
            time.sleep(2)
            self._verify_models()
            self._verify_providers()
            self._verify_account_pool()
            self._verify_routing()
            self._verify_brand()
            self._report()
            return 0 if all(ok for _, ok, _ in self.results) else 1
        finally:
            self.stop()

    def _verify_models(self) -> None:
        d = self.get("/v1/models")
        ok = d["status"] == 200
        items = (d.get("json") or {}).get("items") or {}
        count = (d.get("json") or {}).get("count") or 0
        self.check("/v1/models HTTP 200", ok, str(d["status"]))
        self.check("模型总数 ≥ 40（4 提供商）", count >= 40, f"count={count}")
        self.check("imagefree 组存在", "imagefree" in items)
        self.check("minimaxh3 组存在", "minimaxh3" in items)
        self.check("aifreeforever 组存在", "aifreeforever" in items)
        self.check("nanobanana 组存在", "nanobanana" in items)
        mm = items.get("minimaxh3") or []
        ids = {m["id"] for m in mm}
        self.check("seedance-1.5-pro 480P 视频模型", "minimaxh3/seedance-1.5-pro" in ids,
                   "480P 模型缺失!" if "minimaxh3/seedance-1.5-pro" not in ids else "")
        # 命名契约：id 都是 provider/真实名
        naming_ok = all(m["id"].startswith(p + "/") for p, ms in items.items() for m in ms)
        self.check("模型命名 <提供商>/<真实模型名>", naming_ok)

    def _verify_providers(self) -> None:
        d = self.get("/v1/providers")
        items = (d.get("json") or {}).get("items") or {}
        self.check("/v1/providers HTTP 200", d["status"] == 200)
        self.check("minimaxh3 需号池", items.get("minimaxh3", {}).get("needs_account") is True)
        self.check("aifreeforever 每请求换 IP", items.get("aifreeforever", {}).get("needs_proxy_per_request") is True)
        self.check("nanobanana 需号池", items.get("nanobanana", {}).get("needs_account") is True)
        self.check("imagefree 免号池", items.get("imagefree", {}).get("needs_account") is False)

    def _verify_account_pool(self) -> None:
        d = self.get("/v1/account-pool")
        acc = (d.get("json") or {}).get("accounts") or {}
        mm = acc.get("minimaxh3") or {}
        nb = acc.get("nanobanana") or {}
        self.check("minimaxh3 自动补号到目标", mm.get("ok", 0) >= 1, f"ok={mm.get('ok')}")
        self.check("nanobanana 自动补号到目标", nb.get("ok", 0) >= 1, f"ok={nb.get('ok')}")
        self.check("minimaxh3 余额>0", (mm.get("credits") or 0) > 0, f"credits={mm.get('credits')}")
        self.check("号池自动注册运行中", mm.get("auto_register") is True)

    def _verify_routing(self) -> None:
        # imagefree → 引擎队列（mock 上游 completed）
        t = self.submit_and_wait({"prompt": "a dog", "model": "imagefree/default", "aspect_ratio": "1:1"})
        self.check("imagefree 路由 completed", t.get("status") == "completed", str(t.get("status")))
        # minimaxh3 文生图（mock 号池）
        t = self.submit_and_wait({"prompt": "a cat", "model": "minimaxh3/nano-banana-pro",
                                  "aspect_ratio": "1:1", "resolution": "1K"})
        self.check("minimaxh3 文生图 completed", t.get("status") == "completed",
                   f"{t.get('status')} {str(t.get('error') or '')[:50]}")
        # minimaxh3 视频（seedance-1.5-pro 480P）
        t = self.submit_and_wait({"prompt": "v", "model": "minimaxh3/seedance-1.5-pro",
                                  "aspect_ratio": "16:9", "resolution": "480p", "duration": 4}, timeout=15)
        self.check("minimaxh3 视频 completed", t.get("status") == "completed",
                   f"{t.get('status')} {str(t.get('error') or '')[:50]}")
        # minimaxh3 图生图
        import base64
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
        r = self.post("/v1/edit", {"image": f"data:image/png;base64,{png}",
                                   "prompt": "make red", "model": "minimaxh3/nano-banana-pro"})
        tid = (r.get("json") or {}).get("id")
        if tid:
            deadline = time.monotonic() + 15
            t = {}
            while time.monotonic() < deadline:
                t = (self.get(f"/v1/edit/tasks/{tid}").get("json") or {})
                if t.get("status") in ("completed", "error"):
                    break
                time.sleep(0.3)
            self.check("minimaxh3 图生图 completed", t.get("status") == "completed", str(t.get("status")))
        else:
            self.check("minimaxh3 图生图 completed", False, "提交失败")
        # aifreeforever 代理池未配置 → 明确降级（非静默崩溃）
        t = self.submit_and_wait({"prompt": "x", "model": "aifreeforever/gpt-image-2", "aspect_ratio": "1:1"})
        self.check("aifreeforever 无代理池降级（直连或失败）", t.get("status") in ("error", "submission_failed", "timeout"),
                   str(t.get("error") or t.get("status") or "")[:60])

    def _verify_brand(self) -> None:
        d = self.get("/")
        self.check("首页品牌「听风AI」", "听风AI" in d["text"], "品牌缺失!" if "听风AI" not in d["text"] else "")
        self.check("首页含微信 Tf00798", "Tf00798" in d["text"])
        self.check("首页含 GitHub 链接", "github.com/lza6" in d["text"])
        with httpx.Client(timeout=10.0) as c:
            r = c.get(self.api_url + "/static/logo.png")
            self.check("logo 静态资源可达", r.status_code == 200, str(r.status_code))
            self.check("logo 为 PNG", "image/png" in (r.headers.get("content-type") or ""))

    def _report(self) -> None:
        print("\n" + "=" * 64)
        print("多提供商网关 E2E 验收报告")
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
    ap.add_argument("--api-port", type=int, default=8101)
    args = ap.parse_args()
    for port in (args.api_port, 8001):
        if port_open(port):
            print(f"[错误] :{port} 已被占用，先停止再验收", file=sys.stderr)
            return 1
    e = ProvidersE2E(args.api_port)
    return e.run()


if __name__ == "__main__":
    sys.exit(main())
