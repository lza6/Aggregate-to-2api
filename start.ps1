# ============================================================
#  imagefree_api one-click launcher
#  1) start cf_solver (port 8001, reuse GPT project venv)
#  2) run imagefree_api (port 8100) in foreground
# ============================================================
$ErrorActionPreference = 'Stop'

$py     = 'C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\私单\GPT自动化注册的项目\.venv\Scripts\python.exe'
$cfDir  = 'C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\私单\GPT自动化注册的项目\cf_solver'
$cfPort = 8001
$apiPort = 8100

if (-not (Test-Path $py)) {
    Write-Host "[ERROR] Python interpreter not found: $py" -ForegroundColor Red
    Write-Host "        Edit PY at the top of start.ps1"
    exit 1
}

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
    Write-Host "[cf_solver] already running on port $cfPort, skip." -ForegroundColor Green
} else {
    Write-Host "[cf_solver] starting on port $cfPort ..."
    Start-Process -FilePath $py -ArgumentList 'boterdrop_wrapper.py' -WorkingDirectory $cfDir -WindowStyle Minimized
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Port '127.0.0.1' $cfPort) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if ($ready) { Write-Host "[cf_solver] ready." -ForegroundColor Green }
    else { Write-Host "[cf_solver] timeout after 60s, check $cfDir\logs\cf_solver.log" -ForegroundColor Yellow }
}

# ---------- 2. API service (foreground) ----------
Set-Location $PSScriptRoot
Write-Host "[api] starting imagefree_api on http://127.0.0.1:$apiPort  (Ctrl+C to stop)"
& $py -m uvicorn api.main:app --host 127.0.0.1 --port $apiPort
