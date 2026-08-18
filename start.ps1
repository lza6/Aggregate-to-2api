# ============================================================
#  imagefree_api one-click launcher (Windows)
#  1) start cf_solver (port 8001)
#  2) run imagefree_api (port 8100) in foreground
# ============================================================
$ErrorActionPreference = 'Stop'

# ── 自动检测 Python 虚拟环境 ──────────────────────────
# 优先级：项目 .venv > 父级 .venv > 系统 PATH
$py = $null
$candidates = @(
    Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    Join-Path $PSScriptRoot "..\..\.venv\Scripts\python.exe"
    (Get-Command python -ErrorAction SilentlyContinue).Source
)
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $py = $c; break }
}
if (-not $py) {
    Write-Host "[ERROR] 未找到 Python 解释器。请创建虚拟环境：" -ForegroundColor Red
    Write-Host "        python -m venv .venv" -ForegroundColor Yellow
    Write-Host "        .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# ── cf_solver 路径（自动检测）─────────────────────────
$cfDir = $null
$cfCandidates = @(
    Join-Path $PSScriptRoot "cf_solver"
    Join-Path $PSScriptRoot "..\cf_solver"
    Join-Path $PSScriptRoot "..\GPT自动化注册的项目\cf_solver"
)
foreach ($c in $cfCandidates) {
    if (Test-Path $c) { $cfDir = $c; break }
}
$cfPort = 8001
$apiPort = 8100

function Test-Port($hostName, $port) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect($hostName, $port)
        $c.Close()
        return $true
    } catch { return $false }
}

# ---------- 1. cf_solver ----------
if (Test-Port '127.0.0.1' $cfPort) {
    Write-Host "[cf_solver] 已在端口 $cfPort 运行，跳过。" -ForegroundColor Green
} elseif ($cfDir) {
    Write-Host "[cf_solver] 启动中（端口 $cfPort）..."
    $wrapper = Join-Path $cfDir "boterdrop_wrapper.py"
    if (Test-Path $wrapper) {
        Start-Process -FilePath $py -ArgumentList "boterdrop_wrapper.py" -WorkingDirectory $cfDir -WindowStyle Minimized
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            if (Test-Port '127.0.0.1' $cfPort) { $ready = $true; break }
            Start-Sleep -Seconds 2
        }
        if ($ready) { Write-Host "[cf_solver] 就绪。" -ForegroundColor Green }
        else { Write-Host "[cf_solver] 启动超时（60s），请检查 $cfDir\logs\cf_solver.log" -ForegroundColor Yellow }
    } else {
        Write-Host "[cf_solver] boterdrop_wrapper.py 未找到，跳过。" -ForegroundColor Yellow
    }
} else {
    Write-Host "[cf_solver] cf_solver 目录未找到，跳过。请手动启动 cf_solver (端口 8001)" -ForegroundColor Yellow
}

# ---------- 2. API service (foreground) ----------
Set-Location $PSScriptRoot
Write-Host "[api] 启动 imagefree_api → http://127.0.0.1:$apiPort  (Ctrl+C 停止)"
& $py -m uvicorn api.main:app --host 127.0.0.1 --port $apiPort