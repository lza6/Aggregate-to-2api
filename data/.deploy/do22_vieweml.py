import httpx, uuid, re, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
# 取 inbox 页查找 viewEml 定义或引用的 JS
pg = client.get(BASE+"/inbox")
# 找 viewEml 函数定义/来源
for m in re.finditer(r'viewEml[\s\S]{0,200}', pg.text):
    print("viewEml 片段:", m.group(0)[:200], flush=True)
    break
# 找引用的 JS 文件
for m in re.finditer(r'src="([^"]+\.js[^"]*)"', pg.text):
    print("JS 文件:", m.group(1), flush=True)
# 找 /mail/ 链接模式
for m in re.finditer(r'[\'"]/(api|mail|action)/[^\'"]*', pg.text):
    print("API 路径:", m.group(0)[:80], flush=True)
