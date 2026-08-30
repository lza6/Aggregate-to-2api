"""模块级共享状态（v4.2 拆分：main.py 的全局单例集中于此，供 routes/lifespan 引用）。

注意：本模块不能 import 任何 routes/ 子模块（避免循环），只做状态持有与工具函数。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from . import config
from .db import DB
from .worker import Engine
from .cache import LRUCache

log = logging.getLogger("imagefree_api")

# ── 全局单例（main.py 组装时初始化）──
db: DB = DB(config.DB_FILE)
engine: Engine = Engine(db)
gallery_cache: LRUCache = LRUCache(maxsize=config.IF_LRU_CACHE_SIZE, ttl=config.IF_LRU_CACHE_TTL, persist_db=db)

# 路由/提供商（providers.registry 模块级单例 registry 已存在）
from .providers import registry  # noqa: E402,F401
from .providers.registry import bootstrap as providers_bootstrap  # noqa: E402,F401

# 图生图 lifespan 注入 engine 前记录旧值（共享单例跨 lifespan 复用防污染）
_prev_engine = None


def _prev_engine_fallback(imagefree_provider, engine_to_set) -> None:
    """lifespan 启动时记录注入前值并注入 engine。"""
    global _prev_engine
    _prev_engine = getattr(imagefree_provider, "engine", None)
    imagefree_provider.engine = engine_to_set


# ── 工具函数 ──
def _uptime_human(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}天{h}小时"
    if h:
        return f"{h}小时{m}分钟"
    if m:
        return f"{m}分钟"
    return f"{seconds}秒"


async def shutdown_phase(timeout: float, label: str, *coros):
    """带超时和标签的优雅关闭阶段（A-03）。"""
    if not coros:
        return
    tasks = [asyncio.create_task(c) for c in coros]
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for t in pending:
        t.cancel()
    if pending:
        log.warning("%s: %d 个任务超时未完成, 已强制取消", label, len(pending))


_SLOW_PAGE = Path(__file__).parent / "static" / "slow.html"
