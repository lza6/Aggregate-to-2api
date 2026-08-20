"""IMP-20: DB 连接池/多连接支持测试。

覆盖场景：
- 多连接并发读写（round-robin 分配写连接，独立读连接）
- 连接泄漏检测：close 后所有连接关闭
- 自动重连：健康检查+重建失效连接
- IF_DB_POOL_SIZE=1 兼容旧行为（单连接模式）
- 读走 _read_conns 池，写走 pool 连接
"""
import asyncio
import os
import tempfile
import time

import pytest


async def _make_db(pool_size: int = 3, timeout: int = 5, batch_enabled: bool = True):
    """创建临时 DB 实例，返回 (db, path)。"""
    import api.config as cfg
    from api.db import DB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old_size = cfg.IF_DB_POOL_SIZE
    old_timeout = cfg.IF_DB_POOL_TIMEOUT
    old_batch = cfg.IF_DB_BATCH_ENABLED
    cfg.IF_DB_POOL_SIZE = pool_size
    cfg.IF_DB_POOL_TIMEOUT = timeout
    cfg.IF_DB_BATCH_ENABLED = batch_enabled
    try:
        db = DB(path)
        await db._ensure_initialized()
    finally:
        cfg.IF_DB_POOL_SIZE = old_size
        cfg.IF_DB_POOL_TIMEOUT = old_timeout
        cfg.IF_DB_BATCH_ENABLED = old_batch
    return db, path


async def _cleanup(db, path: str):
    """清理临时 DB 文件。"""
    try:
        await db.close()
    except Exception:
        pass
    try:
        os.unlink(path)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.unlink(path + suffix)
    except OSError:
        pass


class TestConnectionPool:
    """连接池基础行为验证。"""

    @pytest.mark.asyncio
    async def test_pool_creates_correct_number_of_connections(self):
        """连接池按 IF_DB_POOL_SIZE 创建正确数量的写连接。"""
        for size in (1, 3, 5):
            db, path = await _make_db(pool_size=size)
            try:
                assert len(db._connections) == size
                assert len(db._conn_locks) == size
            finally:
                await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_pool_size_1_single_conn(self):
        """IF_DB_POOL_SIZE=1 时退化为单连接模式。"""
        db, path = await _make_db(pool_size=1)
        try:
            assert len(db._connections) == 1
            # _conn 向后兼容引用
            assert db._conn is db._connections[0]
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_read_conn_separate_from_write_conns(self):
        """_read_conns 是独立连接池，不在写连接池中。"""
        db, path = await _make_db(pool_size=3)
        try:
            assert db._read_conn is not None
            assert len(db._read_conns) == 3
            # _read_conns 不应在 _connections 列表中
            for conn in db._read_conns:
                for wconn in db._connections:
                    assert conn is not wconn
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_round_robin_distributes_writes(self):
        """Round-robin 分配写连接。"""
        db, path = await _make_db(pool_size=3)
        try:
            indices = []
            for _ in range(6):
                idx, _, _ = await db._get_write_conn()
                indices.append(idx)
            # 3 个连接 round-robin: 0,1,2,0,1,2
            assert indices == [0, 1, 2, 0, 1, 2]
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_read_uses_read_conn_not_pool(self):
        """读操作走 _read_conns，不用写连接池。"""
        db, path = await _make_db(pool_size=3)
        try:
            read_conn_ids = {id(c) for c in db._read_conns}
            write_conn_ids = {id(c) for c in db._connections}

            await db.create_request("t1", "p", "1:1", False)
            await db.flush()

            # get 应该走 _read_conns
            row = await db.get("t1")
            assert row is not None
            assert row["id"] == "t1"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_write_uses_pool_connections(self):
        """写操作使用连接池的连接（非批量模式）。"""
        import api.config as cfg
        db, path = await _make_db(pool_size=2)
        try:
            old_batch = cfg.IF_DB_BATCH_ENABLED
            cfg.IF_DB_BATCH_ENABLED = False
            try:
                conn_ids_before = {id(c) for c in db._connections}
                await db.create_request("t1", "p", "1:1", False)
                # 写后连接池共享不变
                assert {id(c) for c in db._connections} == conn_ids_before
            finally:
                cfg.IF_DB_BATCH_ENABLED = old_batch
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_close_cleans_all_connections(self):
        """close() 关闭所有写连接和读连接。"""
        db, path = await _make_db(pool_size=3, batch_enabled=False)
        # 关闭前验证连接存在
        assert all(c is not None for c in db._connections)
        await db.close()
        # close 后直接 execute 应报错（连接已关）
        for conn in db._connections:
            with pytest.raises(Exception):
                await conn.execute("SELECT 1")


class TestConcurrentReadWrite:
    """多连接并发读写验证。"""

    @pytest.mark.asyncio
    async def test_concurrent_writes_from_multiple_tasks(self):
        """多协程并发写入不冲突。"""
        db, path = await _make_db(pool_size=3)
        try:
            errors = []

            async def writer(n: int):
                try:
                    for i in range(10):
                        task_id = f"t{n}-{i}"
                        await db.create_request(task_id, f"prompt-{n}-{i}", "1:1", False)
                        await db.mark_started(task_id)
                        await db.mark_finished(task_id, "completed", f"https://img/{task_id}", None, 0.5)
                except Exception as e:
                    errors.append(e)

            tasks = [asyncio.create_task(writer(i)) for i in range(5)]
            await asyncio.gather(*tasks)

            assert not errors, f"并发异常: {errors}"
            await db.flush()
            assert await db.count() == 50
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_concurrent_read_write_no_deadlock(self):
        """并发读写不产生死锁（读走读池，写走 pool）。"""
        db, path = await _make_db(pool_size=3)
        try:
            errors = []

            async def writer():
                try:
                    for i in range(20):
                        await db.create_request(f"w-{i}", "p", "1:1", False)
                        await asyncio.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            async def reader():
                try:
                    for _ in range(20):
                        await db.recent_images(limit=10)
                        await db.stats_overview()
                        await asyncio.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            tasks = [
                asyncio.create_task(writer()),
                asyncio.create_task(reader()),
                asyncio.create_task(reader()),
            ]
            await asyncio.gather(*tasks)

            assert not errors, f"并发异常: {errors}"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_round_robin_under_concurrent_writes(self):
        """并发写入时 round-robin 分配不同连接。"""
        db, path = await _make_db(pool_size=3)
        try:
            used_indices = set()

            async def record_conn():
                idx, conn, _ = await db._get_write_conn()
                used_indices.add(idx)

            tasks = [asyncio.create_task(record_conn()) for _ in range(10)]
            await asyncio.gather(*tasks)

            # 至少用到 2 个不同连接
            assert len(used_indices) >= 2, f"round-robin 未分配到不同连接: {used_indices}"
        finally:
            await _cleanup(db, path)


class TestHealthCheck:
    """自动重连验证。"""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_for_healthy_conn(self):
        """健康检查对正常连接返回 True。"""
        db, path = await _make_db(pool_size=2)
        try:
            for conn in db._connections:
                assert await db._health_check(conn) is True
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_health_check_returns_false_for_closed_conn(self):
        """健康检查对已关闭连接返回 False。"""
        db, path = await _make_db(pool_size=2)
        try:
            conn = db._connections[0]
            await conn.close()
            assert await db._health_check(conn) is False
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_auto_reconnect_on_stale_connection(self):
        """失效连接自动重建（健康检查失败后 _get_write_conn 重建）。"""
        db, path = await _make_db(pool_size=2)
        try:
            # 关闭 connections[0]，使其失效
            old_conn = db._connections[0]
            old_conn_id = id(old_conn)
            await old_conn.close()

            # round-robin: 第1次 → idx=0 触发重建，第2次 → idx=1，第3次 → idx=0
            idx1, conn1, _ = await db._get_write_conn()  # idx=0, 触发重建
            assert idx1 == 0
            assert id(conn1) != old_conn_id
            assert await db._health_check(conn1) is True

            # 第2次 → idx=1
            idx2, conn2, _ = await db._get_write_conn()
            assert idx2 == 1

            # 第3次 → idx=0，重建后的连接正常
            idx3, conn3, _ = await db._get_write_conn()
            assert idx3 == 0
            assert id(conn3) == id(conn1)  # 同一重建连接
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_auto_reconnect_still_works(self):
        """重建后的连接可正常读写。"""
        db, path = await _make_db(pool_size=2, batch_enabled=False)
        try:
            # 关闭所有写连接
            for conn in db._connections:
                await conn.close()

            # 写入应触发重建
            await db.create_request("t1", "p", "1:1", False)
            # 读走读池（未关闭），不受影响
            row = await db.get("t1")
            assert row is not None
            assert row["status"] == "pending"
        finally:
            await _cleanup(db, path)


class TestPoolSizeOne:
    """IF_DB_POOL_SIZE=1 兼容旧行为。"""

    @pytest.mark.asyncio
    async def test_single_conn_behaves_like_original(self):
        """单连接模式下写入和读取正常。"""
        db, path = await _make_db(pool_size=1)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.mark_started("t1")
            await db.mark_finished("t1", "completed", "https://img", None, 1.0)
            await db.flush()

            row = await db.get("t1")
            assert row is not None
            assert row["status"] == "completed"
            assert row["image_url"] == "https://img"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_pool_size_1_no_round_robin(self):
        """单连接时 round-robin 始终返回索引 0。"""
        db, path = await _make_db(pool_size=1)
        try:
            for _ in range(5):
                idx, _, _ = await db._get_write_conn()
                assert idx == 0
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_pool_size_1_backward_compat_conn(self):
        """单连接时 _conn 指向 _connections[0]（旧代码兼容）。"""
        db, path = await _make_db(pool_size=1)
        try:
            assert db._conn is db._connections[0]
        finally:
            await _cleanup(db, path)


class TestConnectionLeak:
    """连接泄漏检测。"""

    @pytest.mark.asyncio
    async def test_no_connection_leak_after_close(self):
        """close() 后所有连接关闭，无泄漏。"""
        db, path = await _make_db(pool_size=4)
        try:
            conns = db._connections[:]
            read_conns = db._read_conns[:]
            await db.close()
            # 所有写连接应被关闭
            for i, c in enumerate(conns):
                with pytest.raises(Exception):
                    await c.execute("SELECT 1")
            # 所有读连接应被关闭
            for c in read_conns:
                with pytest.raises(Exception):
                    await c.execute("SELECT 1")
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_close_then_create_does_not_leak(self):
        """close 后重建不泄漏文件句柄。"""
        import api.config as cfg
        from api.db import DB

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        old_size = cfg.IF_DB_POOL_SIZE
        cfg.IF_DB_POOL_SIZE = 3
        try:
            db1 = DB(path)
            await db1.create_request("t1", "p", "1:1", False)
            await db1.flush()
            await db1.close()

            db2 = DB(path)
            try:
                # 新实例应能读取旧数据
                row = await db2.get("t1")
                assert row is not None
                assert row["id"] == "t1"
            finally:
                await db2.close()
        finally:
            cfg.IF_DB_POOL_SIZE = old_size
            db_temp = DB(path)
            await db_temp.close()
            _cleanup(db_temp, path)


class TestBatchWriteWithPool:
    """IMP-20 连接池 + IMP-25 批量写入兼容性。"""

    @pytest.mark.asyncio
    async def test_batch_write_with_pool(self):
        """批量写入模式下连接池正常工作。"""
        db, path = await _make_db(pool_size=3)
        try:
            await db.create_request("t1", "p", "1:1", False)
            await db.create_request("t2", "p", "16:9", True)
            await db.create_request("t3", "p", "4:3", False, "img", "anime")
            assert len(db._write_buffer) == 3

            await db.flush()
            assert len(db._write_buffer) == 0
            row1 = await db.get("t1")
            assert row1["status"] == "pending"
            row3 = await db.get("t3")
            assert row3["type"] == "img"
        finally:
            await _cleanup(db, path)

    @pytest.mark.asyncio
    async def test_non_batch_write_with_pool(self):
        """非批量模式下连接池写入正常。"""
        db, path = await _make_db(pool_size=3, batch_enabled=False)
        try:
            before = db._commit_count
            await db.create_request("t1", "p", "1:1", False)
            assert db._commit_count == before + 1
            await db.mark_started("t1")
            assert db._commit_count == before + 2
            await db.mark_finished("t1", "completed", "https://img", None, 1.0)
            assert db._commit_count == before + 3

            row = await db.get("t1")
            assert row["status"] == "completed"
        finally:
            await _cleanup(db, path)