#!/usr/bin/env python3
"""nanobanana 批量注册脚本（生产用，依赖 cf_solver + 22.do 邮箱 + 免费代理池）。

用法：
  python scripts/batch_register_nb.py --target 10000 --concurrency 2
  python scripts/batch_register_nb.py --resume --target 10000 --concurrency 2

设计：
  - 复用 api/registerer.py 的 NanobananaRegisterer（不重复实现注册逻辑）
  - 支持 checkpoint 断点续跑（写 /tmp/nb_registry.json）
  - 错误分类退避：429→60s, socket→30s, other→15s
  - 连续 10 次失败则暂停 5 分钟（留手动恢复窗口）
  - 每 10 次注册输出 JSON 进度行
  - SIGTERM/SIGINT 时保存 checkpoint 后优雅退出
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import tempfile
import time

# 添加项目根目录到路径，确保可以直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置环境变量（不启动 worker/engine）
os.environ.setdefault("IF_ACCOUNT_AUTO", "0")
os.environ.setdefault("IF_MOCK_REGISTER", "0")
os.environ.setdefault("IF_DB_FILE", "data/account_pool.db")
os.environ.setdefault("IF_MOCK_UPSTREAM", "0")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch_register")

CHECKPOINT = os.path.join(tempfile.gettempdir(), "nb_registry.json")
MAX_CONSECUTIVE_FAIL = 10
PROGRESS_INTERVAL = 10


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=10000, help="目标注册数")
    parser.add_argument(
        "--concurrency", type=int, default=2, choices=range(1, 4), help="并发数（cf_solver 单槽，建议 2）"
    )
    parser.add_argument("--resume", action="store_true", help="从 checkpoint 恢复")
    args = parser.parse_args()

    # 从 checkpoint 加载已注册邮箱
    registered = set()
    if args.resume and os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT, "r") as f:
                data = json.load(f)
                registered = set(data.get("emails", []))
            log.info("从 checkpoint 恢复：已注册 %d 个", len(registered))
        except Exception as e:
            log.warning("checkpoint 加载失败: %s, 从头开始", e)

    # 初始化注册器
    from api.registerer import NanobananaRegisterer
    from api.account_pool import account_pool

    registerer = NanobananaRegisterer()
    start_time = time.time()
    consecutive_fail = 0
    total_start = len(registered)

    # 信号处理
    shutting_down = False

    def _signal_handler(sig, frame):
        nonlocal shutting_down
        shutting_down = True
        log.info("收到信号 %s，正在保存 checkpoint...", sig)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    async def _register_one():
        try:
            result = await registerer.register_one()
            if result:
                email = result["email"]
                account_pool.add(
                    "nanobanana", email, result["cookie"], result.get("password"), result.get("credits", 4)
                )
                registered.add(email)
                return True, email
            return False, None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                log.warning("429 限流，等待 60s")
                await asyncio.sleep(60)
            elif "socket" in err_str.lower() or "connect" in err_str.lower():
                log.warning("网络异常，等待 30s")
                await asyncio.sleep(30)
            else:
                log.warning("注册异常: %s, 等待 15s", err_str)
                await asyncio.sleep(15)
            return False, None

    sem = asyncio.Semaphore(args.concurrency)
    progress = 0

    async def _worker():
        nonlocal consecutive_fail, progress
        while not shutting_down and len(registered) < args.target:
            async with sem:
                ok, email = await _register_one()
                if ok:
                    consecutive_fail = 0
                    progress += 1
                    if progress % PROGRESS_INTERVAL == 0:
                        elapsed = time.time() - start_time
                        rate = progress / (elapsed / 3600) if elapsed > 0 else 0
                        log.info(
                            json.dumps(
                                {
                                    "count": len(registered),
                                    "target": args.target,
                                    "rate": f"{rate:.1f}/hr",
                                    "elapsed_min": f"{elapsed/60:.1f}",
                                    "consecutive_fail": consecutive_fail,
                                }
                            )
                        )
                else:
                    consecutive_fail += 1
                    if consecutive_fail >= MAX_CONSECUTIVE_FAIL:
                        log.warning("连续 %d 次失败，暂停 5 分钟", MAX_CONSECUTIVE_FAIL)
                        await asyncio.sleep(300)
                        consecutive_fail = 0
                    # 保存 checkpoint
                    with open(CHECKPOINT, "w") as f:
                        json.dump({"emails": list(registered), "updated_at": time.time()}, f)
                    await asyncio.sleep(5)

    workers = [asyncio.create_task(_worker()) for _ in range(args.concurrency)]
    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        pass
    finally:
        # 最终 checkpoint
        with open(CHECKPOINT, "w") as f:
            json.dump({"emails": list(registered), "updated_at": time.time()}, f)
        elapsed = time.time() - start_time
        log.info(
            "注册完成: %d 个, 耗时 %.1f 分钟, 速率 %.1f/hr",
            len(registered),
            elapsed / 60,
            len(registered) / (elapsed / 3600) if elapsed > 0 else 0,
        )


if __name__ == "__main__":
    asyncio.run(main())
