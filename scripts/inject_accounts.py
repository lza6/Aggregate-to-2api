"""号池预置/批量注册脚本：向 account_pool 注入账号（文件导入）或批量真实注册。

用法：
  # 从文件导入现成账号（每行 JSON 或 tab 分隔：email<TAB>cookie<TAB>[password<TAB>credits]）
  python scripts/inject_accounts.py --provider minimaxh3 --import accounts.txt

  # 批量真实注册（需 cf_solver :8001 + 邮箱源可达；受 Turnstile 求解速度限制，默认 1/轮询 2s）
  # --use-proxy-pool 时每号从免费/住宅代理池轮换出口 IP（防批量注册同 IP 风控）
  python scripts/inject_accounts.py --provider minimaxh3 --count 500 --real --use-proxy-pool

  # mock 注册（测试/演示号池补号逻辑，不碰上游）
  python scripts/inject_accounts.py --provider nanobanana --count 10 --mock
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _import_file(pool, provider: str, path: str) -> int:
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("{"):  # JSON
                import json
                acc = json.loads(line)
                pool.add(provider, acc["email"], acc.get("cookie", ""),
                         acc.get("password"), int(acc.get("credits", 0)))
            else:  # tab 分隔
                parts = line.split("\t")
                email, cookie = parts[0], parts[1]
                password = parts[2] if len(parts) > 2 else None
                credits = int(parts[3]) if len(parts) > 3 else 4
                pool.add(provider, email, cookie, password, credits)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["minimaxh3", "nanobanana"])
    ap.add_argument("--import", dest="import_file", help="从文件导入账号")
    ap.add_argument("--count", type=int, default=10, help="批量注册数量")
    ap.add_argument("--real", action="store_true", help="真实注册（需 cf_solver+邮箱）")
    ap.add_argument("--mock", action="store_true", help="mock 注册（不碰上游）")
    ap.add_argument("--use-proxy-pool", action="store_true",
                    help="每号从代理池轮换出口 IP（需 IF_PROXY_FILE 或 IF_FREE_PROXY=1，防批量注册同 IP 风控）")
    ap.add_argument("--db", default="data/account_pool.db")
    args = ap.parse_args()

    os.environ["IF_ACCOUNT_DB_FILE"] = args.db
    if args.mock:
        os.environ["IF_MOCK_REGISTER"] = "1"

    from api.account_pool import AccountPool
    from api import config
    pool = AccountPool(args.db)

    if args.import_file:
        n = _import_file(pool, args.provider, args.import_file)
        print(f"导入 {n} 个 {args.provider} 账号到号池")
        pool._conn.close()
        return 0

    import asyncio
    from api.registerer import build_registerers

    reg = build_registerers().get(args.provider)
    if reg is None:
        print(f"无 {args.provider} 注册器")
        return 1

    async def _run():
        from api.proxy_pool import proxy_pool
        from api.free_proxy_fetcher import FreeProxyFetcher, _precheck
        # H4(审计修复): --use-proxy-pool 必须显式加载代理源，否则 proxy_pool.enabled 恒 False（静默 no-op）。
        if args.use_proxy_pool:
            if config.PROXY_FILE:
                proxy_pool.load_file(config.PROXY_FILE)
            if not proxy_pool.enabled:
                print("[提示] 住宅代理池为空，尝试抓取免费代理兜底…")
                if config.FREE_PROXY_ENABLED:
                    f = FreeProxyFetcher(proxy_pool)
                    import httpx as _hx
                    f._client = _hx.AsyncClient(timeout=15.0, proxy=config.PROXY)
                    stats = await f._fetch_once()
                    print(f"免费代理抓取: injected={stats['injected']}")
                if not proxy_pool.enabled:
                    print("[错误] 代理池仍为空（需 IF_PROXY_FILE 或 IF_FREE_PROXY=1）。注册流量含凭据，禁止回退直连批量注册。")
                    return
        done = 0
        for i in range(args.count):
            try:
                if args.use_proxy_pool and proxy_pool.enabled:
                    # M10(审计修复): 注册流量含邮箱/密码/验证链接，强制住宅代理，free 池空时明确报错而非静默回退
                    reg.proxy = await proxy_pool.acquire(prefer_source="residential")
                acc = await reg.register_one()
                if acc:
                    pool.add(args.provider, acc["email"], acc["cookie"], acc.get("password"),
                             credits=acc.get("credits", 0))
                    done += 1
                    print(f"[{i+1}/{args.count}] 注册成功 {acc['email']} credits={acc.get('credits')} proxy={reg.proxy or 'direct'}")
                else:
                    print(f"[{i+1}/{args.count}] 注册失败（跳过）")
            except Exception as e:
                print(f"[{i+1}/{args.count}] 注册异常: {str(e)[:100]}")
            if i < args.count - 1:
                await asyncio.sleep(1.0)

    asyncio.run(_run())
    print(f"\n号池 {args.provider} 现有 {len(pool.get(args.provider))} 个账号")
    pool._conn.close()
    # L8(审计修复): 关闭注册器同步 client
    try:
        reg.client.close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
