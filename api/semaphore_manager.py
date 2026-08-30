"""IMP-27: 全局信号量管理（上游并发控制）。

对 imagefree.net 的最大并发请求数由 IF_UPSTREAM_MAX_INFLIGHT 控制。
所有上游 HTTP 请求（submit_generate / poll_generate_status）在发起前 acquire，
返回后 release，确保不会超过配置的上游并发上限。

使用 asyncio.Semaphore 而非 threading.Semaphore：
- 在 async 函数中 acquire 不阻塞事件循环
- 超时/取消场景下不会产生幽灵线程"""

import asyncio
import logging

from . import config

log = logging.getLogger("semaphore")

# 全局信号量：控制上游并发请求数。acquire/release 由调用方负责。
# 初始值 = IF_UPSTREAM_MAX_INFLIGHT，跨模块共享同一实例。
upstream_semaphore = asyncio.Semaphore(config.IF_UPSTREAM_MAX_INFLIGHT)
