"""M9: 同步 deploy/api 与根 api/，检测代码漂移。

用法：
  python scripts/sync_deploy.py check    # 只对比，列出差异（exit 1 表示有差异）
  python scripts/sync_deploy.py sync     # 把 api/*.py 等同步到 deploy/api/

背景：deploy/api 是线上部署副本，根 api 是开发源。改代码必须两边一致，
否则上线版本与本地开发版漂移。本脚本用逐文件哈希对比，杜绝 M9 漂移风险。
"""
import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "api"
DST = ROOT / "deploy" / "api"

# 需保持一致的源码文件（.py 服务代码 + 首页文档）。不含 __pycache__。
FILES = ["__init__.py", "main.py",
         "imagefree_client.py", "turnstile_client.py", "solver_guard.py", "docs.html",
         "account_pool.py", "email_pool.py", "proxy_pool.py", "registerer.py",
         "free_proxy_fetcher.py", "kookeey.py",
         "semaphore_manager.py", "cache.py", "log_buffer.py", "base64_store.py",
         "retry_policy.py", "alerting.py", "audit.py", "metrics_ext.py", "log_ws.py",
         "context.py", "health.py", "cache_warmup.py", "errors.py",
         "slow_log.py", "worker_health.py", "disk_logger.py", "telemetry.py",
         "email_sources_linshi.py", "geo_ip.py", "provider_probe.py",
         "adaptive_router.py", "dispatch.py", "dispatch_edit.py",
         "lifespan.py", "handlers.py", "bg_tasks.py", "models.py", "meta.py", "sse_events.py",
         "contracts.py"]
# 需整体同步的目录（providers 包 / 静态资源 / 路由子包）
DIRS = ["providers", "static", "routes", "config", "db", "worker"]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def diff() -> list[str]:
    """返回不一致文件清单。"""
    out = []
    for name in FILES:
        s, d = SRC / name, DST / name
        if not s.exists():
            out.append(f"{name}: 源缺失")
        elif not d.exists():
            out.append(f"{name}: deploy 缺失")
        elif sha256(s) != sha256(d):
            out.append(name)
    # 目录递归比对
    for sub in DIRS:
        sdir, ddir = SRC / sub, DST / sub
        if not sdir.exists():
            out.append(f"{sub}/: 源缺失")
            continue
        for sfile in sorted(sdir.rglob("*")):
            if "__pycache__" in str(sfile):
                continue
            rel = sfile.relative_to(SRC)
            dfile = DST / rel
            if sfile.is_dir():
                continue
            if not dfile.exists():
                out.append(str(rel))
            elif sha256(sfile) != sha256(dfile):
                out.append(str(rel))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["check", "sync"], nargs="?", default="check")
    args = ap.parse_args()

    if args.action == "sync":
        DST.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            s, d = SRC / name, DST / name
            if s.exists():
                shutil.copy2(s, d)
                print(f"sync {name}")
        for sub in DIRS:
            sdir = SRC / sub
            if sdir.exists():
                for sfile in sorted(sdir.rglob("*")):
                    if "__pycache__" in str(sfile) or sfile.is_dir():
                        continue
                    rel = sfile.relative_to(SRC)
                    dfile = DST / rel
                    dfile.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sfile, dfile)
                    print(f"sync {rel}")
        print("deploy/api 已同步")
        return 0

    # Windows 控制台可能 GBK，兜底强制 UTF-8 输出（勾/叉等非 ASCII 不崩）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    diffs = diff()
    if not diffs:
        print("OK api/ 与 deploy/api/ 完全一致")
        return 0
    print("DIFF 以下文件不一致（运行 sync 修复）:")
    for name in diffs:
        print(f"  - {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
