import httpx, json, re, sys
sys.path.insert(0, '/app')

# 从 6475.js 提取完整 Server Action 调用（签到用）
# 已知：claimDailyCheckinAction 绑定变量（A7 等），7fa3d4d2... 是 action ID
# 看 6475.js 中 7fa3d4d2 绑定的变量和调用
import urllib.request

# 直接从服务器拉 6475.js（本地文件在逆向目录）
js = open('/tmp/6475.js', encoding='utf-8').read() if False else None
# 从远程拿
try:
    js = httpx.get("https://nanobanana-pro.com/_next/static/chunks/6475-e500756784a92a0f.js", timeout=20).text
except Exception as e:
    print("拉 JS 失败:", e); sys.exit()

# 找 claimDailyCheckinAction 相关
i = js.find("claimDailyCheckinAction")
if i < 0:
    # 可能在打包里被混淆，搜 actionId
    i = js.find("7fa3d4d28767dbc090ad4228dff062a1e20d421ce2")
print("JS len:", len(js), "idx:", i)
if i >= 0:
    seg = js[max(0,i-200):i+200]
    print("上下文:", re.sub(r"\s+", " ", seg)[:300])
    # 找该 action 的调用函数（createServerReference 之后的变量使用）
    # 在变量绑定附近找调 body 组装
    # 搜索所有 callServer 调用
    for m in re.finditer(r"callServer\(\s*(\"[a-f0-9]{40}\")", js):
        print("callServer action:", m.group(1)[:20])
    # 搜索 .call( 或 fetch 带该 actionId
    for m in re.finditer(r".{80}7fa3d4d28767dbc090ad4228dff062a1e20d421ce2.{100}", js):
        print("调用上下文:", re.sub(r"\s+", " ", m.group(0))[:300])
        break