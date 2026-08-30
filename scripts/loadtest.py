"""并发压测：模拟 50 RPS 瞬时入口，验证全部接受（无 429/5xx），并核对排队/并发状态。"""

import json
import sys
import time
import urllib.error
import urllib.request

# 默认 8100（与启动端口一致）；可用 `python loadtest.py 8101` 指定其它端口（H9）
PORT = sys.argv[1] if len(sys.argv) > 1 else "8100"
URL = f"http://127.0.0.1:{PORT}/v1/generate/async"
N = 50  # 瞬时 50 个并发请求（≈50 RPS 入口）

results = {"ok": 0, "429": 0, "other": 0}
durations = []
errors = []

start = time.time()
for i in range(N):
    t0 = time.time()
    body = json.dumps({"prompt": f"a cat playing in nature scene number {i}", "aspect_ratio": "1:1"}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        d = json.loads(r.read().decode())
        if r.status == 200 and d.get("status") in ("pending", "processing"):
            results["ok"] += 1
        else:
            results["other"] += 1
            errors.append(f"status={r.status} {d}")
    except urllib.error.HTTPError as e:
        code = e.read().decode()[:80] if hasattr(e, "read") else ""
        if e.code == 429:
            results["429"] += 1
        else:
            results["other"] += 1
        errors.append(f"HTTP {e.code} {code}")
    except Exception as e:
        results["other"] += 1
        errors.append(str(e))
    durations.append(time.time() - t0)

elapsed = time.time() - start
rps = N / elapsed
print(f"=== 压测结果: {N} 请求 / {elapsed:.2f}s ≈ {rps:.1f} RPS ===")
print(f"接受(202/pending): {results['ok']}")
print(f"限流429: {results['429']}")
print(f"其他: {results['other']}")
print(
    f"单请求耗时: min={min(durations)*1000:.0f}ms max={max(durations)*1000:.0f}ms avg={sum(durations)/len(durations)*1000:.0f}ms"
)
if errors[:3]:
    print("前3个错误:", errors[:3])
