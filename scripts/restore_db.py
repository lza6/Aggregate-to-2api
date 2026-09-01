"""SQLite 数据库恢复脚本（P2-1）。

从备份文件恢复到目标 DB。恢复前自动对当前目标 DB 做一份 pre-restore 备份（防覆盖），
恢复后立即 PRAGMA integrity_check 校验，确保恢复结果完整可用。

用法:
    python scripts/restore_db.py --backup data/backups/imagefree-20260901-030000.db
    python scripts/restore_db.py --backup data/backups/imagefree-20260901-030000.db --target data/imagefree.db

⚠️ 恢复是覆盖操作：目标 DB 的当前内容会被备份内容替换。脚本会先自动备份当前 target
到 <target>.pre-restore-<ts>.db，但生产恢复仍建议手动二次确认。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time

DEFAULT_TARGET = "data/imagefree.db"


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def _integrity_check(db_path: str) -> bool:
    """PRAGMA integrity_check 校验 DB 完整性。"""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("PRAGMA integrity_check")
        result = cur.fetchone()
        conn.close()
        return result is not None and result[0] == "ok"
    except sqlite3.Error as e:
        print(f"[FAIL] integrity_check 异常 {db_path}: {e}", file=sys.stderr)
        return False


def restore(backup_path: str, target: str) -> int:
    """从备份恢复到 target，返回 0=成功 / 1=失败。"""
    if not os.path.exists(backup_path):
        print(f"[FAIL] 备份文件不存在: {backup_path}", file=sys.stderr)
        return 1

    # 1. 先校验备份本身的完整性（恢复前预检）
    if not _integrity_check(backup_path):
        print(f"[FAIL] 备份完整性校验失败，中止恢复: {backup_path}", file=sys.stderr)
        return 1
    print(f"[OK] 备份完整性校验通过: {backup_path}")

    # 2. 对当前 target 做自动 pre-restore 备份（防覆盖丢失）
    if os.path.exists(target):
        pre_restore = f"{target}.pre-restore-{_timestamp()}.db"
        try:
            shutil.copy2(target, pre_restore)
            print(f"[OK] 当前 target 已自动备份: {pre_restore}")
        except OSError as e:
            print(f"[FAIL] 自动 pre-restore 备份失败: {e}", file=sys.stderr)
            return 1
    else:
        print(f"[INFO] target 不存在，将新建: {target}")

    # 3. 确保目标目录存在
    target_dir = os.path.dirname(os.path.abspath(target))
    os.makedirs(target_dir, exist_ok=True)

    # 4. 恢复：备份文件已通过 VACUUM INTO 生成（紧凑单文件，无 WAL/SHM 伴随），
    #    直接复制即可。复制后若启动服务会自动重建 WAL（无需手动 checkpoint）。
    try:
        shutil.copy2(backup_path, target)
    except OSError as e:
        print(f"[FAIL] 复制备份到 target 失败: {e}", file=sys.stderr)
        return 1

    # 5. 清理可能残留的旧 WAL/SHM（避免旧 WAL 与新主库不一致）
    for suffix in ("-wal", "-shm"):
        sidecar = f"{target}{suffix}"
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
                print(f"[OK] 清理残留 {sidecar}")
            except OSError:
                pass

    # 6. 恢复后校验完整性
    if not _integrity_check(target):
        print(f"[FAIL] 恢复后 target 完整性校验失败: {target}", file=sys.stderr)
        return 1

    # 7. 信息性：行数对照
    try:
        conn = sqlite3.connect(target)
        cur = conn.execute("SELECT count(*) FROM requests")
        rows = cur.fetchone()[0]
        conn.close()
        print(f"[OK] 恢复成功: {target} (requests={rows})")
    except sqlite3.Error:
        print(f"[OK] 恢复成功: {target} (requests 表不存在，跳过行数校验)")

    print("[DONE] 恢复完成。如服务在运行，请重启容器使新 DB 生效：")
    print("       sudo docker compose restart api")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite 从备份恢复（自动 pre-restore + integrity_check）")
    parser.add_argument("--backup", required=True, help="备份文件路径")
    parser.add_argument("--target", default=DEFAULT_TARGET, help=f"恢复目标 DB 路径（默认 {DEFAULT_TARGET}）")
    args = parser.parse_args()
    return restore(args.backup, args.target)


if __name__ == "__main__":
    sys.exit(main())
