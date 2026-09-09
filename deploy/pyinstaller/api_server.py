# -*- coding: utf-8 -*-
"""PyInstaller 后端入口（sidecar uvicorn.exe）。

api/main.py 使用相对导入（from . import config），不能作为 PyInstaller 顶层脚本。
本入口用绝对导入启动同一应用，作为 onefile 的入口脚本。
"""

import os
import sys

# 把仓库根加入 path（onefile 解包目录 _MEIPASS 含 api/ 包）
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.main import app  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("IF_HOST", "127.0.0.1")
    port = int(os.environ.get("IF_PORT", "8100"))
    uvicorn.run(app, host=host, port=port, log_level="info")
