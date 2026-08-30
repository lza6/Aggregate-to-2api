"""批量注号与号池健康管理脚本（支持目标 500 号，断点续存，多邮箱源故障转移）。

用法：
  python scripts/batch_register.py --provider nanobanana --target 500 --concurrency 2
  python scripts/batch_register.py --provider nanobanana --target 500 --concurrency 2
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.account_pool import account_pool
from api.registerer import build_registerers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch_register")


async def register_worker(provider: str, target: int, sem: asyncio.Semaphore, progress: dict):
    reg = build_registerers().get(provider)
    if not reg:
        log.error("未找到提供商 %s 的注册器", provider)
        return

    while True:
        current_count = len(account_pool.get(provider, status="ok"))
        if current_count >= target:
            break

        async with sem:
            current_count = len(account_pool.get(provider, status="ok"))
            if current_count >= target:
                break
            log.info("[%s] 正在注册新账号... 当前进度: %d/%d", provider, current_count, target)
            try:
                acc = await reg.register_one()
                if acc:
                    account_pool.add(
                        provider,
                        acc["email"],
                        acc["cookie"],
                        password=acc.get("password", ""),
                        credits=acc.get("credits", 4),
                    )
                    progress["success"] += 1
                    log.info(
                        "[%s] ✅ 成功入池: %s (积分=%s) 总有效: %d",
                        provider,
                        acc["email"],
                        acc.get("credits"),
                        len(account_pool.get(provider, status="ok")),
                    )
                else:
                    progress["failed"] += 1
                    log.warning("[%s] ⚠️ 注册未生成有效账号，稍后重试", provider)
            except Exception as e:
                progress["failed"] += 1
                log.exception("[%s] ❌ 注册异常: %s", provider, e)

        await asyncio.sleep(2.0)


async def main():
    parser = argparse.ArgumentParser(description="批量自动化注册号池账号")
    parser.add_argument("--provider", choices=["nanobanana"], default="nanobanana", help="目标提供商")
    parser.add_argument("--target", type=int, default=500, help="目标有效账号数")
    parser.add_argument("--concurrency", type=int, default=1, help="并发任务数（Turnstile 单槽建议 1~2）")
    args = parser.parse_args()

    current = len(account_pool.get(args.provider, status="ok"))
    log.info("=== 听风AI 批量注号引擎启动 ===")
    log.info(
        "目标提供商: %s | 当前有效号数: %d | 目标数: %d | 并发度: %d",
        args.provider,
        current,
        args.target,
        args.concurrency,
    )

    if current >= args.target:
        log.info("当前账号数已达到或超过目标数，无需额外注册。")
        return

    sem = asyncio.Semaphore(args.concurrency)
    progress = {"success": 0, "failed": 0}
    tasks = [
        asyncio.create_task(register_worker(args.provider, args.target, sem, progress)) for _ in range(args.concurrency)
    ]
    await asyncio.gather(*tasks)
    log.info(
        "=== 批量注号任务结束 === 成功: %d | 失败: %d | 当前池总数: %d",
        progress["success"],
        progress["failed"],
        len(account_pool.get(args.provider, status="ok")),
    )


if __name__ == "__main__":
    asyncio.run(main())
