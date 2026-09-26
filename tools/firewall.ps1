<#
.SYNOPSIS
    为 OCR 服务放行防火墙端口（需要管理员权限）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\firewall.ps1 -Ports 8080,8443
#>
param(
    [int[]]$Ports = @(8080, 8443),
    [string]$RuleName = 'MyOCR'
)

$ErrorActionPreference = 'Continue'
foreach ($port in $Ports) {
    $name = "$RuleName-$port"
    & netsh.exe advfirewall firewall delete rule name="$name" | Out-Null
    & netsh.exe advfirewall firewall add rule name="$name" dir=in action=allow protocol=TCP localport=$port | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[完成] 已放行 TCP $port" -ForegroundColor Green
    } else {
        Write-Host "[失败] 放行 TCP $port 失败，请以管理员身份运行" -ForegroundColor Red
    }
}