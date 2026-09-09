# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec：把听风AI 后端（uvicorn）打为单文件 sidecar `backend/uvicorn.exe`
# 让桌面版在**任何机器（无需 Python/依赖）**双击即完整运行：
#   - 内含全部 api/ 代码 + 依赖 + 静态资源（frontend/dist + landing/dist）
#   - 运行时在 exe 旁自动展开数据目录 data/（号池/DB/日志）
# 构建：pyinstaller backend.spec --noconfirm

import os
import sys

# spec 由 pyinstaller 执行时无 __file__——用 SPECPATH（PyInstaller 注入）
ROOT = SPECPATH

# ── 收集静态资源（管理面板 + 落地页 dist）───────────────
frontend_dist = os.path.join(ROOT, "..", "..", "frontend", "dist")
landing_dist = os.path.join(ROOT, "..", "..", "landing", "dist")
skills_dir = os.path.join(ROOT, "..", "..", "api", "skills")
prompts_dir = os.path.join(ROOT, "..", "..", "api", "prompts")

datas = []
for src, dst in [
    (frontend_dist, "frontend/dist"),
    (landing_dist, "landing/dist"),
    (skills_dir, "api/skills"),
    (prompts_dir, "api/prompts"),
]:
    if os.path.isdir(src):
        datas.append((src, dst))

a = Analysis(
    [os.path.join(ROOT, "api_server.py")],
    pathex=[ROOT, os.path.join(ROOT, "..", "..")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # 运行时动态 import 的模块（懒加载/字符串 import），显式收集避免漏
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "anyio._backends._asyncio",
        "aiosqlite",
        "multipart",
        "python_multipart",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "playwright"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="uvicorn",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 保留控制台方便排障（生产可改 False）
    icon=os.path.join(ROOT, "..", "..", "desktop", "src-tauri", "icons", "icon.ico"),
)
