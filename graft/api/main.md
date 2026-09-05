# api/main.py

- SecurityHeadersMiddleware · class · L46-L103 — class SecurityHeadersMiddleware
- __init__ · method · L74-L77 — def __init__(self, app)
- __call__ · method · L79-L103 — async def __call__(self, scope, receive, send)
- send_with_headers · function · L86-L101 — async def send_with_headers(message)
- SPAStaticFiles · class · L151-L181 — class SPAStaticFiles(StaticFiles)
- get_response · method · L161-L181 — async def get_response(self, path: str, scope)
- _apply_nocache · function · L167-L172 — def _apply_nocache(resp)
- _admin_redirect · function · L190-L191 — async def _admin_redirect() -> RedirectResponse
