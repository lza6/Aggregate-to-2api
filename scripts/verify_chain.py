"""临时验证脚本：cf_solver 求解 → imagefree 生成 → 轮询，全链路预演。"""

import json
import socket
import time
import urllib.error
import urllib.request

socket.setdefaulttimeout(30)
PROXY = "http://127.0.0.1:10808"
CF = "http://127.0.0.1:8001"
BASE = "https://imagefree.net"
SITEKEY = "0x4AAAAAACE-XLGoQUckKKm_"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def get(url, referer=None, host=None):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        h["Referer"] = referer
    if host:
        h["Host"] = host
    try:
        r = opener.open(urllib.request.Request(url, headers=h))
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def post(path, body):
    h = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": BASE + "/",
        "Accept": "*/*",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    try:
        r = opener.open(urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=h))
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


# 1) 求解 turnstile（新鲜 token）
st, data = get(f"{CF}/turnstile?url={BASE}/&sitekey={SITEKEY}", host="127.0.0.1")
print("turnstile submit:", st, json.dumps(data)[:120])
tid = data["task_id"]
token = None
for i in range(60):
    st, d = get(f"{CF}/result?id={tid}", host="127.0.0.1")
    if st == 200:
        token = d.get("value")
        print(f"turnstile solved [{i}]: {str(token)[:40]}...")
        break
    if st in (404, 408, 422):
        print("turnstile FAIL:", d)
        break
    time.sleep(2)
if not token:
    raise SystemExit("no turnstile token")

# 2) 提交生成
st, data = post("/api/generate", {"prompt": "a cute cat", "aspect_ratio": "1:1", "turnstile_token": token})
print("generate submit:", st, json.dumps(data)[:300])
if st != 200 or not data.get("taskId"):
    raise SystemExit("generate submit failed")

# 3) 轮询
for i in range(40):
    st, d = get(f'{BASE}/api/generate/status?taskId={data["taskId"]}', referer=BASE + "/")
    print(f"poll[{i}]:", json.dumps(d)[:300])
    if d.get("status") in ("completed", "error", "failed"):
        break
    time.sleep(2)
