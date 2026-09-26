<#
.SYNOPSIS
    把本项目发布到 GitHub（创建仓库 + 推送 + 可选发布压缩包）。

.DESCRIPTION
    本机实测：github.com 的 443 端口不通，但 22 端口（SSH）与 api.github.com 通，
    所以脚本走 SSH 推送、用 gh 的 API 建仓库并上传 SSH 公钥，全程不需要打开网页。

    使用前只需做一次登录：gh auth login（选 GitHub.com → HTTPS → 浏览器授权；
    若浏览器打不开 github.com，可用 Personal Access Token 方式登录）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1 -Visibility public
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1 -WithRelease -ReleaseZip E:\CODE\my-ocr-0.1.0-20260926.zip
#>
param(
    [string]$RepoName = 'my-ocr',
    [ValidateSet('private', 'public')][string]$Visibility = 'private',
    [string]$Description = '局域网离线多用户 OCR 系统（封装 Umi-OCR：批量图片 / 批量 PDF / 摄像头拍照）',
    [switch]$WithRelease,
    [string]$ReleaseZip = '',
    [string]$Tag = 'v0.1.0',
    [switch]$SkipPush
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Gh {
    $onPath = Get-Command gh -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\GitHub CLI\gh.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\GitHub.cli_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\gh.exe'),
        'C:\Program Files\GitHub CLI\gh.exe'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Test-Tcp([string]$HostName, [int]$Port, [int]$TimeoutMs = 8000) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false) -and $client.Connected
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

$gh = Find-Gh
if (-not $gh) {
    Write-Host '[错误] 未找到 gh（GitHub CLI）。安装：winget install --id GitHub.cli --scope user' -ForegroundColor Red
    exit 1
}
Write-Host "使用 gh：$gh" -ForegroundColor Cyan

& $gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '[需要你先登录一次]' -ForegroundColor Yellow
    Write-Host '在另一个 PowerShell 窗口里执行：'
    Write-Host "    & `"$gh`" auth login" -ForegroundColor Green
    Write-Host '  选 GitHub.com → HTTPS → 按提示在浏览器里授权（或用 Token 登录）'
    Write-Host '登录完成后，重新运行本脚本即可。'
    exit 2
}

$user = (& $gh api user --jq .login).Trim()
if (-not $user) { Write-Host '[错误] 无法获取 GitHub 用户名' -ForegroundColor Red; exit 1 }
Write-Host "已登录：$user" -ForegroundColor Green

# 1) 创建仓库（用 API，走 api.github.com）
Write-Host ''
Write-Host "创建仓库 $user/$RepoName（$Visibility）..." -ForegroundColor Cyan
& $gh repo view "$user/$RepoName" *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  仓库已存在，跳过创建。'
} else {
    & $gh repo create "$user/$RepoName" "--$Visibility" --description $Description
    if ($LASTEXITCODE -ne 0) { Write-Host '[错误] 创建仓库失败' -ForegroundColor Red; exit 1 }
}

# 2) 准备 SSH 公钥（443 不通、22 通，所以用 SSH 推送）
$sshDir = Join-Path $env:USERPROFILE '.ssh'
if (-not (Test-Path -LiteralPath $sshDir)) { New-Item -ItemType Directory -Force -Path $sshDir | Out-Null }
$keyPath = Join-Path $sshDir 'id_ed25519'
if (-not (Test-Path -LiteralPath $keyPath)) {
    Write-Host '生成 SSH 密钥 ...' -ForegroundColor Cyan
    $sshKeygen = Join-Path (Split-Path -Parent (Split-Path -Parent (Get-Command ssh-keygen -ErrorAction SilentlyContinue).Source)) 'bin\ssh-keygen.exe'
    if (-not (Test-Path -LiteralPath $sshKeygen)) { $sshKeygen = 'ssh-keygen' }
    & $sshKeygen -q -t ed25519 -N '""' -C "my-ocr@$env:COMPUTERNAME" -f $keyPath
    if ($LASTEXITCODE -ne 0) { Write-Host '[错误] 生成 SSH 密钥失败' -ForegroundColor Red; exit 1 }
}
$publicKey = (Get-Content -LiteralPath "$keyPath.pub" -Raw).Trim()
if (-not $publicKey) { Write-Host '[错误] 读不到 SSH 公钥' -ForegroundColor Red; exit 1 }

Write-Host '把公钥上传到 GitHub 账号（通过 API，不需要打开网页）...' -ForegroundColor Cyan
& $gh ssh-key add "$keyPath.pub" --title "my-ocr-$env:COMPUTERNAME" 2>&1 | ForEach-Object { '  ' + $_ }

# 3) 关联远程并推送
$remote = "git@github.com:$user/$RepoName.git"
& git remote remove origin *> $null
& git remote add origin $remote
Write-Host ''
Write-Host "推送 main 到 $remote ..." -ForegroundColor Cyan
if (-not $SkipPush) {
    if (-not (Test-Tcp 'github.com' 22)) {
        Write-Host '  github.com:22 不通，尝试走 443 端口的 SSH（ssh.github.com）' -ForegroundColor Yellow
        $configPath = Join-Path $sshDir 'config'
        $block = @(
            '',
            '# my-ocr：GitHub SSH 走 443 端口（本机 22 不通时用）',
            'Host github.com',
            '  HostName ssh.github.com',
            '  Port 443',
            '  User git'
        ) -join "`r`n"
        if (-not (Test-Path -LiteralPath $configPath) -or -not (Select-String -LiteralPath $configPath -Pattern 'my-ocr：GitHub SSH' -Quiet)) {
            Add-Content -LiteralPath $configPath -Value $block -Encoding utf8
        }
    }
    & git -c core.sshCommand='ssh -o StrictHostKeyChecking=accept-new' push -u origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[错误] 推送失败。检查网络或执行 ssh -T git@github.com 看认证是否正常。' -ForegroundColor Red
        exit 1
    }
    Write-Host "[完成] 仓库地址：https://github.com/$user/$RepoName" -ForegroundColor Green
}

# 4) 可选：发布压缩包
if ($WithRelease) {
    if (-not $ReleaseZip -or -not (Test-Path -LiteralPath $ReleaseZip)) {
        $found = Get-ChildItem -Path (Split-Path -Parent $root) -Filter 'my-ocr-*.zip' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
        if ($found) { $ReleaseZip = $found.FullName }
    }
    if (-not $ReleaseZip) {
        Write-Host '[提示] 没找到发布包 zip，跳过 Release（可先用 tools\build_release.ps1 生成）' -ForegroundColor Yellow
    } else {
        Write-Host "创建 Release $Tag 并附上 $ReleaseZip ..." -ForegroundColor Cyan
        & $gh release create $Tag $ReleaseZip --title $Tag --notes "局域网离线 OCR 系统 $Tag"
    }
}