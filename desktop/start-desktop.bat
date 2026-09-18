@echo off
REM TingfengAI desktop launcher - run full stack without Rust environment.
REM Usage: desktop\start-desktop.bat [mock|real] [no-solver]
REM   mock       IF_MOCK_UPSTREAM=1 (default), all upstream mocked
REM   real       IF_MOCK_UPSTREAM=0, real upstream calls (paid providers still gated)
REM   no-solver  skip starting cf_solver (mock mode works without it)

setlocal enabledelayedexpansion
set ROOT=%~dp0..
set MODE=%1
set EXTRA=%2
if "%MODE%"=="" set MODE=mock
if /i "%MODE%"=="real" (set IF_MOCK=0) else (set IF_MOCK=1)

REM -- 0. key env passthrough (honor existing values, else defaults) --
if not defined IF_CF_SOLVER_URL set IF_CF_SOLVER_URL=http://127.0.0.1:8001
if not defined IF_PORT set IF_PORT=8100
if not defined IF_HOST set IF_HOST=127.0.0.1

REM -- 1. python interpreter --
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
echo [desktop] interpreter: !PYEXE!  mode: !MODE! (IF_MOCK_UPSTREAM=!IF_MOCK!)

if not exist "%ROOT%\frontend\dist\index.html" (
    echo [desktop] frontend\dist missing, building frontend (first run ~30s)...
    pushd "%ROOT%\frontend"
    call npm install --no-audit --no-fund 2>nul
    call npm run build
    if errorlevel 1 (
        echo [desktop] [ERROR] frontend build failed, check node/npm
        popd
        pause
        exit /b 1
    )
    popd
)

REM -- 2. cf_solver @ :8001 with readiness polling (30 x 2s) --
if not "%EXTRA%"=="no-solver" (
    netstat -ano 2>nul | findstr ":8001 " | findstr "LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [desktop] starting cf_solver @ :8001 ...
        if not exist "%ROOT%\deploy\cf_solver\logs" mkdir "%ROOT%\deploy\cf_solver\logs"
        start /b "" !PYEXE! "%ROOT%\deploy\cf_solver\boterdrop_wrapper.py" > "%ROOT%\deploy\cf_solver\logs\cf_solver.log" 2>&1
        set SOLVER_READY=0
        for /l %%i in (1,1,30) do (
            if "!SOLVER_READY!"=="0" (
                netstat -ano 2>nul | findstr ":8001 " | findstr "LISTENING" >nul 2>&1
                if not errorlevel 1 (
                    set SOLVER_READY=1
                ) else (
                    timeout /t 2 /nobreak >nul
                )
            )
        )
        if "!SOLVER_READY!"=="1" (
            echo [desktop] cf_solver ready @ :8001 [OK]
        ) else (
            echo [desktop] [WARN] cf_solver :8001 not ready within 60s, tail logs:
            for %%f in ("%ROOT%\deploy\cf_solver\logs\*.log") do (
                if exist "%%f" (
                    echo ---- %%~nxf ----
                    powershell -NoProfile -Command "Get-Content -LiteralPath '%%f' -Tail 20"
                )
            )
        )
    ) else (
        echo [desktop] cf_solver :8001 already running, skip
    )
)

REM -- 3. cleanup stale backend windows (title filter + port 8100 double check) --
netstat -ano 2>nul | findstr ":8100 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    for /f "tokens=2 delims=," %%p in ('tasklist /v /fo csv /nh ^| findstr /i "tingfeng-backend"') do (
        set STALE_PID=%%~p
        if defined STALE_PID (
            netstat -ano 2>nul | findstr ":8100 " | findstr "LISTENING" | findstr /r /c:"!STALE_PID!$" >nul 2>&1
            if not errorlevel 1 (
                echo [desktop] killing stale backend PID !STALE_PID! (title + :8100 verified)
                taskkill /pid !STALE_PID! /t /f >nul 2>&1
            )
        )
    )
)

REM -- 4. start backend @ :8100 --
netstat -ano 2>nul | findstr ":8100 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [desktop] starting api.main @ :8100 ...
    (echo @echo off
    echo cd /d %ROOT%
    echo set IF_MOCK_UPSTREAM=%IF_MOCK%
    echo set IF_CF_SOLVER_URL=%IF_CF_SOLVER_URL%
    echo set IF_HOST=%IF_HOST%
    echo set IF_PORT=%IF_PORT%
    echo !PYEXE! -m uvicorn api.main:app --host !IF_HOST! --port !IF_PORT!
    ) > "%TEMP%\tingfeng-backend-launcher.bat"
    start "tingfeng-backend" cmd /c "%TEMP%\tingfeng-backend-launcher.bat"
    timeout /t 2 /nobreak >nul
) else (
    echo [desktop] backend :8100 already running, skip
)

REM -- 5. healthz probe (15 x 1s) with diagnostics on failure --
set READY=0
set LAST_CODE=000
for /l %%i in (1,1,15) do (
    if "!READY!"=="0" (
        curl -s -o nul -w "%%{http_code}" http://127.0.0.1:!IF_PORT!/v1/healthz 2>nul > "%TEMP%\tingfeng-healthz-code.txt"
        set /p LAST_CODE=<"%TEMP%\tingfeng-healthz-code.txt"
        if "!LAST_CODE!"=="200" (
            set READY=1
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)
if "%READY%"=="1" (
    echo [desktop] healthz [OK]
) else (
    echo [desktop] [WARN] /v1/healthz not ready after 15s (last http_code=!LAST_CODE!)
    echo ---- /v1/healthz body ----
    curl -s --max-time 3 http://127.0.0.1:!IF_PORT!/v1/healthz 2>nul
    echo.
    echo ---- launcher content ----
    type "%TEMP%\tingfeng-backend-launcher.bat" 2>nul
)

REM -- 6. open admin console --
echo [desktop] open console http://127.0.0.1:!IF_PORT!/admin/ ...
start http://127.0.0.1:!IF_PORT!/admin/
echo [desktop] done. To stop: close the tingfeng-backend window (or taskkill /im cmd.exe /fi "WINDOWTITLE eq tingfeng-backend")
endlocal