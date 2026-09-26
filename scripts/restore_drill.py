"""SQLite 备份恢复演练脚本（非破坏性，J2 v20.3.6）。

目的：每周自动验证「备份真实可恢复」，不做生产覆盖（区别于 restore_db.py 的覆盖恢复）。
方法：最新备份 → 临时目录 → 打开 + PRAGMA integrity_check + 查询 requests 表行数 → 清理临时目录。
无任何生产 DB 写入，纯只读演练。

用法:
    python scripts/restore_drill.py --backup-dir /opt/imagefree-api/backups
    # cron 每周日 04:00:
    # 0 4 * * 0 cd /opt/imagefree-api && .venv/bin/python scripts/restore_drill.py --backup-dir /opt/imagefree-api/backups >> /opt/imagefree-api/backups/drill.log 2>&1
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sqlite3
import sys
import tempfile
import time


def _latest_backup(backup_dir: str, db_name: str = "imagefree") -> str | None:
    """取指定 DB 的最新备份（按时间戳排序，imagefree-20260926-061642.db）。"""
    pat = os.path.join(backup_dir, f"{db_name}-*.db")
    files = sorted(glob.glob(pat), reverse=True)
    return files[0] if files else None


def drill(backup_dir: str, db_name: str = "imagefree") -> int:
    """从最新备份恢复到临时目录并验证可查询。返回 0=成功 / 1=失败。"""
    latest = _latest_backup(backup_dir, db_name)
    if not latest:
        print(f"[SKIP] 无 {db_name} 备份（backup_dir={backup_dir}）")
        return 0
    tmp = tempfile.mkdtemp(prefix="restore-drill-")
    try:
        target = os.path.join(tmp, f"{db_name}.db")
        shutil.copy2(latest, target)
        conn = sqlite3.connect(target)
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        # 主表存在则查行数；不存在（非主库）只校验完整性
        try:
            rows = conn.execute("SELECT count(*) FROM requests").fetchone()[0]
            row_info = f" requests={rows}"
        except sqlite3.Error:
            row_info = " (无 requests 表，跳过行数)"
        conn.close()
        if integ != "ok":
            print(f"[FAIL] {db_name} 恢复演练失败: integrity={integ}（备份 {latest}）")
            return 1
        print(f"[OK] {db_name} 恢复演练通过: integrity=ok{row_info}（备份 {latest}）")
        return 0
    except Exception as e:
        print(f"[FAIL] {db_name} 恢复演练异常: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite 备份恢复演练（非破坏性）")
    ap.add_argument("--backup-dir", required=True, help="备份目录（含 <db>-<ts>.db）")
    ap.add_argument("--dbs", default="imagefree", help="逗号分隔要演练的 DB 名（默认 imagefree）")
    args = ap.parse_args()
    failed = 0
    for db in [d.strip() for d in args.dbs.split(",") if d.strip()]:
        failed += drill(args.backup_dir, db)
    print(f"[DONE] 恢复演练完成: {'全部通过' if failed == 0 else f'{failed} 个失败'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
