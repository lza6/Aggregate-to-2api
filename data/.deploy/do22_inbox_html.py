import httpx, uuid, re, sys
sys.path.insert(0, '/app')
BASE = "https://22.do"
h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json"}
client = httpx.Client(headers=h, timeout=15, follow_redirects=True)
# 建新箱 – 已有 verify 邮件的旧箱页面可能清空了
r = client.post(BASE+"/action/mailbox/create", json={"type":"random"})
email = ((r.json() or {}).get("data") or {}).get("email") or ""
client.post(BASE+"/action/mailbox/login", json={"email":email,"language":"en-US"})
# 取 inbox 原始 HTML，看邮件列表结构
pg = client.get(BASE+"/inbox")
# 搜所有可能的邮件容器
for pattern in [r'class="[^"]*message[^"]*"', r'class="[^"]*mail[^"]*"', r'class="[^"]*item[^"]*"', r'<tr[^>]*>', r'data-id=']:
    matches = re.findall(pattern, pg.text)
    if matches:
        print(f"  {pattern[:30]}: {len(matches)} 个", flush=True)
# 看页面是否有邮件列表容器
for keyword in ['message', 'mail-item', 'inbox-item', 'email-item', 'messageId', 'data-message']:
    if keyword in pg.text:
        idx = pg.text.find(keyword)
        print(f"  '{keyword}': 位置 {idx}, 上下文: {pg.text[max(0,idx-20):idx+80]}", flush=True)
# 输出页面关键部分（去掉样式/脚本）
body = re.search(r'<body[^>]*>(.*?)</body>', pg.text, re.S)
if body:
    text = re.sub(r'<script[^>]*>.*?</script>', '', body.group(1), flags=re.S)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    print(f"inbox 纯文本: {text[:600]}", flush=True)
