"""base64 文件缓存存储（IMP-26）：将 image_base64 从 SQLite 全量存储改为本地文件缓存。

数据写入 data/imgs/<task_id>.<ext>，DB 仅存 file:// 路径。
文件通过 mtime 判定过期，由周期性清理任务移除。
"""

import logging
import os
import time

from . import config

log = logging.getLogger("base64_store")

# MIME → 扩展名映射
_MIME_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
}


def _mime_to_ext(mime: str) -> str:
    """MIME → 文件扩展名，未知 mime 回退 'bin'。"""
    return _MIME_EXT.get(mime.split(";")[0].strip(), "bin")


def ensure_dir() -> str:
    """确保缓存目录存在，返回规范化路径（公开入口，供 main.py lifespan 调用）。"""
    return _ensure_dir()


def _ensure_dir() -> str:
    """确保缓存目录存在，返回规范化路径。"""
    d = os.path.abspath(config.IF_BASE64_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _file_path(task_id: str, mime: str) -> str:
    """返回 data/imgs/<task_id>.<ext> 的绝对路径。"""
    ext = _mime_to_ext(mime)
    d = _ensure_dir()
    return os.path.join(d, f"{task_id}.{ext}")


def _file_path_from_id(task_id: str) -> str | None:
    """根据 task_id 在缓存目录中查找对应文件，返回路径或 None。"""
    d = os.path.abspath(config.IF_BASE64_DIR)
    if not os.path.isdir(d):
        return None
    # 遍历目录找 <task_id>.*
    for fname in os.listdir(d):
        if fname.startswith(task_id + "."):
            return os.path.join(d, fname)
    return None


def save_base64(task_id: str, data: str, mime: str) -> str:
    """将 base64 字符串写入文件，返回 file:// 路径。

    如果 data 已包含 file:// 前缀（幂等），直接返回原值。
    """
    if data.startswith("file://"):
        return data
    path = _file_path(task_id, mime)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        log.debug("base64 写入文件 %s (%d chars)", path, len(data))
    except OSError as e:
        log.warning("base64 文件写入失败 %s: %s", path, e)
        # 写入失败时仍返回原 data（降级：DB 存 base64 原文）
        return data
    return f"file://{path}"


def read_base64(task_id: str) -> str | None:
    """从文件读取 base64 字符串。返回 None 表示文件不存在或读取失败。"""
    path = _file_path_from_id(task_id)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        log.warning("base64 文件读取失败 %s: %s", path, e)
        return None


def delete_base64(task_id: str) -> None:
    """删除 task_id 对应的 base64 缓存文件。"""
    path = _file_path_from_id(task_id)
    if path is not None:
        try:
            os.unlink(path)
            log.debug("base64 文件已删除 %s", path)
        except OSError as e:
            log.warning("base64 文件删除失败 %s: %s", path, e)


def clean_expired(ttl: float) -> int:
    """清理超过 TTL 秒的过期 base64 缓存文件，返回删除数。"""
    d = os.path.abspath(config.IF_BASE64_DIR)
    if not os.path.isdir(d):
        return 0
    now = time.time()
    deleted = 0
    for fname in os.listdir(d):
        fpath = os.path.join(d, fname)
        try:
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > ttl:
                os.unlink(fpath)
                deleted += 1
        except OSError as e:
            log.warning("base64 过期文件清理失败 %s: %s", fpath, e)
    if deleted:
        log.info("base64 文件清理: 删除 %d 个过期文件", deleted)
    return deleted


def gc_stats() -> dict:
    """统计 base64 缓存目录的 GC 水位（P3-2 可观测闭环）。

    按 mtime 区分：
    - hot：mtime 在 TTL 内（未过期，视为"热"数据）
    - cold：mtime 超过 TTL（待清理，视为"冷"数据）

    返回字段：
    total_files / total_gb / hot_files / hot_gb / cold_files / cold_gb /
    quota_gb / usage_pct / pending_cleanup_count / pending_cleanup_gb
    """
    d = os.path.abspath(config.IF_BASE64_DIR)
    ttl = config.IF_BASE64_FILE_TTL
    quota_gb = config.IF_IMG_MAX_GB
    total_files = hot_files = cold_files = 0
    total_bytes = hot_bytes = cold_bytes = 0
    if os.path.isdir(d):
        now = time.time()
        try:
            names = os.listdir(d)
        except OSError:
            names = []  # 目录存在但不可读（权限/瞬时错误）→ 视为空，避免 /v1/stats 500
        for fname in names:
            fpath = os.path.join(d, fname)
            try:
                if not os.path.isfile(fpath):
                    continue
                size = os.path.getsize(fpath)
                total_files += 1
                total_bytes += size
                if now - os.path.getmtime(fpath) > ttl:
                    cold_files += 1
                    cold_bytes += size
                else:
                    hot_files += 1
                    hot_bytes += size
            except OSError:
                continue
    _gib = 1024**3
    usage_pct = (total_bytes / (quota_gb * _gib) * 100) if quota_gb > 0 else 0.0
    return {
        "total_files": total_files,
        "total_gb": total_bytes / _gib,
        "hot_files": hot_files,
        "hot_gb": hot_bytes / _gib,
        "cold_files": cold_files,
        "cold_gb": cold_bytes / _gib,
        "quota_gb": quota_gb,
        "usage_pct": usage_pct,
        "pending_cleanup_count": cold_files,
        "pending_cleanup_gb": cold_bytes / _gib,
    }


# ── S-14: 配额保护 ──────────────────────────────────


def dir_size_gb(directory: str) -> float:
    """递归统计目录文件总体积（GB），目录不存在返回 0.0。"""
    d = os.path.abspath(directory)
    if not os.path.isdir(d):
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(d):
        for fname in files:
            try:
                total += os.path.getsize(os.path.join(root, fname))
            except OSError:
                continue
    return total / (1024**3)


def list_oldest_files(directory: str, n: int | None = None) -> list[str]:
    """按 mtime 升序（旧→新）返回目录内普通文件绝对路径列表。

    n 为 None 返回全部；目录不存在返回空列表。
    """
    d = os.path.abspath(directory)
    if not os.path.isdir(d):
        return []
    files = []
    for root, _dirs, fnames in os.walk(d):
        for fname in fnames:
            fpath = os.path.join(root, fname)
            try:
                files.append((os.path.getmtime(fpath), fpath))
            except OSError:
                continue
    files.sort(key=lambda t: t[0])
    paths = [fpath for _mtime, fpath in files]
    if n is not None:
        return paths[: max(0, n)]
    return paths


def enforce_quota(directory: str, max_gb: float, audit_fn=None) -> int:
    """配额保护：目录超过 max_gb 上限时，按 mtime 从旧到新删除文件直至 ≤80% 上限。

    audit_fn(path: str, detail: str) 可选回调（生产由 main 传入 audit_log.record）。
    只删文件不删 DB 引用（file:// 路径失效时 _row_to_dict 返回 None，已容忍）。
    返回删除文件数。
    """
    d = os.path.abspath(directory)
    if max_gb <= 0 or not os.path.isdir(d):
        return 0
    size = dir_size_gb(d)
    target_gb = max_gb * 0.8
    if size <= target_gb:
        return 0
    deleted = 0
    freed = 0.0
    for fpath in list_oldest_files(d):
        try:
            fsize_gb = os.path.getsize(fpath) / (1024**3)
            os.unlink(fpath)
            freed += fsize_gb
            deleted += 1
            if audit_fn is not None:
                try:
                    audit_fn(fpath, f"配额 {max_gb}GB 超限（当前 {size:.2f}GB），删除至 {target_gb}GB")
                except Exception:  # 审计回调失败不阻断清理
                    log.warning("base64 配额审计写入失败 %s", fpath)
        except OSError as e:
            log.warning("base64 配额清理失败 %s: %s", fpath, e)
            continue
        if size - freed <= target_gb:
            break
    if deleted:
        log.info("base64 配额保护: 删除 %d 个文件（%s 超过 %.1fGB 上限）", deleted, config.IF_BASE64_DIR, max_gb)
    return deleted
