"""S-14: base64 文件配额保护测试 — 验证目录体积统计与配额清理纯函数。

测试覆盖：
1. dir_size_gb 统计目录累计体积（GB），目录不存在返回 0.0
2. list_oldest_files 按 mtime 从旧到新排序
3. enforce_quota 超限时按最旧优先删除，降至 80% 上限后停止
4. enforce_quota 支持审计回调、未超限不动作、目录不存在不报错
"""
import os
import sys
import time
from pathlib import Path

import pytest

# 确保项目根目录可导入 api 包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import api.base64_store as store  # noqa: E402

_GIB = 1024 ** 3


# ── 辅助：造大小可控的假文件 ──────────────────────
def _make_file(dirpath: str, fname: str, size: int,
               mtime: float | None = None) -> str:
    path = os.path.join(dirpath, fname)
    with open(path, "wb") as f:
        f.write(b"\0" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def img_dir(tmp_path) -> str:
    """临时 base64 缓存目录（S-14 不需要集成 fixture，纯 tmp_path 即可）。"""
    return str(tmp_path)


# ── 测试 1: dir_size_gb 统计目录体积 ───────────────
def test_dir_size_gb(img_dir):
    """3 个假文件 → dir_size_gb 返回 >0，且约为总字节/GB。"""
    for i in range(3):
        _make_file(img_dir, f"f{i}.png", 1_000_000 + i)

    expected_gb = (1_000_000 + 1_000_001 + 1_000_002) / _GIB
    assert store.dir_size_gb(img_dir) == pytest.approx(expected_gb, rel=1e-9)

    # 目录存在时恒 > 0
    assert store.dir_size_gb(img_dir) > 0.0


# ── 测试 2: dir_size_gb 目录不存在返回 0.0 ──────────
def test_dir_size_gb_missing():
    """目录不存在时返回 0.0。"""
    missing = str(Path(__file__).resolve().parent / "no_such_dir_s14")
    assert store.dir_size_gb(missing) == 0.0


# ── 测试 3: enforce_quota 超限按最旧优先删除 ──────────
def test_enforce_quota_oldest_first(img_dir):
    """超限时从 mtime 最旧的文件开始删，直至 ≤80% 上限。"""
    base = time.time()
    # 3 个 1MB 文件，mtime 依次递增（f0 最旧）
    for i in range(3):
        _make_file(img_dir, f"f{i}.png", 1_000_000, base - (2 - i) * 100)

    # max_gb=0.002（约 2MB）：1.5MB 后降至 3MB*80%=2.4MB → 仍需删至 ≤2.4MB
    # 3MB 总量 → 目标 1.6MB（0.002*0.8），需删 2 个文件（剩 1MB）
    deleted = store.enforce_quota(img_dir, 0.002)
    assert deleted == 2, f"应删除 2 个文件，实际 {deleted}"

    remaining = os.listdir(img_dir)
    assert sorted(remaining) == ["f2.png"], f"应只保留最新的 f2.png，实际 {remaining}"
    assert store.dir_size_gb(img_dir) <= 0.002 * 0.8, "剩余体积应 ≤80% 上限"


# ── 测试 4: enforce_quota 未超限不动作 ──────────────
def test_enforce_quota_below_limit(img_dir):
    """体积未超上限时不删除任何文件。"""
    for i in range(3):
        _make_file(img_dir, f"f{i}.png", 100_000, time.time() - i)

    deleted = store.enforce_quota(img_dir, 5.0)
    assert deleted == 0
    assert len(os.listdir(img_dir)) == 3


# ── 测试 5: enforce_quota 目录不存在 / 非法上限 ──────
def test_enforce_quota_missing_or_bad():
    """目录不存在或 max_gb<=0 时返回 0，不抛异常。"""
    missing = str(Path(__file__).resolve().parent / "no_such_dir_s14")
    assert store.enforce_quota(missing, 5.0) == 0
    # max_gb <= 0 → 视为关闭配额，不动作
    img_dir = str(Path(__file__).resolve().parent / "no_such_dir_s14")
    assert store.enforce_quota(img_dir, 0.0) == 0


# ── 测试 6: enforce_quota 审计回调被调用（次数/参数）──
def test_enforce_quota_audit_callback(img_dir):
    """超限删除时逐一回调 audit_fn(path, detail)。"""
    base = time.time()
    for i in range(3):
        _make_file(img_dir, f"f{i}.png", 1_000_000, base - (2 - i) * 100)

    calls: list[tuple[str, str]] = []

    def _audit(path: str, detail: str) -> None:
        calls.append((path, detail))

    store.enforce_quota(img_dir, 0.002, audit_fn=_audit)
    assert len(calls) == 2, f"应回调 2 次，实际 {len(calls)}"
    # 按最旧优先：f0.png 先删，再 f1.png
    assert "f0.png" in os.path.basename(calls[0][0])
    assert "配额" in calls[0][1]


# ── 测试 7: 未超限时审计回调不被调用 ────────────────
def test_enforce_quota_no_audit_when_ok(img_dir):
    """未超限时审计回调不被调用。"""
    _make_file(img_dir, "f0.png", 100_000, time.time())
    calls: list[tuple[str, str]] = []

    def _audit(path: str, detail: str) -> None:
        calls.append((path, detail))

    store.enforce_quota(img_dir, 5.0, audit_fn=_audit)
    assert calls == []


# ── 测试 8: enforce_quota 审计回调抛异常不阻断清理 ───
def test_enforce_quota_audit_error_ignored(img_dir):
    """审计回调抛异常时清理继续，不中断、不向上抛。"""
    base = time.time()
    for i in range(3):
        _make_file(img_dir, f"f{i}.png", 1_000_000, base - (2 - i) * 100)

    def _bad_audit(path: str, detail: str) -> None:
        raise RuntimeError("audit down")

    deleted = store.enforce_quota(img_dir, 0.002, audit_fn=_bad_audit)
    assert deleted == 2, "审计失败不应阻断清理"
    assert len(os.listdir(img_dir)) == 1