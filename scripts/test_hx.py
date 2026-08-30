"""H1/H2/H4/H5/H7/H8 修复的单元验证（标准库 unittest + asyncio）。

覆盖：
- H1: token TTL——取用跳过过期 token、全过期超时返回 None、预取 prune 清过期
- H2: 共享 httpx client 单例（连接复用）
- H4: 孤儿任务回收——启动时 pending/processing 标记 error，completed 不动
- H5: finished_at 索引存在
- H7: 同步接口超时返回 202 + Location
- H8: detect_mime 魔数判定

运行：python -m unittest scripts.test_hx -v   （项目根目录）
"""

import asyncio
import base64
import json
import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from api.db import DB
from api.worker import Engine
import api.imagefree_client as ifc
import api.turnstile_client as tsc
import api.config as cfg
import api.worker as worker_mod


# ── H1: token TTL ──────────────────────────────────
class H1TokenTTLTest(unittest.IsolatedAsyncioTestCase):
    def _engine(self) -> Engine:
        return Engine(None)  # 只测 token 池，不碰 db

    async def test_acquire_skips_expired_and_takes_fresh(self):
        e = self._engine()
        e.token_pool.put_nowait(("old", time.time() - 200))  # 过期
        e.token_pool.put_nowait(("fresh", time.time()))  # 新鲜
        tok = await e._acquire_token(1.0)
        self.assertEqual(tok, "fresh")
        self.assertTrue(e.token_pool.empty(), "两个 token 都该被消费")

    async def test_all_expired_then_timeout(self):
        e = self._engine()
        e.token_pool.put_nowait(("old", time.time() - 200))
        tok = await e._acquire_token(0.5)
        self.assertIsNone(tok, "全过期且无新鲜 token → 超时返回 None")

    async def test_prune_removes_expired_only(self):
        e = self._engine()
        e.token_pool.put_nowait(("old", time.time() - 200))
        e.token_pool.put_nowait(("fresh", time.time()))
        e._prune_expired_tokens()
        items = []
        while not e.token_pool.empty():
            items.append(e.token_pool.get_nowait())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], "fresh")


# ── H2: 共享连接池单例 ────────────────────────────
class H2ClientSingletonTest(unittest.TestCase):
    def test_imagefree_client_is_singleton(self):
        a, b = ifc._get_client(), ifc._get_client()
        self.assertIs(a, b)

    def test_turnstile_client_is_singleton(self):
        a, b = tsc._get_client(), tsc._get_client()
        self.assertIs(a, b)


# ── H4: 孤儿任务回收 ──────────────────────────────
class H4RecoverTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.db = DB(os.path.join(d, "t.db"))

    def _age(self, *ids: str, seconds: float = 600.0) -> None:
        """把任务 created_at 改到过去，模拟上次进程遗留的陈旧任务。"""
        self.db._conn.execute(
            f"UPDATE requests SET created_at=? WHERE id IN ({','.join('?'*len(ids))})",
            (time.time() - seconds, *ids),
        )
        self.db._conn.commit()

    def test_recover_marks_stale_as_error(self):
        t1, t2, t3 = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        self.db.create_request(t1, "p1", "1:1", False)
        self.db.create_request(t2, "p2", "1:1", False)
        self.db.create_request(t3, "p3", "1:1", False)
        self.db.mark_started(t1)  # processing
        # t2 保持 pending
        self.db.mark_finished(t3, "completed", "https://r2.dev/x.png", None, 3.0)
        self._age(t1, t2)  # 都是 10 分钟前的陈旧任务
        n = self.db.recover_stale_tasks()
        self.assertEqual(n, 2, "pending + processing 两条陈旧任务应被回收")
        self.assertEqual(self.db.get(t1)["status"], "error")
        self.assertEqual(self.db.get(t2)["status"], "error")
        self.assertEqual(self.db.get(t3)["status"], "completed", "completed 不受影响")
        self.assertIn("服务重启", self.db.get(t1)["error"])

    def test_fresh_tasks_not_recovered(self):
        """MEDIUM-2: 刚创建（<5min）的 pending/processing 不应被回收（防多进程误伤）。"""
        t = uuid.uuid4().hex
        self.db.create_request(t, "p", "1:1", False)
        self.db.mark_started(t)
        self.assertEqual(self.db.recover_stale_tasks(), 0, "新鲜任务不应被回收")
        self.assertEqual(self.db.get(t)["status"], "processing")

    def test_no_stale_noop(self):
        t = uuid.uuid4().hex
        self.db.create_request(t, "p", "1:1", False)
        self.db.mark_finished(t, "completed", "u", None, 1.0)
        self.assertEqual(self.db.recover_stale_tasks(), 0)


# ── H5: finished_at 索引 ───────────────────────────
class H5IndexTest(unittest.TestCase):
    def test_finished_index_created(self):
        d = tempfile.mkdtemp()
        db = DB(os.path.join(d, "t.db"))
        row = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_requests_finished'"
        ).fetchone()
        self.assertIsNotNone(row, "finished_at 索引应存在")


# ── HIGH-1/HIGH-2: download 交付 + 下载失败不丢图 ──
class HDownloadTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        d = tempfile.mkdtemp()
        self.db = DB(os.path.join(d, "t.db"))
        self.engine = Engine(self.db)
        # 注入一个新鲜 token
        await self.engine.token_pool.put(("tok", time.time()))

    async def _run(self, download: bool) -> dict:
        tid = uuid.uuid4().hex
        self.db.create_request(tid, "a cat", "1:1", download)
        await self.engine._process(tid)
        return self.db.get(tid)

    async def test_download_true_delivers_base64(self):
        """HIGH-1: download=true 时 image_base64/image_mime 应真实落库交付。"""
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        with (
            patch.object(worker_mod.imagefree_client, "submit_generate", new=AsyncMock(return_value="task_dl")),
            patch.object(
                worker_mod.imagefree_client,
                "poll_generate_status",
                new=AsyncMock(return_value={"status": "completed", "image": "https://r2.dev/x.png"}),
            ),
            patch.object(worker_mod.imagefree_client, "download_image", new=AsyncMock(return_value=png)),
        ):
            t = await self._run(download=True)
        self.assertEqual(t["status"], "completed")
        self.assertTrue(t["image_base64"], "download=true 应交付 base64")
        self.assertTrue(t["image_base64"].startswith("data:image/png;base64,"))
        self.assertEqual(t["image_mime"], "image/png")

    async def test_download_failure_keeps_image_url(self):
        """HIGH-2: 下载失败不应把已出图的任务标 error，image_url 必须保留。"""
        with (
            patch.object(worker_mod.imagefree_client, "submit_generate", new=AsyncMock(return_value="task_dl2")),
            patch.object(
                worker_mod.imagefree_client,
                "poll_generate_status",
                new=AsyncMock(return_value={"status": "completed", "image": "https://r2.dev/y.png"}),
            ),
            patch.object(
                worker_mod.imagefree_client,
                "download_image",
                new=AsyncMock(side_effect=worker_mod.imagefree_client.ImagefreeError("下载超时")),
            ),
        ):
            t = await self._run(download=True)
        self.assertEqual(t["status"], "completed", "下载失败仍应 completed")
        self.assertEqual(t["image_url"], "https://r2.dev/y.png", "image_url 不能丢")
        self.assertIsNone(t["image_base64"])


# ── 迁移回归：旧库 ALTER 加列后读取不依赖列序 ──────
class MigrationCompatibilityTest(unittest.TestCase):
    def test_old_schema_reads_after_migration(self):
        """生产旧库没有 image_base64/image_mime 列，迁移后 get/task_to_public 必须正常。"""
        d = tempfile.mkdtemp()
        p = os.path.join(d, "old.db")
        conn = sqlite3.connect(p)
        conn.execute("""CREATE TABLE requests (
            id TEXT PRIMARY KEY, prompt TEXT, aspect_ratio TEXT, download INTEGER DEFAULT 0,
            status TEXT, image_url TEXT, error TEXT, created_at REAL, started_at REAL,
            finished_at REAL, duration_sec REAL)""")
        conn.commit()
        conn.close()
        from api.db import task_to_public

        db = DB(p)  # 触发 ALTER 迁移
        tid = uuid.uuid4().hex
        db.create_request(tid, "a cat", "1:1", True)
        db.mark_finished(tid, "completed", "https://r2/x.png", None, 3.0, "data:image/png;base64,AAA", "image/png")
        t = db.get(tid)
        self.assertEqual(t["duration_sec"], 3.0)
        self.assertTrue(t["image_base64"].startswith("data:image/png"))
        self.assertEqual(task_to_public(t)["image_mime"], "image/png")


# ── H7: 同步接口 202 语义 ─────────────────────────
class H7SyncSemanticsTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _fake_request() -> Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/generate",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
        return Request(scope)

    async def test_timeout_returns_202_with_location(self):
        import api.main as m

        req = m.GenerateRequest(prompt="a cat", aspect_ratio="1:1", download=False)
        fake = AsyncMock()
        fake.submit = AsyncMock(return_value="abc-123")
        fake.wait_result = AsyncMock(
            return_value={
                "id": "abc-123",
                "status": "processing",
                "image_url": None,
                "image_base64": None,
                "image_mime": None,
                "error": None,
                "created_at": 1.0,
                "duration_sec": None,
            }
        )
        with patch.object(m, "engine", fake):
            resp = await m.generate_sync(self._fake_request(), req)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.headers["Location"], "http://testserver/v1/tasks/abc-123")
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "queued")

    async def test_completed_returns_200(self):
        import api.main as m

        req = m.GenerateRequest(prompt="a cat", aspect_ratio="1:1", download=False)
        fake = AsyncMock()
        fake.submit = AsyncMock(return_value="abc-124")
        fake.wait_result = AsyncMock(
            return_value={
                "id": "abc-124",
                "status": "completed",
                "image_url": "https://r2.dev/x.png",
                "image_base64": None,
                "image_mime": None,
                "error": None,
                "created_at": 1.0,
                "duration_sec": 3.0,
            }
        )
        with patch.object(m, "engine", fake):
            resp = await m.generate_sync(self._fake_request(), req)
        # 终态走正常 return（TaskInfo，HTTP 200）；只有排队超时才返回 202 JSONResponse
        self.assertFalse(isinstance(resp, JSONResponse), "终态不应返回 202 JSONResponse")
        self.assertEqual(resp.status, "completed")


# ── H8: detect_mime 魔数判定 ──────────────────────
class H8MimeTest(unittest.TestCase):
    def test_jpeg(self):
        self.assertEqual(ifc.detect_mime(b"\xff\xd8\xff\xe0\x00\x10JFIF"), "image/jpeg")

    def test_png(self):
        self.assertEqual(ifc.detect_mime(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"), "image/png")

    def test_webp(self):
        self.assertEqual(ifc.detect_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")

    def test_avif(self):
        self.assertEqual(ifc.detect_mime(b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00"), "image/avif")

    def test_gif(self):
        self.assertEqual(ifc.detect_mime(b"GIF89a\x01\x00\x01\x00"), "image/gif")

    def test_unknown(self):
        self.assertEqual(ifc.detect_mime(b"not an image at all"), "application/octet-stream")


# ── 图生图上游并发槽瞬态占用重试 ─────────────────
class EditRetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import api.main as m

        self.m = m
        m._EDIT_MUTEX_DIR = os.path.join(tempfile.mkdtemp(), ".edit_locks")
        m.config.EDIT_MUTEX_ENABLED = False  # 本测试只测链内重试，不走文件锁
        m.config.EDIT_RETRY_INTERVAL = 0  # 加速：重试不 sleep
        d = tempfile.mkdtemp()
        self.db = DB(os.path.join(d, "t.db"))
        self.engine = Engine(self.db)

    def tearDown(self):
        self.m.config.EDIT_MUTEX_ENABLED = True
        self.m.config.EDIT_RETRY_INTERVAL = 20

    def test_wedge_detection(self):
        self.assertTrue(
            self.m._is_edit_slot_wedged("获取上传地址失败: HTTP 429 You already have an image editing task in progress")
        )
        self.assertTrue(self.m._is_edit_slot_wedged("task in progress"))
        self.assertFalse(self.m._is_edit_slot_wedged("生成失败: 内容被拦截"))
        self.assertFalse(self.m._is_edit_slot_wedged("turnstile 求解失败"))

    async def test_wedge_retry_then_success(self):
        """首次撞上游 429 槽占用 → 自动重试 → 成功出图，且记录上游 taskId。"""
        import api.main as m
        from api import imagefree_client as ifc

        job_id = uuid.uuid4().hex
        self.db.create_request(job_id, "x", "1:1", False, "img", "default")
        await self.engine.token_pool.put(("tok", time.time()))
        await self.engine.token_pool.put(("tok2", time.time()))
        calls = {"n": 0}

        async def fake_upload(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ifc.ImagefreeError(
                    "获取上传地址失败: HTTP 429 You already have an image editing task in progress"
                )
            return "https://r2/u.png"

        with (
            patch.object(m, "engine", self.engine),
            patch.object(m, "db", self.db),
            patch.object(ifc, "upload_edit_image", new=AsyncMock(side_effect=fake_upload)),
            patch.object(ifc, "submit_edit", new=AsyncMock(return_value="up_tid")),
            patch.object(
                ifc,
                "poll_edit_status",
                new=AsyncMock(return_value={"status": "completed", "image": "https://r2/out.png"}),
            ),
        ):
            await m._run_edit_chain(job_id, b"a", "image/png", "x", False, "default")
        row = self.db.get(job_id)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(calls["n"], 2, "首次 429 应重试一次")
        self.assertEqual(row["upstream_task_id"], "up_tid", "上游 taskId 应落库")
        self.assertEqual(row["image_url"], "https://r2/out.png")

    async def test_persistent_wedge_fails_after_max_retries(self):
        """一直 429 → 重试满后标记 error，不无限卡。"""
        import api.main as m
        from api import imagefree_client as ifc

        self.m.config.EDIT_RETRY_MAX = 2
        job_id = uuid.uuid4().hex
        self.db.create_request(job_id, "x", "1:1", False, "img", "default")
        # token 池 maxsize=TOKEN_POOL_SIZE(2)，只注入池容量内的 token
        for i in range(self.engine.token_pool.maxsize):
            await self.engine.token_pool.put((f"tok{i}", time.time()))
        calls = {"n": 0}

        async def fake_upload(*a, **k):
            calls["n"] += 1
            raise ifc.ImagefreeError("获取上传地址失败: HTTP 429 You already have an image editing task in progress")

        with (
            patch.object(m, "engine", self.engine),
            patch.object(m, "db", self.db),
            patch.object(ifc, "upload_edit_image", new=AsyncMock(side_effect=fake_upload)),
        ):
            await m._run_edit_chain(job_id, b"a", "image/png", "x", False, "default")
        row = self.db.get(job_id)
        self.assertEqual(row["status"], "error")
        self.assertIn("仍被上游占用", row["error"])
        self.assertEqual(calls["n"], 2)
        self.m.config.EDIT_RETRY_MAX = 10


# ── 图生图跨进程互斥（文件锁）────────────────────
class EditMutexTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import api.main as m

        self.m = m
        # 指向临时目录，避免污染项目 data/
        self._tmp = tempfile.mkdtemp()
        m._EDIT_MUTEX_DIR = os.path.join(self._tmp, ".edit_locks")
        m.config.EDIT_MUTEX_ENABLED = True

    def tearDown(self):
        self.m.config.EDIT_MUTEX_ENABLED = False

    async def test_acquire_release_same_key_serial(self):
        tok = await self.m._acquire_edit_mutex("key1")
        self.assertTrue(tok, "首次应拿到锁")
        tok2 = await self.m._acquire_edit_mutex("key1", timeout=0.5)
        self.assertIsNone(tok2, "同 key 未释放前应拿不到（串行）")
        self.m._release_edit_mutex("key1", tok)
        tok3 = await self.m._acquire_edit_mutex("key1", timeout=1.0)
        self.assertTrue(tok3, "释放后应能再次拿到")
        self.m._release_edit_mutex("key1", tok3)

    async def test_different_keys_parallel(self):
        t1 = await self.m._acquire_edit_mutex("kA")
        t2 = await self.m._acquire_edit_mutex("kB", timeout=1.0)
        self.assertTrue(t2, "不同 key 互不阻塞（代理池并行语义）")
        self.m._release_edit_mutex("kA", t1)
        self.m._release_edit_mutex("kB", t2)

    async def test_stale_lock_recovered(self):
        path = self.m._edit_mutex_path("keyX")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()} {time.time() - 99999} deadbeef")
        tok = await self.m._acquire_edit_mutex("keyX", timeout=3.0)
        self.assertTrue(tok, "过期锁应被 stale 检测清理后拿到")
        self.m._release_edit_mutex("keyX", tok)

    async def test_release_wrong_token_does_not_delete(self):
        """release 时 token 不匹配（他人新锁）不应误删。"""
        path = self.m._edit_mutex_path("keyY")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()} {time.time()} other_token")
        self.m._release_edit_mutex("keyY", "my_token")
        self.assertTrue(os.path.exists(path), "token 不匹配不应删除他人锁")


# ── 图生图并发互斥（上游硬并发=1）────────────────
class EditConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import api.main as m

        self.m = m
        # 重置全局锁/集合，避免测试间污染；跨进程锁重定向到临时目录
        m._EDIT_LOCK = asyncio.Lock()
        m._EDIT_PENDING.clear()
        m._EDIT_MUTEX_DIR = os.path.join(tempfile.mkdtemp(), ".edit_locks")
        m.config.EDIT_MUTEX_ENABLED = True
        d = tempfile.mkdtemp()
        self.db = DB(os.path.join(d, "t.db"))
        self.engine = Engine(self.db)

    async def test_edit_tasks_serialize(self):
        """两个图生图任务应串行执行（不并发），不会撞上游硬并发=1。"""
        import api.main as m
        from api import imagefree_client as ifc

        job_a, job_b = uuid.uuid4().hex, uuid.uuid4().hex
        self.db.create_request(job_a, "a", "1:1", False, "img", "default")
        self.db.create_request(job_b, "b", "1:1", False, "img", "default")
        await self.engine.token_pool.put(("tok", time.time()))
        await self.engine.token_pool.put(("tok2", time.time()))
        # 记录提交顺序：并发跑会乱序，串行会严格 a→b
        order = []

        async def fake_upload(*a, **k):
            order.append("up")
            await asyncio.sleep(0.1)  # 让并发更容易暴露
            return "https://r2/u.png"

        with (
            patch.object(m, "engine", self.engine),
            patch.object(m, "db", self.db),
            patch.object(ifc, "upload_edit_image", new=AsyncMock(side_effect=fake_upload)),
            patch.object(ifc, "submit_edit", new=AsyncMock(side_effect=lambda *a, **k: order.append("sub") or "tid")),
            patch.object(
                ifc,
                "poll_edit_status",
                new=AsyncMock(return_value={"status": "completed", "image": "https://r2/o.png"}),
            ),
        ):
            await asyncio.gather(
                m._run_edit_job(job_a, b"a", "image/png", "a", False, "default"),
                m._run_edit_job(job_b, b"b", "image/png", "b", False, "default"),
            )
        # 断言：不出现 up,up 相邻（即第二个任务的 upload 不可能在第一个的 upload 前开始）
        self.assertNotEqual(order, ["up", "up", "sub", "sub"], "两个任务必须串行")
        # 更直接的：submit_edit 之间必有一个 upload 完成（串行结构）
        self.assertLessEqual(order.count("up"), order.count("sub") + 1)
        # 终态都应完成
        self.assertEqual(self.db.get(job_a)["status"], "completed")
        self.assertEqual(self.db.get(job_b)["status"], "completed")


# ── 模型列表 / model 前缀注入 ────────────────────
class ModelPresetTest(unittest.TestCase):
    def test_apply_model_default_no_prefix(self):
        self.assertEqual(cfg.apply_model("a cat", "default"), "a cat")

    def test_apply_model_anime_prefix(self):
        out = cfg.apply_model("a cat", "anime")
        self.assertTrue(out.startswith("anime style"))
        self.assertTrue(out.endswith("a cat"))

    def test_apply_model_unknown_falls_back_to_plain(self):
        self.assertEqual(cfg.apply_model("a cat", "nope"), "a cat")

    def test_models_endpoint_shape(self):
        from api.main import models
        import asyncio

        resp = asyncio.run(models())
        self.assertEqual(resp["count"], len(cfg.MODEL_PRESETS))
        ids = {m["id"] for m in resp["items"]}
        self.assertIn("default", ids)
        self.assertIn("anime", ids)
        self.assertTrue(all({"id", "name", "description", "applies_to"} <= set(m) for m in resp["items"]))


# ── 图生图持久化：type='img' 落 SQLite ────────────
class EditPersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import api.main as m

        self.m = m
        # 跨进程锁重定向临时目录，避免污染项目 data/
        m._EDIT_MUTEX_DIR = os.path.join(tempfile.mkdtemp(), ".edit_locks")
        m.config.EDIT_MUTEX_ENABLED = True
        d = tempfile.mkdtemp()
        self.db = DB(os.path.join(d, "t.db"))
        self.engine = Engine(self.db)

    async def test_edit_job_persists_and_queryable(self):
        """图生图任务经 _run_edit_job 落库 type='img'，DB 可查回、终态正确。"""
        import api.main as m
        import uuid as _uuid

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        from api import imagefree_client as ifc

        job_id = _uuid.uuid4().hex
        self.db.create_request(job_id, "make it cute", "1:1", False, "img", "default")
        await self.engine.token_pool.put(("tok", time.time()))
        # _run_edit_job 引用 main 模块全局 engine/db，必须 patch 掉，否则写到真实 DB/真实 token 池
        with (
            patch.object(m, "engine", self.engine),
            patch.object(m, "db", self.db),
            patch.object(ifc, "upload_edit_image", new=AsyncMock(return_value="https://r2/u.png")),
            patch.object(ifc, "submit_edit", new=AsyncMock(return_value="edit_tid")),
            patch.object(
                ifc,
                "poll_edit_status",
                new=AsyncMock(return_value={"status": "completed", "image": "https://r2/out.png"}),
            ),
        ):
            await m._run_edit_job(job_id, png, "image/png", "make it cute", False, "default")
        row = self.db.get(job_id)
        self.assertIsNotNone(row, "图生图任务应落库")
        self.assertEqual(row["type"], "img")
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["image_url"], "https://r2/out.png")
        self.assertEqual(row["model"], "default")

    async def test_edit_failure_persists_error(self):
        """图生图失败也应落库 error，错误原因可查。"""
        import api.main as m
        import uuid as _uuid
        from api import imagefree_client as ifc

        job_id = _uuid.uuid4().hex
        self.db.create_request(job_id, "x", "1:1", False, "img", "default")
        await self.engine.token_pool.put(("tok", time.time()))
        with (
            patch.object(m, "engine", self.engine),
            patch.object(m, "db", self.db),
            patch.object(ifc, "upload_edit_image", new=AsyncMock(side_effect=ifc.ImagefreeError("上游拒绝"))),
        ):
            await m._run_edit_job(job_id, b"png", "image/png", "x", False, "default")
        row = self.db.get(job_id)
        self.assertEqual(row["status"], "error")
        self.assertIn("上游拒绝", row["error"])


# ── 图生图 /v1/edit 输入解析 ────────────────────
class EditInputTest(unittest.TestCase):
    """_parse_input_image：data URI 解码 / URL 放行 / SSRF 私网拒绝 / 非法格式。"""

    @staticmethod
    def _call(image: str):
        from api.main import _parse_input_image
        from fastapi import HTTPException

        try:
            return _parse_input_image(image)
        except HTTPException as e:
            return ("HTTP", e.status_code)

    def test_data_uri_decodes(self):
        b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nxxxx").decode()
        data, ctype = self._call(f"data:image/png;base64,{b64}")
        self.assertIsInstance(data, bytes)
        self.assertEqual(ctype, "image/png")

    def test_data_uri_bad_base64(self):
        self.assertEqual(self._call("data:image/png;base64,!!!notbase64!!!")[0], "HTTP")

    def test_data_uri_wrong_syntax(self):
        self.assertEqual(self._call("data:text/plain,hello")[0], "HTTP")

    def test_public_url_allowed(self):
        data, ctype = self._call("https://pub-abc.r2.dev/images/x.png")
        self.assertIsNone(data)
        self.assertTrue(ctype.startswith("https://"))

    def test_private_ip_rejected(self):
        for u in (
            "http://127.0.0.1:8100/v1/stats",
            "http://192.168.1.1/x.png",
            "http://10.0.0.1/x.png",
            "http://localhost/x.png",
        ):
            self.assertEqual(self._call(u)[0], "HTTP", f"{u} 应被拒绝")

    def test_bad_scheme_rejected(self):
        self.assertEqual(self._call("ftp://x/y.png")[0], "HTTP")


if __name__ == "__main__":
    unittest.main()
