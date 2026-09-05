"""best-effort 真实出图重试：上游限流（429 too frequent）窗口外重试，成功即退出。"""

import sys
import time

import httpx

BASE = "http://127.0.0.1:8100"


def main() -> int:
    deadline = time.monotonic() + 900  # 最多 15 分钟
    attempt = 0
    with httpx.Client(timeout=15) as c:
        while time.monotonic() < deadline:
            attempt += 1
            try:
                r = c.post(
                    BASE + "/v1/generate/async",
                    json={"prompt": "a cute husky puppy", "aspect_ratio": "1:1", "download": False},
                )
                if r.status_code != 200:
                    print(f"[{attempt}] submit HTTP {r.status_code}", flush=True)
                    time.sleep(30)
                    continue
                tid = r.json()["id"]
                dl = time.monotonic() + 240
                while time.monotonic() < dl:
                    j = c.get(BASE + f"/v1/tasks/{tid}", timeout=15).json()
                    st = j.get("status")
                    if st == "completed":
                        print(f"[{attempt}] REAL GENERATION COMPLETED: {j.get('image_url','')}", flush=True)
                        return 0
                    if st == "error":
                        print(f"[{attempt}] task error: {(j.get('error') or '')[:120]}", flush=True)
                        break
                    time.sleep(3)
                else:
                    print(f"[{attempt}] task timeout", flush=True)
            except Exception as e:
                print(f"[{attempt}] exception: {type(e).__name__}: {str(e)[:100]}", flush=True)
            time.sleep(45)  # 等待限流窗口
    print("REAL GENERATION FAILED after 15min (upstream rate limit window)", flush=True)
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
