# verify-start-modes.ps1 (B5b / P1-6)
# Static verification of desktop\start-desktop.bat fixes. Does NOT start any service / occupy ports.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $root 'start-desktop.bat'
if (-not (Test-Path $bat)) { Write-Error "start-desktop.bat not found: $bat" }

$text = [System.IO.File]::ReadAllText($bat, [System.Text.Encoding]::GetEncoding(936))
$checks = [ordered]@{}
# 1. MODE drives IF_MOCK_UPSTREAM (real->0, default mock->1)
$checks['MODE real branch sets IF_MOCK=0'] = $text -match 'if /i "%MODE%"=="real" \(set IF_MOCK=0\)'
$checks['launcher writes IF_MOCK_UPSTREAM from variable'] = $text -match 'set IF_MOCK_UPSTREAM=%IF_MOCK%'
# 2. cf_solver readiness polling (30 x 2s with netstat LISTENING)
$checks['cf_solver poll loop 30x'] = $text -match 'for /l %%i in \(1,1,30\)'
$checks['cf_solver LISTENING probe'] = $text -match ':8001 ' -and $text -match 'LISTENING'
$checks['cf_solver timeout tails logs'] = $text -match 'not ready within 60s'
# 3. healthz diagnostics on failure (http_code + body + launcher echo)
$checks['healthz captures http_code'] = $text -match '{http_code}'
$checks['healthz failure prints body'] = $text -match '/v1/healthz body'
$checks['healthz failure echoes launcher'] = $text -match 'launcher content'
# 4. stale backend cleanup with title + port double check
$checks['cleanup filters tingfeng-backend title'] = $text -match 'findstr /i "tingfeng-backend"'
$checks['cleanup verifies port 8100'] = $text -match ':8100 ' -and $text -match 'taskkill /pid'
# 5. encoding: GBK-compatible + CRLF
$bytes = [System.IO.File]::ReadAllBytes($bat)
$crlf = 0
for ($i = 0; $i -lt $bytes.Length - 1; $i++) { if ($bytes[$i] -eq 13 -and $bytes[$i+1] -eq 10) { $crlf++ } }
$checks['CRLF line endings'] = $crlf -gt 10
$checks['no UTF-8 BOM'] = -not ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)

$failed = 0
foreach ($k in $checks.Keys) {
    $ok = $checks[$k]
    if (-not $ok) { $failed++ }
    Write-Output ("[{0}] {1}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $k)
}
Write-Output ("RESULT: {0} pass, {1} fail" -f ($checks.Count - $failed), $failed)
exit $failed