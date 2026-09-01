"""SQLite 数据库在线热备脚本（P2-1）。

用 VACUUM INTO 实现 WAL 模式下的在线热备（不锁写、安全），生成带时间戳的全量备份，
备份后立即 PRAGMA integrity_check 校验，并按 keep-days 滚动清理旧备份。

支持单 DB 备份或扫描 data/ 下所有 .db 文件批量备份（--all）。

用法:
    python scripts/backup_db.py --db data/imagefree.db --out-dir data/backups
    python scripts/backup_db.py --all --out-dir data/backups --keep-days 7
    # cron 调度（每日 03:00 全量备份，保留 7 天）:
    # 0 3 * * * cd /home/ubuntu/imagefree-api && python scripts/backup_db.py --db data/imagefree.db --out-dir data/backups
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_DB = "data/imagefree.db"
DEFAULT_OUT_DIR = "data/backups"
DEFAULT_KEEP_DAYS = 7


def _timestamp() -> str:
    """YYYYMMDD-HHMMSS 时间戳（用于备份文件名排序）。"""
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def _db_stem(db_path: str) -> str:
    """data/imagefree.db → imagefree（用于文件名前缀）。"""
    return Path(db_path).stem


def _integrity_check(backup_path: str) -> bool:
    """PRAGMA integrity_check 校验备份完整性，返回 ok 标志。"""
    try:
        conn = sqlite3.connect(backup_path)
        cur = conn.execute("PRAGMA integrity_check")
        result = cur.fetchone()
        conn.close()
        return result is not None and result[0] == "ok"
    except sqlite3.Error as e:
        print(f"[FAIL] integrity_check 异常 {backup_path}: {e}", file=sys.stderr)
        return False


def _row_count(backup_path: str, table: str = "requests") -> int | None:
    """校验备份中关键表行数（requests 是主业务表，存在则返回行数）。"""
    try:
        conn = sqlite3.connect(backup_path)
        # 表不存在时返回 None（不当作失败，仅作信息）
        cur = conn.execute("SELECT count(*) FROM requests")
        n = cur.fetchone()[0]
        conn.close()
        return n
    except sqlite3.Error:
        return None


def backup_one(db_path: str, out_dir: str, keep_days: int) -> str | None:
    """备份单个 DB 文件，返回备份路径或 None（失败）。"""
    if not os.path.exists(db_path):
        print(f"[SKIP] DB 不存在: {db_path}", file=sys.stderr)
        return None

    os.makedirs(out_dir, exist_ok=True)
    stem = _db_stem(db_path)
    backup_path = os.path.join(out_dir, f"{stem}-{_timestamp()}.db")

    # VACUUM INTO：WAL 模式在线热备（不阻塞写，生成紧凑全量副本）
    # 对源库连接执行 VACUUM INTO '目标路径'，源库需先 checkpoint 确保 WAL 已合并
    try:
        conn = sqlite3.connect(db_path)
        # 合并 WAL 到主库后再 VACUUM INTO，保证备份是最新快照
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute(f"VACUUM INTO '{backup_path}'")
        conn.close()
    except sqlite3.Error as e:
        print(f"[FAIL] VACUUM INTO 失败 {db_path} → {backup_path}: {e}", file=sys.stderr)
        return None

    # 校验完整性
    if not _integrity_check(backup_path):
        print(f"[FAIL] integrity_check 失败 {backup_path}", file=sys.stderr)
        return None

    # 行数校验（信息性，不阻断）
    rows = _row_count(backup_path)
    rows_info = f" requests={rows}" if rows is not None else " requests表不存在(跳过行数校验)"
    size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"[OK] 备份成功: {backup_path} ({size_mb:.2f}MB{rows_info})")

    # 滚动清理旧备份
    if keep_days > 0:
        _prune_old(out_dir, stem, keep_days)

    return backup_path


def _prune_old(out_dir: str, stem: str, keep_days: int) -> None:
    """清理超过 keep_days 天的旧备份（按文件名时间戳排序）。"""
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for name in os.listdir(out_dir):
        if not name.startswith(f"{stem}-") or not name.endswith(".db"):
            continue
        path = os.path.join(out_dir, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    if removed:
        print(f"[CLEAN] 清理 {removed} 个超 {keep_days} 天的旧备份（{stem}）")


def find_all_dbs(data_dir: str = "data") -> list[str]:
    """扫描 data/ 下所有 .db 文件（排除 -wal/-shm 副本与 backups 子目录）。"""
    if not os.path.isdir(data_dir):
        return []
    dbs: list[str] = []
    for name in os.listdir(data_dir):
        full = os.path.join(data_dir, name)
        # 跳过 WAL/SHM 伴随文件、备份目录、非 .db 文件
        if name.endswith("-wal") or name.endswith("-shm"):
            continue
        if name.endswith(".db") and os.path.isfile(full):
            dbs.append(full)
    return sorted(dbs)


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite 在线热备（VACUUM INTO + integrity_check）")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"目标 DB 路径（默认 {DEFAULT_DB}）")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help=f"备份输出目录（默认 {DEFAULT_OUT_DIR}）")
    parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS, help=f"保留天数，超期滚动清理（默认 {DEFAULT_KEEP_DAYS}）")
    parser.add_argument("--all", action="store_true", help="备份 data/ 下所有 .db 文件（批量）")
    args = parser.parse_args()

    if args.all:
        dbs = find_all_dbs("data")
        if not dbs:
            print("[SKIP] data/ 下无 .db 文件", file=sys.stderr)
            return 0
        print(f"[BATCH] 备份 {len(dbs)} 个 DB → {args.out_dir}")
        ok, fail = 0, 0
        for db in dbs:
            res = backup_one(db, args.out_dir, args.keep_days)
            if res:
                ok += 1
            else:
                fail += 1
        print(f"[DONE] 成功 {ok} / 失败 {fail} / 共 {len(dbs)}")
        return 0 if fail == 0 else 1

    res = backup_one(args.db, args.out_dir, args.keep_days)
    return 0 if res else 1


if __name__ == "__main__":
    sys.exit(main())
