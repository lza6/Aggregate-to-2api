# deploy/test_retry.py

- RetryTest · class · L27-L124 — class RetryTest(unittest.IsolatedAsyncioTestCase)
- asyncSetUp · method · L28-L31 — async def asyncSetUp(self)
- _run · method · L33-L37 — async def _run(self, prompt: str = "test prompt") -> dict
- _seed_tokens · method · L39-L43 — async def _seed_tokens(self, n: int) -> None: # H1 后 token 池存 (token, 时间戳) 元组；注入新鲜的
- test_rejected_then_retry_success · method · L46-L64 — async def test_rejected_then_retry_success(self)
- fake_submit · function · L50-L54 — async def fake_submit(base, prompt, ratio, token, timeout)
- fake_poll · function · L56-L57 — async def fake_poll(base, tid, timeout, interval)
- test_rejected_twice_fails · method · L67-L80 — async def test_rejected_twice_fails(self)
- fake_submit · function · L71-L73 — async def fake_submit(base, prompt, ratio, token, timeout)
- test_other_error_no_retry · method · L83-L96 — async def test_other_error_no_retry(self)
- fake_submit · function · L87-L90 — async def fake_submit(base, prompt, ratio, token, timeout)
- test_token_wait_timeout · method · L99-L105 — async def test_token_wait_timeout(self)
- test_first_attempt_success · method · L108-L124 — async def test_first_attempt_success(self)
- fake_submit · function · L112-L114 — async def fake_submit(base, prompt, ratio, token, timeout)
- fake_poll · function · L116-L117 — async def fake_poll(base, tid, timeout, interval)
