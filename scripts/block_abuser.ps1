# 封禁恶意 IP 脚本——在服务器或本地执行
# 用法：powershell -File scripts/block_abuser.ps1 -Ip 47.112.162.80 -AdminKey <你的管理Key>
param(
    [Parameter(Mandatory=$true)][string]$Ip,
    [Parameter(Mandatory=$true)][string]$AdminKey,
    [string]$ApiBase = "https://imagefree.tingfengai.art"
)
$body = @{ ip = $Ip; block_type = "block"; reason = "恶意刷接口资源（自动封禁脚本）"; ttl_seconds = 0 } | ConvertTo-Json
$headers = @{ "Authorization" = "Bearer $AdminKey"; "Content-Type" = "application/json" }
try {
    $resp = Invoke-RestMethod -Uri "$ApiBase/v1/admin/security/block-ip" -Method Post -Headers $headers -Body $body -TimeoutSec 15
    Write-Host "✅ 已封禁 $Ip" -ForegroundColor Green
    Write-Host ($resp | ConvertTo-Json -Depth 5)
} catch {
    Write-Host "❌ 封禁失败: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails) { Write-Host $_.ErrorDetails.Message }
}
