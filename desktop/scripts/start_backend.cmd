@echo off
REM 听风AI 桌面版 - 手动后端启动器（调试用，等价于 Tauri 启动时自动拉起）
REM 用法: desktop\scripts\start_backend.cmd [mock|real] [no-solver]

setlocal
set PORT=8100
set IF_HOST=127.0.0.1
set IF_PORT=%PORT%
set IF_CF_SOLVER_URL=http://127.0.0.1:8001
if "%1"=="real" (set IF_MOCK_UPSTREAM=0) else (set IF_MOCK_UPSTREAM=1)
if "%2"=="no-solver" (set IF_DESKTOP_NO_SOLVER=1)

echo [desktop] 启动 uvicorn backend @ %IF_HOST%:%PORT% (mock=%IF_MOCK_UPSTREAM%)
python -m uvicorn api.main:app --host %IF_HOST% --port %PORT%