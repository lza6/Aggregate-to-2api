"""M2/M4/M5/M7/M8 的 pytest 用例：统一异常、/metrics、healthz 深指标、DB 清理、轻量投影。"""
import asyncio
import os
import time

import pytest

from api.db import DB, task_to_public


# ── M7: DB TTL 清理 ──────────────────────────────
class TestDbCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_only(self, tmp_db):
        import uuid

        old = uuid.uuid4().hex
        new = uuid.uuid4().hex
        await tmp_db.create_request(old, "old", "1:1", False)
        await tmp_db.create_request(new, "new", "1:1", False)
        await tmp_db.flush()  # IMP-25: 批量模式下先 flush 确保数据已落盘
        # 把 old 的 created_at 改到 2 年前
        conn0 = tmp_db._connections[0]
        await conn0.execute(
            "UPDATE requests SET created_at=? WHERE id=?",
            (time.time() - 2 * 366 * 86400, old),
        )
        await conn0.commit()
        r = await tmp_db.cleanup(retention_days=365)
        assert r["deleted"] == 1
        old_row = await tmp_db.get(old)
        assert old_row is None
        new_row = await tmp_db.get(new)
        assert new_row is not None

    @pytest.mark.asyncio
    async def test_cleanup_noop_when_nothing_old(self, tmp_db):
        import uuid

        await tmp_db.create_request(uuid.uuid4().hex, "x", "1:1", False)
        r = await tmp_db.cleanup(retention_days=365)
        assert r["deleted"] == 0


# ── M8: 轻量投影 get_public ──────────────────────
class TestPublicProjection:
    @pytest.mark.asyncio
    async def test_get_public_excludes_prompt(self, tmp_db):
        import uuid

        tid = uuid.uuid4().hex
        await tmp_db.create_request(tid, "secret prompt content", "1:1", False)
        await tmp_db.mark_started(tid)
        await tmp_db.mark_finished(tid, "completed", "https://r2/x.png", None, 3.0)
        pub = await tmp_db.get_public(tid)
        assert "prompt" not in pub, "get_public 不应返回 prompt"
        assert "download" not in pub, "get_public 不应返回 download"
        assert pub["status"] == "completed"
        assert pub["image_url"] == "https://r2/x.png"
        assert pub["id"] == tid

    @pytest.mark.asyncio
    async def test_get_public_missing(self, tmp_db):
        result = await tmp_db.get_public("nope")
        assert result is None


# ── M4: /metrics 文本格式 ─────────────────────────
class TestMetrics:
    @pytest.mark.asyncio
    async def test_metrics_returns_prometheus_text(self):
        from api.routes.admin import metrics

        resp = await metrics()
        assert resp.status_code == 200
        text = resp.body.decode()
        assert "imagefree_requests_total" in text
        assert "imagefree_processing" in text
        assert "imagefree_token_pool" in text
        assert "# TYPE imagefree_requests_total counter" in text


# ── M5: healthz 深指标 + TTL 缓存 ────────────────
class TestHealthz:
    @pytest.mark.asyncio
    async def test_healthz_has_deep_metrics(self):
        from api.routes.health import healthz

        h = await healthz()
        assert "token_pool" in h
        assert "db_rows" in h
        assert "edit_inflight" in h
        assert "workers" in h
        assert "uptime_seconds" in h

    @pytest.mark.asyncio
    async def test_cf_probe_cache_ttl(self):
        """TTL 内二次调用不重复探测（缓存命中），force=True 强制刷新。"""
        from api.routes.health import _probe_cf_solver, _cf_probe_cache
        from api import config

        config.HEALTHZ_CACHE_TTL = 5
        _cf_probe_cache.update(ok=True, at=time.time())
        # 缓存命中：无需真连 cf_solver（本地 8001 可能不存在），直接返回 True
        assert await _probe_cf_solver() is True
        # force 刷新会真的尝试连接（结果取决于环境），只验证不抛异常
        await _probe_cf_solver(force=True)


# ── P13/P15: 磁盘日志与 healthz 新段单测 ──────────────

class TestDiskLogger:
    def test_setup_creates_dir_and_writes(self, tmp_path):
        import logging
        from api.disk_logger import setup_disk_logging, teardown_disk_logging
        # 单元测试不 import api.main（无 basicConfig），裸进程 root level=WARNING
        # 会把 info 记录在 handler 之前过滤掉——生产服务 root 是 INFO，测试对齐该前提
        root = logging.getLogger()
        saved_level = root.level
        root.setLevel(logging.INFO)
        log_dir = str(tmp_path / "logs")
        h = setup_disk_logging(log_dir, retention_days=3)
        try:
            logging.getLogger("disk.test").info("hello-disk")
            h.flush()
            import os, glob
            files = glob.glob(os.path.join(log_dir, "imagefree-api.log*"))
            assert files, f"日志目录无文件: {os.listdir(log_dir) if os.path.isdir(log_dir) else log_dir}"
            content = ""
            for f in files:
                with open(f, encoding="utf-8") as fh:
                    content += fh.read()
            assert "hello-disk" in content
        finally:
            teardown_disk_logging(h)
            root.setLevel(saved_level)

    def test_teardown_removes_handler(self, tmp_path):
        import logging
        from api.disk_logger import setup_disk_logging, teardown_disk_logging
        h = setup_disk_logging(str(tmp_path / "logs2"))
        assert h in logging.getLogger().handlers
        teardown_disk_logging(h)
        assert h not in logging.getLogger().handlers

    def test_rotation_keeps_backup_count(self, tmp_path):
        """TimedRotatingFileHandler 配置了 backupCount=保留天数。"""
        from api.disk_logger import setup_disk_logging
        import logging
        h = setup_disk_logging(str(tmp_path / "logs3"), retention_days=5)
        assert h.backupCount == 5
        logging.getLogger().removeHandler(h)
        h.close()
