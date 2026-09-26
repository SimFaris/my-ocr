<#
.SYNOPSIS
    取消开机自启的计划任务。
#>
param([string]$TaskName = 'MyOCR-Service')

& schtasks.exe /Delete /TN $TaskName /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "[完成] 已删除计划任务 $TaskName" -ForegroundColor Green
} else {
    Write-Host '[提示] 删除失败：任务不存在或当前不是管理员' -ForegroundColor Yellow
}