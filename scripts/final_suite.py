"""v3.1.0 全量回归 + 覆盖率基线（终局验证阶段）。

执行：python scripts/final_suite.py [--integration]
环境：Windows；先清残留 python 再跑，避免端口/锁竞争假卡死。
P3-4: 覆盖率门禁从 0 对齐到 70（与 CI 一致），本地不达标即失败。
"""

import subprocess
import sys

ARGS = ["python", "-m", "pytest", "tests/", "-q", "--no-header", "-p", "no:cacheprovider"]
ARGS += ["--cov=api", "--cov-report=term", "--cov-fail-under=80"]
if "--integration" not in sys.argv:
    ARGS += ["--ignore=tests/integration", "--ignore=tests/chaos", "--ignore=tests/performance"]

print(" ".join(ARGS))
r = subprocess.run(ARGS)
sys.exit(r.returncode)
