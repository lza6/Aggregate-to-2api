import httpx, re
js = httpx.get("https://22.do/assets/js/temporary.js", timeout=15).text
i = js.find("viewEml")
if i > 0:
    seg = js[i:i+800]
    seg = re.sub(r"\s+", " ", seg)
    print("viewEml:", seg[:600])
actions = set(re.findall(r"/action/mailbox/[a-zA-Z/]+", js))
for a in sorted(actions):
    print("API:", a)