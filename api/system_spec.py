import multiprocessing
import os


def _detect_cpu_count() -> int:
    """检测可用 CPU 核心数，容错返回 2。"""
    try:
        return multiprocessing.cpu_count()
    except (NotImplementedError, OSError):
        return 2


def _detect_memory_mb() -> int:
    """检测总内存（MB），失败返回 2048（2GB）。"""
    try:
        import psutil

        return int(psutil.virtual_memory().total / (1024 * 1024))
    except ImportError:
        # 回退：通过 /proc/meminfo（Linux）
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) // 1024
        except OSError:
            pass
        return 2048


def _detect_disk_gb(path: str = ".") -> tuple[float, float, float]:
    """检测磁盘总容量/已用/可用（GB），失败返回 (0,0,0)。"""
    try:
        import psutil

        d = psutil.disk_usage(path)
        return (d.total / 1e9, d.used / 1e9, d.free / 1e9)
    except ImportError:
        try:
            s = os.statvfs(path)
            total = s.f_frsize * s.f_blocks / 1e9
            free = s.f_frsize * s.f_bavail / 1e9
            used = total - free
            return (total, used, free)
        except (AttributeError, OSError):
            pass
        return (0, 0, 0)


# ── 服务器规格检测 ─────────────────────────────────
CPU_COUNT = _detect_cpu_count()
MEMORY_MB = _detect_memory_mb()

# ── 自适应并发参数 ─────────────────────────────────
# 核心原则：worker 数 = cpu_count * 2（IO 密集型任务，多线程有利）
# 上游并发上限 = cpu_count * 8（网络 IO 为主，可更高并发）
# Token 池水位 = max(2, cpu_count * 2)
# 队列上限 = max(1000, cpu_count * 500)

ADAPTIVE_WORKERS = max(2, CPU_COUNT * 2)
ADAPTIVE_UPSTREAM_INFLIGHT = max(4, CPU_COUNT * 8)
ADAPTIVE_TOKEN_POOL_SIZE = max(2, CPU_COUNT * 2)
ADAPTIVE_MAX_QUEUE = max(500, CPU_COUNT * 500)

# 内存约束：内存 < 2GB 时压缩并发
if MEMORY_MB < 2048:
    ADAPTIVE_WORKERS = min(ADAPTIVE_WORKERS, 4)
    ADAPTIVE_UPSTREAM_INFLIGHT = min(ADAPTIVE_UPSTREAM_INFLIGHT, 12)
    ADAPTIVE_TOKEN_POOL_SIZE = min(ADAPTIVE_TOKEN_POOL_SIZE, 3)
    ADAPTIVE_MAX_QUEUE = min(ADAPTIVE_MAX_QUEUE, 1000)

# 内存 2-4GB 中等压缩
elif MEMORY_MB < 4096:
    ADAPTIVE_WORKERS = min(ADAPTIVE_WORKERS, 8)
    ADAPTIVE_UPSTREAM_INFLIGHT = min(ADAPTIVE_UPSTREAM_INFLIGHT, 24)
    ADAPTIVE_MAX_QUEUE = min(ADAPTIVE_MAX_QUEUE, 2000)

# 内存 >= 8GB 全开
elif MEMORY_MB >= 8192:
    ADAPTIVE_WORKERS = max(ADAPTIVE_WORKERS, 16)
    ADAPTIVE_UPSTREAM_INFLIGHT = max(ADAPTIVE_UPSTREAM_INFLIGHT, 64)
    ADAPTIVE_TOKEN_POOL_SIZE = max(ADAPTIVE_TOKEN_POOL_SIZE, 8)
    ADAPTIVE_MAX_QUEUE = max(ADAPTIVE_MAX_QUEUE, 5000)


def system_spec() -> dict:
    """返回服务器规格摘要（供 /v1/system 端点）。"""
    total_gb, used_gb, free_gb = _detect_disk_gb()
    return {
        "cpu": {
            "cores": CPU_COUNT,
            "model": "auto-detected",
        },
        "memory": {
            "total_mb": MEMORY_MB,
            "total_gb": round(MEMORY_MB / 1024, 1),
        },
        "disk": {
            "total_gb": round(total_gb, 1),
            "used_gb": round(used_gb, 1),
            "free_gb": round(free_gb, 1),
        },
        "adaptive": {
            "workers": ADAPTIVE_WORKERS,
            "upstream_inflight": ADAPTIVE_UPSTREAM_INFLIGHT,
            "token_pool_size": ADAPTIVE_TOKEN_POOL_SIZE,
            "max_queue": ADAPTIVE_MAX_QUEUE,
        },
    }
