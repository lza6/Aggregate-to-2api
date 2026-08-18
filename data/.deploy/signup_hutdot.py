import asyncio, httpx, time, sys
sys.path.insert(0, '/app')
import api.turnstile_client as tc
BTC = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150","Content-Type":"application/json","Origin":"https://nanobanana-pro.com","Referer":"https://nanobanana-pro.com/zh"}
async def t():
    captcha = await tc.solve_turnstile("http://cfsolver:8001","https://nanobanana-pro.com/zh","0x4AAAAAACBMF7NSqVf-BSmE",90,proxy=None)
    print("captcha:", len(captcha))
    r = httpx.post("https://nanobanana-pro.com/api/auth/sign-up/email", headers={**BTC,"x-turnstile-token":captcha},
        json={"email":"test_"+str(int(time.time()))+"@hutdot.com","password":"Tf@12345678","name":"TfTest","callbackURL":"/zh"}, timeout=30)
    print("sign-up:", r.status_code, r.text[:80])
asyncio.run(t())
