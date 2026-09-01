"""性能基准测试：关键路径操作的基准测试。

使用 pytest-benchmark 精确测量操作耗时。
依赖：pytest-benchmark（pip install pytest-benchmark）

用法：pytest tests/performance/ --benchmark-only
"""

import pytest


@pytest.mark.slow
class TestEngineBenchmark:
    """引擎关键路径基准测试。"""

    @pytest.mark.benchmark
    def test_engine_submit_perf(self, benchmark, tmp_db, no_proxy_env):
        """引擎提交操作的基准测试。"""
        from api.worker import Engine

        engine = Engine(tmp_db)

        async def _setup():
            await engine.start()
            return engine

        import asyncio

        engine = asyncio.run(_setup())

        def _submit():
            import asyncio

            task_id = asyncio.run(engine.submit("benchmark prompt", "1:1", False, "default"))
            return task_id

        benchmark.pedantic(_submit, rounds=50, iterations=2)
        asyncio.run(engine.stop())


@pytest.mark.benchmark
@pytest.mark.slow
class TestDBBenchmark:
    """DB 操作基准测试。"""

    def test_db_create_and_query(self, benchmark, tmp_db):
        """DB 创建任务 + 查询的基准测试。"""
        db = tmp_db

        def _create_and_query():
            import asyncio
            import uuid

            tid = str(uuid.uuid4())

            async def _do():
                await db.create_request(tid, "test prompt", "1:1", False, "txt", "default")
                return await db.get(tid)

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_do())
            finally:
                loop.close()

        benchmark.pedantic(_create_and_query, rounds=100, iterations=1)


@pytest.mark.benchmark
@pytest.mark.slow
class TestConfigBenchmark:
    """配置加载基准测试。"""

    def test_apply_model_perf(self, benchmark):
        """模型风格预设注入性能。"""
        from api.config import apply_model

        benchmark(apply_model, "a test prompt for image generation", "anime")
