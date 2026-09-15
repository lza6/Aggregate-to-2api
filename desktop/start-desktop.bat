@echo off
REM 听风AI 桌面版 - 一键启动器（无 Rust 环境也能跑完整功能）
REM 用法: desktop\start-desktop.bat [mock|real] [no-solver]
REM   mock      后端走 IF_MOCK_UPSTREAM=1（默认，零上游消耗）
REM   real      后端走真实上游（IF_MOCK_UPSTREAM=0）
REM   no-solver 不拉起 cf_solver（仅 mock 模式建议带）

setlocal enabledelayedexpansion
set ROOT=%~dp0..
set MODE=%1
set EXTRA=%2

REM -- 1. 环境检查 --
set PYEXE=
if exist %ROOT%\.venv\Scripts\python.exe set PYEXE=%ROOT%\.venv\Scripts\python.exe
if not defined PYEXE (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set PYEXE=py -3.11
)
if not defined PYEXE (
    where.exe python >nul 2>&1
    if not errorlevel 1 set PYEXE=python
)
if not defined PYEXE (
    echo [desktop] [ERROR] Python 3.11+ not found - check .venv, py launcher, PATH
    pause
    exit /b 1
)
echo [desktop] interpreter: !PYEXE!
if not exist "%ROOT%\frontend\dist\index.html" (
    echo [desktop] frontend\dist 不存在 —— 正在构建前端（首次约 30s）...
    pushd "%ROOT%\frontend"
    call npm install --no-audit --no-fund 2>nul
    call npm run build
    if errorlevel 1 (
        echo [desktop] [错误] 前端构建失败，请检查 node/npm 是否可用
        popd
        pause
        exit /b 1
    )
    popd
)

REM -- 2. 拉起 cf_solver（端口 8001，除非 no-solver）--
if not "%EXTRA%"=="no-solver" (
    netstat -ano 2>nul | findstr ":8001 " | findstr "LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [desktop] 启动 cf_solver @ :8001...
        start /b "" !PYEXE! "%ROOT%\deploy\cf_solver\boterdrop_wrapper.py" >nul 2>&1
        timeout /t 2 /nobreak >nul
    ) else (
        echo [desktop] cf_solver :8001 已在运行，跳过
    )
)

REM -- 3. 拉起后端（端口 8100）--
netstat -ano 2>nul | findstr ":8100 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [desktop] 启动后端 api.main @ :8100 ...
    REM 写临时 launcher（规避 start cmd /c 引号嵌套断裂，dry6 已验证）
    (echo @echo off
    echo cd /d %ROOT%
    echo set IF_MOCK_UPSTREAM=1
    echo set IF_CF_SOLVER_URL=http://127.0.0.1:8001
    echo !PYEXE! -m uvicorn api.main:app --host 127.0.0.1 --port 8100
    ) > "%TEMP%\tingfeng-backend-launcher.bat"
    start "tingfeng-backend" cmd /c "%TEMP%\tingfeng-backend-launcher.bat"
    timeout /t 2 /nobreak >nul
) else (
    echo [desktop] 后端 :8100 已在运行，跳过
)

REM -- 4. 健康探测（等 /v1/healthz 就绪，最多 15s）--
set READY=0
for /l %%i in (1,1,15) do (
    if "!READY!"=="0" (
        curl -s -o nul http://127.0.0.1:8100/v1/healthz 2>nul
        if not errorlevel 1 (
            set READY=1
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)
if "%READY%"=="1" (
    echo [desktop] 后端就绪 [OK]
) else (
    echo [desktop] [警告] /v1/healthz 15s 内未就绪（可能仍在启动，页面会显示"后端启动中"）
)

REM -- 5. 打开浏览器工作台（等价桌面 UI；有 Tauri 环境时建议用 npm run dev）--
echo [desktop] 打开工作台 http://127.0.0.1:8100/admin/ ...
start http://127.0.0.1:8100/admin/
echo [desktop] 完成。关闭方式：关闭 tingfeng-backend 窗口（按 pid 终止，不留孤儿）
endlocal
