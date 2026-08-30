"""压力测试：模拟高并发场景。

单独运行（非 pytest）：
  python tests/performance/test_stress.py [--api-url http://127.0.0.1:8100] [--concurrency 50]

需要先启动 API 服务（mock 模式）：
  IF_MOCK_UPSTREAM=1 IF_MOCK_REGISTER=1 IF_ACCOUNT_AUTO=0 \\
  python -m uvicorn api.main:app --host 127.0.0.1 --port 8100
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def stress_test(api_url: str, concurrency: int = 50, timeout: int = 30):
    """执行压力测试：模拟 concurrency 个并发请求。"""
    url = f"{api_url}/v1/generate/async"
    results = {"ok": 0, "429": 0, "error": 0, "timeout": 0}
    durations = []

    print(f"压力测试: {concurrency} 并发, {api_url}")
    print("-" * 50)

    start = time.time()
    for i in range(concurrency):
        t0 = time.time()
        body = json.dumps(
            {
                "prompt": f"stress test {i}",
                "aspect_ratio": "1:1",
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            d = json.loads(r.read().decode())
            if r.status == 200:
                results["ok"] += 1
            else:
                results["error"] += 1
        except urllib.error.HTTPError as e:
            if e.code == 429:
                results["429"] += 1
            else:
                results["error"] += 1
        except Exception:
            results["timeout"] += 1
        durations.append(time.time() - t0)

    elapsed = time.time() - start
    rps = concurrency / elapsed

    print("\n结果:")
    print(f"  总请求: {concurrency}")
    print(f"  RPS: {rps:.1f}")
    print(f"  成功: {results['ok']}")
    print(f"  限流(429): {results['429']}")
    print(f"  错误: {results['error']}")
    print(f"  超时: {results['timeout']}")
    print(f"  平均耗时: {sum(durations)/len(durations)*1000:.0f}ms")
    print(f"  最大耗时: {max(durations)*1000:.0f}ms")
    print(f"  最小耗时: {min(durations)*1000:.0f}ms")

    return results


def main():
    ap = argparse.ArgumentParser(description="性能压力测试")
    ap.add_argument("--api-url", default="http://127.0.0.1:8100")
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    result = stress_test(args.api_url, args.concurrency, args.timeout)
    sys.exit(0 if result["ok"] >= args.concurrency * 0.95 else 1)


if __name__ == "__main__":
    main()
