<#
.SYNOPSIS
    把服务注册为开机自启（Windows 计划任务，静默启动，需要管理员权限）。

.DESCRIPTION
    Windows 7 与 Windows 10 都支持计划任务，可以做到开机自动拉起服务且不弹控制台窗口。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\register_service.ps1
    powershell -ExecutionPolicy Bypass -File tools\register_service.ps1 -TaskName MyOCR -RunAsSystem
#>
param(
    [string]$TaskName = 'MyOCR-Service',
    [switch]$RunAsSystem
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $root 'start_server.bat'))) {
    Write-Host '[错误] 未找到 start_server.bat' -ForegroundColor Red
    exit 1
}

$command = 'cmd.exe /c cd /d "' + $root + '" && start_server.bat --no-pause'
if ($RunAsSystem) {
    & schtasks.exe /Create /TN $TaskName /TR $command /SC ONSTART /RU SYSTEM /RL HIGHEST /F
} else {
    & schtasks.exe /Create /TN $TaskName /TR $command /SC ONSTART /RL HIGHEST /F
}
if ($LASTEXITCODE -ne 0) {
    Write-Host '[错误] 注册计划任务失败，请确认以管理员身份运行' -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "[完成] 已注册计划任务 $TaskName（开机自动启动）" -ForegroundColor Green
Write-Host "手动启动：schtasks /Run /TN $TaskName"
Write-Host "查看状态：schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host '取消注册：powershell -File tools\unregister_service.ps1'