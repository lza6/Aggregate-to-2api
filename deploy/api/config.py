"""imagefree_api 配置。全部可用环境变量覆盖，便于部署。"""
import os


# ── imagefree 目标站点 ────────────────────────────────
BASE_URL = os.getenv("IF_BASE_URL", "https://imagefree.net")
SITEKEY = os.getenv("IF_SITEKEY", "0x4AAAAAACE-XLGoQUckKKm_")

# ── CF solver 子服务（复用 GPT 项目的 cf_solver，端口 8001）──
CF_SOLVER_URL = os.getenv("IF_CF_SOLVER_URL", "http://127.0.0.1:8001")

# ── 本服务监听 ───────────────────────────────────────
HOST = os.getenv("IF_HOST", "127.0.0.1")
PORT = int(os.getenv("IF_PORT", "8100"))

# ── 网络 ─────────────────────────────────────────────
# 默认读环境变量代理（本机 Clash: 127.0.0.1:10808）；显式 IF_PROXY 可覆盖
PROXY = os.getenv("IF_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or None

# HTTP 连接池参数（IMP-27）：httpx.AsyncClient 的 Limits 配置
IF_HTTP_MAX_CONNECTIONS = int(os.getenv("IF_HTTP_MAX_CONNECTIONS", "100"))
IF_HTTP_KEEPALIVE = int(os.getenv("IF_HTTP_KEEPALIVE", "20"))

# 上游并发控制（IMP-27）：对 imagefree.net 的最大并发请求数
IF_UPSTREAM_MAX_INFLIGHT = int(os.getenv("IF_UPSTREAM_MAX_INFLIGHT", "30"))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

# ── 超时 / 轮询（秒）─────────────────────────────────
TURNSTILE_TIMEOUT = int(os.getenv("IF_TURNSTILE_TIMEOUT", "90"))
# cf_solver 结果轮询间隔（默认 2s；mock/CI 环境求解极快时可调小避免轮询成为吞吐瓶颈）
TURNSTILE_POLL_INTERVAL = float(os.getenv("IF_TURNSTILE_POLL_INTERVAL", "2.0"))

GENERATE_TIMEOUT = int(os.getenv("IF_GENERATE_TIMEOUT", "300"))
GENERATE_POLL_INTERVAL = 2.0

# 图生图（ai-photo-editor）上游排队较慢，且实测部分任务在上游全局队列可卡 20 分钟以上。
# 轮询超时必须给足，避免我们中途放弃 → 孤儿上游任务永久占用同 IP 并发槽（下次提交必 429）。
EDIT_TIMEOUT = int(os.getenv("IF_EDIT_TIMEOUT", "3600"))
# 生成任务硬超时兜底（IMP-04）：杜绝 worker 被永不终态的上游永久挂住。
# 图生图走 _run_edit_job 独立分支，不受此值影响。
TASK_HARD_TIMEOUT = int(os.getenv("IF_TASK_HARD_TIMEOUT", "480"))
# 图生图上游硬并发 = 1（同会话只能 1 个编辑任务在途，实测确认）。
# 新编辑请求在排队等待前一个任务完成的最长时间（秒），超时返回 429。
EDIT_CONCURRENCY_WAIT = int(os.getenv("IF_EDIT_CONCURRENCY_WAIT", "60"))
# 跨进程图生图互斥：上游并发=1 是全局硬限制，跨进程/多实例也必须串行。
# 用 O_EXCL 文件锁（DB 同目录卷内，跨进程可见）实现；进程崩溃靠 PID+超时 stale 检测自动清理。
EDIT_MUTEX_ENABLED = os.getenv("IF_EDIT_MUTEX_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
# 锁文件最长存活（秒）：持有进程崩溃后靠超时兜底清理（图生图单任务最多 ~10 分钟）
EDIT_LOCK_MAX_AGE = int(os.getenv("IF_EDIT_LOCK_MAX_AGE", "1500"))
# 上游并发槽瞬态占用重试：孤儿上游任务（如进程中断遗留）会让同 IP 的编辑槽暂时被占
# （429 "task in progress"），实测自愈时长可达数分钟到 ~10 分钟。遇到即等待并重试，
# 预算默认 30 次 × 20s = 10 分钟，尽量骑过自愈窗口，避免任务直接失败。
EDIT_RETRY_MAX = int(os.getenv("IF_EDIT_RETRY_MAX", "30"))
EDIT_RETRY_INTERVAL = int(os.getenv("IF_EDIT_RETRY_INTERVAL", "20"))

# ── 图生图住宅代理池（绕过上游并发=1）──────────────
# 上游并发限制基于出口 IP：同 IP 同时只能 1 个编辑任务在途（实测 "task in progress"）。
# 用「住宅代理池」给每个图生图任务分配独立出口 IP（token 与提交绑定同一代理），
# 不同 IP 之间即可并行 → 绕过并发=1。
# 注意：免费数据中心代理会被 Cloudflare WAF 403（实测），必须用住宅代理（如 kookeey）。
# 内存约束：cf_solver 每代理一个浏览器上下文 ≈ 0.5-1GB，并发数受服务器内存限制。
#   EDIT_PROXY_FILE     代理列表文件（每行一个 http://user:pass@host:port，kookeey 粘性会话也可）
#   EDIT_PROXY_PARALLEL 最大并行代理会话数（默认 1 = 直连单并发；>1 需内存支撑 + 住宅代理）
EDIT_PROXY_FILE = os.getenv("IF_EDIT_PROXY_FILE", "")
EDIT_PROXY_PARALLEL = int(os.getenv("IF_EDIT_PROXY_PARALLEL", "1"))
# IMP-19: 图生图代理池并行上限：同一时刻最多允许多少个代理会话在途（sem_inflight 信号量）
IF_EDIT_PROXY_MAX_INFLIGHT = int(os.getenv("IF_EDIT_PROXY_MAX_INFLIGHT", "2"))

# 图片下载尺寸上限（4MB，防内存打爆）
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# 图生图代理 token 池：每代理（出口 IP）一个独立小池，目标水位 = 1
# （per-proxy 串行，同时只有 1 个任务在途，维持 1 个新鲜 token 即可；token 与代理 IP 绑定）。
# 代理池空闲超过 PROXY_POOL_IDLE_TTL 秒后自动回收（停止预取、释放资源）。
EDIT_PROXY_POOL_SIZE = int(os.getenv("IF_EDIT_PROXY_POOL_SIZE", "1"))
EDIT_PROXY_POOL_IDLE_TTL = int(os.getenv("IF_EDIT_PROXY_POOL_IDLE_TTL", "180"))

# ── 校验 ─────────────────────────────────────────────
ASPECT_RATIOS = {
    "1:1": "1024x1024",
    "3:4": "768x1024",
    "4:3": "1024x768",
    "9:16": "576x1024",
    "16:9": "1024x576",
}

MAX_PROMPT_LEN = 2000

# ── 模型 / 风格预设 ────────────────────────────────
# 诚实声明：上游 imagefree.net 是纯文生图（无 model 参数，已逆向确认），
# 这里的 "模型" = 服务端风格预设（prompt 前缀注入），非上游真实多模型。
# 调用方可传 model 参数指定风格；default 不注入任何前缀（保持原 prompt）。
# prefix 拼到 prompt 前，适用于 txt2img（/v1/generate）；img2img 也支持（applies_to 含 edit）。
MODEL_PRESETS: dict[str, dict] = {
    "default": {
        "name": "默认",
        "description": "不注入任何风格，原样提交提示词",
        "prefix": "",
        "applies_to": ["txt2img", "img2img"],
    },
    "anime": {
        "name": "动漫",
        "description": "日系动漫插画风格，高完成度线稿与上色",
        "prefix": "anime style, high quality anime illustration, vibrant colors, detailed lineart, ",
        "applies_to": ["txt2img"],
    },
    "realistic": {
        "name": "写实摄影",
        "description": "超写实照片质感，高细节、电影级光影",
        "prefix": "photorealistic, ultra detailed, 8k, cinematic lighting, sharp focus, ",
        "applies_to": ["txt2img"],
    },
    "watercolor": {
        "name": "水彩",
        "description": "水彩画风格，柔和晕染、通透层次",
        "prefix": "watercolor painting style, soft washes, delicate brushwork, translucent layers, ",
        "applies_to": ["txt2img", "img2img"],
    },
    "ink": {
        "name": "水墨",
        "description": "中国传统水墨画风，留白、写意、淡雅",
        "prefix": "traditional chinese ink wash painting style, minimalist, elegant negative space, ",
        "applies_to": ["txt2img"],
    },
    "cyberpunk": {
        "name": "赛博朋克",
        "description": "赛博朋克霓虹风格，未来都市、强对比色调",
        "prefix": "cyberpunk neon style, futuristic city, neon glow, high contrast, ",
        "applies_to": ["txt2img", "img2img"],
    },
}
DEFAULT_MODEL = os.getenv("IF_DEFAULT_MODEL", "default")


def apply_model(prompt: str, model: str) -> str:
    """模型风格预设 → prompt 前缀注入（default 不加前缀）。供 worker/main 共用。"""
    prefix = MODEL_PRESETS.get(model, {}).get("prefix", "")
    return prefix + prompt if prefix else prompt

# ── 用量统计持久化（容器内 /app/data，compose 挂载宿主机）──
STATS_FILE = os.getenv("IF_STATS_FILE", "data/stats.json")
DB_FILE = os.getenv("IF_DB_FILE", "data/imagefree.db")

# ── 持久化队列（IMP-29：重启后未消费任务可续跑）───────────
IF_PERSISTENT_QUEUE_ENABLED = os.getenv("IF_PERSISTENT_QUEUE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
IF_PERSISTENT_QUEUE_DB = os.getenv("IF_PERSISTENT_QUEUE_DB", "data/queue.db")

# ── 并发 / 队列（高并发入口设计）──────────────────────
# 有界队列上限：超过则返回 429（保护系统不被打崩）。50 RPS × 单请求 < 1ms 入队。
MAX_QUEUE = int(os.getenv("IF_MAX_QUEUE", "2000"))
# 优先级队列各级独立上限（IMP-01）：priority=0 admin, 1 paid, 2 normal
ADMIN_QUEUE_MAX = int(os.getenv("IF_ADMIN_QUEUE_MAX", "200"))
HIGH_QUEUE_MAX = int(os.getenv("IF_HIGH_QUEUE_MAX", "500"))
NORMAL_QUEUE_MAX = int(os.getenv("IF_NORMAL_QUEUE_MAX", "1500"))
# 生成 worker 并发数：同时多少个生成在途（imagefree 提交/轮询是 HTTP 异步，可并发）
WORKERS = int(os.getenv("IF_WORKERS", "10"))
# ── Worker 自动伸缩（IMP-03）─────────────────────────
# 开关：默认 "0" 关闭，兼容旧行为（静态 worker 数）
IF_WORKER_AUTO = os.getenv("IF_WORKER_AUTO", "0").strip().lower() in {"1", "true", "yes", "on"}
# 最小/最大 worker 数
IF_WORKERS_MIN = int(os.getenv("IF_WORKERS_MIN", "4"))
IF_WORKERS_MAX = int(os.getenv("IF_WORKERS_MAX", "16"))
# 扩容阈值：排队超过此值 → 增 worker
IF_WORKER_SCALE_UP_THRESHOLD = int(os.getenv("IF_WORKER_SCALE_UP_THRESHOLD", "200"))
# 缩容阈值：排队低于此值 → 缩 worker
IF_WORKER_SCALE_DOWN_THRESHOLD = int(os.getenv("IF_WORKER_SCALE_DOWN_THRESHOLD", "20"))
# 空闲超时（秒）：worker 空闲超过此值 → 缩 worker
IF_WORKER_IDLE_SECONDS = int(os.getenv("IF_WORKER_IDLE_SECONDS", "90"))

# Turnstile token 预取池大小：后台持续预取，请求不阻塞在求解上。
# 池越大突发时初始并发越高，但 TTL 内未被消费的 token 会过期重解（空转）。
# 默认 6：匹配 10 worker 的常见突发，且 ≤ TTL(90s)/单槽求解(~5s) 的理论上限(~18)，留安全余量。
# 空闲回退：无排队任务时预取只维持 1 个新鲜 token，避免满池空转（见 worker.py）。
TOKEN_POOL_SIZE = int(os.getenv("IF_TOKEN_POOL_SIZE", "6"))
# Turnstile token 最长存活（秒）：CF token 约 2 分钟过期，池满即停时旧 token 会失效。
# 小于上游过期时间留安全余量；取用前检查，过期即丢弃。H1
TOKEN_TTL = int(os.getenv("IF_TOKEN_TTL", "90"))
# 同步接口最长等待（秒）：超过返回排队状态，建议用 async 模式
SYNC_TIMEOUT = int(os.getenv("IF_SYNC_TIMEOUT", "300"))
# 生成失败时最多尝试次数（含首次）：>1 时若 token 被上游拒绝会自动换新 token 重试
GENERATE_MAX_ATTEMPTS = int(os.getenv("IF_GENERATE_MAX_ATTEMPTS", "2"))
# 文生图 transient 错误重试次数（IMP-05）：含首次尝试，超过进入 DLQ
IF_TXT_RETRY_MAX = int(os.getenv("IF_TXT_RETRY_MAX", "3"))
# 文生图重试指数退避基值（秒）（IMP-05）
IF_TXT_RETRY_BACKOFF_BASE = int(os.getenv("IF_TXT_RETRY_BACKOFF_BASE", "5"))
# 取 token 等待超时（秒）：token 池空时等待预取的最长时间，超时报错而非无限阻塞
TOKEN_WAIT_TIMEOUT = int(os.getenv("IF_TOKEN_WAIT_TIMEOUT", "30"))
# 画廊返回条数
GALLERY_LIMIT = int(os.getenv("IF_GALLERY_LIMIT", "50"))

# ── LRU 缓存（IMP-28：首页/画廊/统计降 DB 读压）───────
IF_LRU_CACHE_SIZE = int(os.getenv("IF_LRU_CACHE_SIZE", "128"))
IF_LRU_CACHE_TTL = int(os.getenv("IF_LRU_CACHE_TTL", "5"))

# ── 可观测性 / 治理（M5/M6/M7）───────────────────────
# base64 文件缓存目录（IMP-26）：将 image_base64 从 SQLite 全量存储改为本地文件缓存
IF_BASE64_DIR = os.getenv("IF_BASE64_DIR", "data/imgs")
# base64 文件缓存 TTL（秒），默认 1 天
IF_BASE64_FILE_TTL = int(os.getenv("IF_BASE64_FILE_TTL", "86400"))
# healthz 的 cf_solver 探活结果缓存秒数（避免每请求建 TCP 连接探测）
HEALTHZ_CACHE_TTL = int(os.getenv("IF_HEALTHZ_CACHE_TTL", "5"))
# token 池并发预取求解上限：cf_solver 是串行贵资源，用信号量限并发，
# 防多协程打爆求解器。默认 1 = 单协程串行（现状）；>1 需 cf_solver 多浏览器槽支撑。
TOKEN_PREFETCH_CONCURRENCY = int(os.getenv("IF_TOKEN_PREFETCH_CONCURRENCY", "1"))
# ── token 预取延迟自适应（IMP-02）────────────────────
# 求解成功后预取等待延迟（秒）。0 = 使用 EMA 自适应延迟；>0 = 固定值，兼容旧行为。
IF_PREFETCH_AFTER_SOLVE_DELAY = float(os.getenv("IF_PREFETCH_AFTER_SOLVE_DELAY", "0"))
# EMA 平滑系数（alpha）：越小越平滑，越大越灵敏。0.3 = 历史 70% + 当前 30%。
IF_PREFETCH_EMA_ALPHA = float(os.getenv("IF_PREFETCH_EMA_ALPHA", "0.3"))

# ── solver 熔断 / 健康指标 ──────────────────────────
# 连续求解失败达到阈值 → 熔断 OPEN：暂停所有新求解，worker 取 token 立即失败（不再 30s 干等）。
SOLVE_CIRCUIT_THRESHOLD = int(os.getenv("IF_SOLVE_CIRCUIT_THRESHOLD", "5"))
# 熔断 OPEN 后每间隔放行一个探测求解（half-open），成功即恢复。
SOLVE_CIRCUIT_PROBE_SECONDS = int(os.getenv("IF_SOLVE_CIRCUIT_PROBE_SECONDS", "30"))
# 求解成功率/平均耗时统计的滑动窗口（秒）。
SOLVE_STATS_WINDOW_SECONDS = int(os.getenv("IF_SOLVE_STATS_WINDOW_SECONDS", "300"))

# ── 多提供商 / 号池 / 邮箱池 / 代理池 ───────────────
# 住宅代理池文件（每行 http://user:pass@host:port，kookeey 格式）：aifreeforever 每 IP 每日限额用
PROXY_FILE = os.getenv("IF_PROXY_FILE", "")
# 免费代理池开关（免费源抓取：proxyscrape/geonode/proxy-list.download/proxifly-github）
FREE_PROXY_ENABLED = os.getenv("IF_FREE_PROXY", "0").strip().lower() in {"1", "true", "yes", "on"}
# 免费代理刷新周期（分钟）
FREE_PROXY_REFRESH_MIN = int(os.getenv("IF_FREE_PROXY_REFRESH_MIN", "30"))
# 代理冷却秒数（429 触发）
PROXY_COOLDOWN_SECONDS = int(os.getenv("IF_PROXY_COOLDOWN_SECONDS", "120"))
# 代理池每 IP 每日最多使用次数（aifreeforever 建议 1，避免递增冷却）
IF_PROXY_MAX_USE_PER_DAY = int(os.getenv("IF_PROXY_MAX_USE_PER_DAY", "1"))
# 递增冷却秒数映射（逗号分隔，第 i 个值对应第 i 次使用后的冷却秒数）
# 默认 "0,30,90,300,900" → 第 1 次 0s, 第 2 次 30s, 第 3 次 90s, 第 4 次 300s, 第 5 次+ 900s
IF_PROXY_USE_COOLDOWN_MAP = os.getenv("IF_PROXY_USE_COOLDOWN_MAP", "0,30,90,300,900")
# 号池 DB / 邮箱注册记录 DB
ACCOUNT_DB_FILE = os.getenv("IF_ACCOUNT_DB_FILE", "data/account_pool.db")
EMAIL_DB_FILE = os.getenv("IF_EMAIL_DB_FILE", "data/email_registry.db")
# minimaxh3 / nanobanana 号池目标账号数
MINIMAXH3_ACCOUNT_TARGET = int(os.getenv("IF_MINIMAXH3_ACCOUNT_TARGET", "500"))
NANOBANANA_ACCOUNT_TARGET = int(os.getenv("IF_NANOBANANA_ACCOUNT_TARGET", "500"))
# 自动注册/签到开关（测试可关）
ACCOUNT_AUTO = os.getenv("IF_ACCOUNT_AUTO", "1").strip().lower() in {"1", "true", "yes", "on"}
# DB 请求记录保留天数：超期清理（DELETE + WAL checkpoint + VACUUM），防表无限增长。
# 默认 365 天以保留近 12 个月统计（monthly 跨 12 月）。
DB_RETENTION_DAYS = int(os.getenv("IF_DB_RETENTION_DAYS", "365"))
# DB 清理周期（秒）：默认 6 小时一次 + 启动时各一次
DB_CLEANUP_INTERVAL = int(os.getenv("IF_DB_CLEANUP_INTERVAL", "21600"))

# ── DB 批量写入（IMP-25）─────────────────────────────
# 写缓冲 + 批量提交：将 batch_window 秒内的写操作合并为一次 commit，
# 减少 50 RPS 下每任务 2 次 commit 的频繁提交压力。
IF_DB_BATCH_ENABLED = os.getenv("IF_DB_BATCH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
IF_DB_BATCH_WINDOW = float(os.getenv("IF_DB_BATCH_WINDOW", "0.2"))

# ── DB 连接池（IMP-20：多连接支持）────────────────────────
# 写连接池大小：>1 时启用多连接模式（round-robin 分配写连接）；
# =1 时退化为单连接模式（原行为）。
IF_DB_POOL_SIZE = int(os.getenv("IF_DB_POOL_SIZE", "3"))
# 获取连接超时秒数（sqlite3.connect timeout 参数）
IF_DB_POOL_TIMEOUT = int(os.getenv("IF_DB_POOL_TIMEOUT", "5"))

# ── provider 降级/熔断（IMP-18）───────────────────────────
# 连续 ProviderRateLimited 次数达到阈值 → 降级该 provider
IF_PROVIDER_DEGRADE_THRESHOLD = int(os.getenv("IF_PROVIDER_DEGRADE_THRESHOLD", "3"))
# 降级恢复探测间隔（秒）：每间隔尝试恢复一个降级 provider
IF_PROVIDER_RECOVER_INTERVAL = int(os.getenv("IF_PROVIDER_RECOVER_INTERVAL", "300"))

# ── 幂等提交（IMP-06）───────────────────────────────────
IF_IDEMPOTENCY_ENABLED = os.getenv("IF_IDEMPOTENCY_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
IF_IDEMPOTENCY_TTL = int(os.getenv("IF_IDEMPOTENCY_TTL", "900"))

# ── 死信队列（IMP-21）───────────────────────────────────
IF_DLQ_ENABLED = os.getenv("IF_DLQ_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
IF_DLQ_MAX_RETRIES = int(os.getenv("IF_DLQ_MAX_RETRIES", "3"))

# ── 健康探测（IMP-22）───────────────────────────────────
# 上游健康检查间隔（秒）
IF_HEALTH_CHECK_INTERVAL = int(os.getenv("IF_HEALTH_CHECK_INTERVAL", "60"))
# 上游健康检查开关
IF_HEALTH_CHECK_ENABLED = os.getenv("IF_HEALTH_CHECK_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}

# ── 画廊鉴权（P1）──────────────────────────────────────
# 画廊密码保护。默认空=无密码（兼容旧行为）；非空时 /v1/gallery 需 ?password=xxx 验证
IF_GALLERY_PASSWORD = os.getenv("IF_GALLERY_PASSWORD", "")
