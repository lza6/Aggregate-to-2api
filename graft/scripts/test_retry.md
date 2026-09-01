# scripts/test_retry.py

- RetryTest · class · L27-L129 — class RetryTest(unittest.IsolatedAsyncioTestCase)
- asyncSetUp · method · L28-L31 — async def asyncSetUp(self)
- _run · method · L33-L37 — async def _run(self, prompt: str = "test prompt") -> dict
- _seed_tokens · method · L39-L44 — async def _seed_tokens(self, n: int) -> None: # H1 后 token 池存 (token, 时间戳) 元组；注入新鲜的
- test_rejected_then_retry_success · method · L47-L67 — async def test_rejected_then_retry_success(self)
- fake_submit · function · L51-L55 — async def fake_submit(base, prompt, ratio, token, timeout)
- fake_poll · function · L57-L58 — async def fake_poll(base, tid, timeout, interval)
- test_rejected_twice_fails · method · L70-L83 — async def test_rejected_twice_fails(self)
- fake_submit · function · L74-L76 — async def fake_submit(base, prompt, ratio, token, timeout)
- test_other_error_no_retry · method · L86-L98 — async def test_other_error_no_retry(self)
- fake_submit · function · L90-L92 — async def fake_submit(base, prompt, ratio, token, timeout)
- test_token_wait_timeout · method · L101-L108 — async def test_token_wait_timeout(self)
- test_first_attempt_success · method · L111-L129 — async def test_first_attempt_success(self)
- fake_submit · function · L115-L117 — async def fake_submit(base, prompt, ratio, token, timeout)
- fake_poll · function · L119-L120 — async def fake_poll(base, tid, timeout, interval)
