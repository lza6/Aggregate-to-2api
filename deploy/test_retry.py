"""worker 换 token 重试逻辑的单元验证（零依赖，标准库 unittest + asyncio）。

验证点：
1. token 被上游拒绝（Human verification failed）→ 自动换新 token 重试一次 → 成功
2. 两次都被拒绝 → 最终 error，且用了 2 个 token
3. 非 token 错误（内容拦截等）→ 不重试，只消耗 1 个 token
4. token 池空且等待超时 → 报「等待 token 超时」，不无限阻塞

运行：python -m unittest scripts.test_retry -v   （在项目根目录）
"""
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

from api.db import DB
from api.worker import Engine
import api.worker as worker_mod

REJECTED_MSG = (
    "generate 提交失败: Human verification failed. "
    "Please complete the setup or refresh the page to try again."
)


class RetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        d = tempfile.mkdtemp()
        self.db = DB(os.path.join(d, "t.db"))
        self.engine = Engine(self.db)

    async def _run(self, prompt: str = "test prompt") -> dict:
        tid = uuid.uuid4().hex
        self.db.create_request(tid, prompt, "1:1", False)
        await self.engine._process(tid)
        return self.db.get(tid)

    async def _seed_tokens(self, n: int) -> None:
        # H1 后 token 池存 (token, 时间戳) 元组；注入新鲜的
        import time as _t
        for i in range(n):
            await self.engine.token_pool.put((f"tok{i}", _t.time()))

    # ── 1) 第一次 token 被拒 → 换 token 重试 → 成功 ──
    async def test_rejected_then_retry_success(self):
        await self._seed_tokens(2)
        calls = {"n": 0}

        async def fake_submit(base, prompt, ratio, token, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise worker_mod.imagefree_client.ImagefreeError(REJECTED_MSG)
            return "task_x"

        async def fake_poll(base, tid, timeout, interval):
            return {"status": "completed", "image": "https://r2.dev/a.png"}

        with patch.object(worker_mod.imagefree_client, "submit_generate", side_effect=fake_submit), \
             patch.object(worker_mod.imagefree_client, "poll_generate_status", side_effect=fake_poll):
            t = await self._run()
        self.assertEqual(t["status"], "completed")
        self.assertEqual(calls["n"], 2, "应换 token 重试一次")
        self.assertEqual(self.engine.token_pool.qsize(), 0, "2 个 token 都应被消耗")

    # ── 2) 两次都被拒 → error ──
    async def test_rejected_twice_fails(self):
        await self._seed_tokens(2)
        calls = {"n": 0}

        async def fake_submit(base, prompt, ratio, token, timeout):
            calls["n"] += 1
            raise worker_mod.imagefree_client.ImagefreeError(REJECTED_MSG)

        with patch.object(worker_mod.imagefree_client, "submit_generate", side_effect=fake_submit):
            t = await self._run()
        self.assertEqual(t["status"], "error")
        self.assertIn("Human verification failed", t["error"])
        self.assertEqual(calls["n"], 2, "最多尝试 2 次")
        self.assertEqual(self.engine.token_pool.qsize(), 0)

    # ── 3) 非 token 错误不重试 ──
    async def test_other_error_no_retry(self):
        await self._seed_tokens(2)
        calls = {"n": 0}

        async def fake_submit(base, prompt, ratio, token, timeout):
            calls["n"] += 1
            raise worker_mod.imagefree_client.ImagefreeError(
                "generate 提交失败: 内容被拦截，请修改提示词")

        with patch.object(worker_mod.imagefree_client, "submit_generate", side_effect=fake_submit):
            t = await self._run()
        self.assertEqual(t["status"], "error")
        self.assertEqual(calls["n"], 1, "非 token 错误不应重试")
        self.assertEqual(self.engine.token_pool.qsize(), 1, "只取走 1 个 token（未重试）")

    # ── 4) token 池空 + 等待超时 → 报错而非阻塞 ──
    async def test_token_wait_timeout(self):
        import api.config as cfg
        cfg.TOKEN_WAIT_TIMEOUT = 1  # 池空且无预取，1s 后应超时报错
        t = await self._run()
        self.assertEqual(t["status"], "error")
        self.assertIn("token", t["error"])
        cfg.TOKEN_WAIT_TIMEOUT = 30

    # ── 5) 首 token 直接成功：不重试，消耗 1 个 ──
    async def test_first_attempt_success(self):
        await self._seed_tokens(1)
        calls = {"n": 0}

        async def fake_submit(base, prompt, ratio, token, timeout):
            calls["n"] += 1
            return "task_ok"

        async def fake_poll(base, tid, timeout, interval):
            return {"status": "completed", "image": "https://r2.dev/b.png"}

        with patch.object(worker_mod.imagefree_client, "submit_generate", side_effect=fake_submit), \
             patch.object(worker_mod.imagefree_client, "poll_generate_status", side_effect=fake_poll):
            t = await self._run()
        self.assertEqual(t["status"], "completed")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(self.engine.token_pool.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
