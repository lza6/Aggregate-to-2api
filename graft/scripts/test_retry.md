# scripts/test_retry.py

- RetryTest · class · L28-L125 — class RetryTest(unittest.IsolatedAsyncioTestCase)
- asyncSetUp · method · L29-L32 — async def asyncSetUp(self)
- _run · method · L34-L38 — async def _run(self, prompt: str = "test prompt") -> dict
- _seed_tokens · method · L40-L44 — async def _seed_tokens(self, n: int) -> None: # H1 后 token 池存 (token, 时间戳) 元组；注入新鲜的
- test_rejected_then_retry_success · method · L47-L65 — async def test_rejected_then_retry_success(self)
- fake_submit · function · L51-L55 — async def fake_submit(base, prompt, ratio, token, timeout)
- fake_poll · function · L57-L58 — async def fake_poll(base, tid, timeout, interval)
- test_rejected_twice_fails · method · L68-L81 — async def test_rejected_twice_fails(self)
- fake_submit · function · L72-L74 — async def fake_submit(base, prompt, ratio, token, timeout)
- test_other_error_no_retry · method · L84-L97 — async def test_other_error_no_retry(self)
- fake_submit · function · L88-L91 — async def fake_submit(base, prompt, ratio, token, timeout)
- test_token_wait_timeout · method · L100-L106 — async def test_token_wait_timeout(self)
- test_first_attempt_success · method · L109-L125 — async def test_first_attempt_success(self)
- fake_submit · function · L113-L115 — async def fake_submit(base, prompt, ratio, token, timeout)
- fake_poll · function · L117-L118 — async def fake_poll(base, tid, timeout, interval)
