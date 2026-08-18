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
        with open(path, "r", encoding="utf-8") as f:
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