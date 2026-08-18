import httpx, re, sys
sys.path.insert(0, '/app')
client = httpx.Client(timeout=15)
js = client.get("https://22.do/assets/js/temporary.js")
if js.status_code == 200:
    # 找 viewEml 和 .download / .view 相关
    for kw in ["viewEml", "download", "viewId", "messageId", "eml", "raw"]:
        for m in re.finditer(re.escape(kw) + r"[\s\S]{0,200}", js.text):
            print(f"== {kw} ==: {m.group(0)[:180]}", flush=True)
            break
    # 找 action/mailbox 相关 axios/fetch
    for m in re.finditer(r"action/mailbox/[a-zA-Z/]+", js.text):
        print("路径:", m.group(0), flush=True)
