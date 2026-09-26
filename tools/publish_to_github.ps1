<#
.SYNOPSIS
    把本项目发布到 GitHub（创建仓库 + 推送 + 可选发布压缩包）。

.DESCRIPTION
    自动处理两件事，让发布不依赖手工配置：
      1. 自动探测系统代理（如 Clash/V2Ray 的 127.0.0.1:7897）并让 git 与 gh 使用它。
         很多机器上浏览器走代理能上 GitHub，但命令行不走代理，于是 git push 超时。
      2. 用 gh 作为 git 的凭据助手（gh auth setup-git），推送时不需要输账号密码/Token。

    使用前只需登录一次：gh auth login（选 GitHub.com → HTTPS → 浏览器授权）。
    仓库默认是私有的，用 -Visibility public 可改为公开。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1 -Visibility public
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1 -WithRelease
    powershell -ExecutionPolicy Bypass -File tools\publish_to_github.ps1 -Proxy http://127.0.0.1:10809
#>
param(
    [string]$RepoName = 'my-ocr',
    [ValidateSet('private', 'public')][string]$Visibility = 'private',
    [string]$Description = '局域网离线多用户 OCR 系统（封装 Umi-OCR：批量图片 / 批量 PDF / 摄像头拍照）',
    [string]$Proxy = '',
    [switch]$NoProxy,
    [switch]$WithRelease,
    [string]$ReleaseZip = '',
    [string]$Tag = 'v0.1.0'
)

# 脚本要驱动 gh / git / ssh 等外部命令：它们的 stderr 在 Stop 策略下会被当成
# 终止性错误（比如 gh auth status 未登录时的提示），导致提前退出。所以显式检查退出码。
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Gh {
    $onPath = Get-Command gh -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\GitHub CLI\gh.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\GitHub.cli_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\gh.exe'),
        'C:\Program Files\GitHub CLI\gh.exe')) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Get-SystemProxy {
    $reg = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if (-not $reg -or $reg.ProxyEnable -ne 1 -or -not $reg.ProxyServer) { return '' }
    $server = [string]$reg.ProxyServer
    if ($server -match '=') {
        $pair = @{}
        foreach ($piece in ($server -split ';')) {
            $kv = $piece -split '=', 2
            if ($kv.Count -eq 2) { $pair[$kv[0].Trim()] = $kv[1].Trim() }
        }
        if ($pair['https']) { $server = $pair['https'] }
        elseif ($pair['http']) { $server = $pair['http'] }
    }
    if ($server -notmatch '^[a-zA-Z]+://') { $server = 'http://' + $server }
    return $server
}

function Test-Tcp([string]$Target, [int]$Port, [int]$TimeoutMs = 6000) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($Target, $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false) -and $client.Connected
        $client.Close()
        return $ok
    } catch { return $false }
}

$gh = Find-Gh
if (-not $gh) {
    Write-Host '[错误] 未找到 gh（GitHub CLI）' -ForegroundColor Red
    Write-Host '安装：winget install --id GitHub.cli --scope user'
    exit 1
}
Write-Host "gh：$gh" -ForegroundColor Cyan

# ---------- 代理 ----------
if (-not $NoProxy) {
    if (-not $Proxy) { $Proxy = Get-SystemProxy }
    if ($Proxy) {
        Write-Host "检测到系统代理，git 与 gh 都走它：$Proxy" -ForegroundColor Cyan
        $env:HTTP_PROXY = $Proxy
        $env:HTTPS_PROXY = $Proxy
        & git config --global "http.https://github.com/.proxy" $Proxy
        & git config --global "https.https://github.com/.proxy" $Proxy
    } else {
        Write-Host '未检测到系统代理（若 git push 超时，可用 -Proxy 手动指定）' -ForegroundColor Yellow
    }
}

# ---------- 登录 ----------
& $gh auth status *> $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '[需要你先登录一次]' -ForegroundColor Yellow
    Write-Host '在另一个 PowerShell 窗口执行（会弹浏览器授权）：'
    Write-Host "    & `"$gh`" auth login" -ForegroundColor Green
    Write-Host '  选择：GitHub.com → HTTPS → Login with a web browser'
    Write-Host '登录完成后重新运行本脚本。'
    exit 2
}
$user = (& $gh api user --jq .login 2>$null).Trim()
if (-not $user) { Write-Host '[错误] 取不到 GitHub 用户名，请确认已登录' -ForegroundColor Red; exit 1 }
Write-Host "已登录：$user" -ForegroundColor Green

# 让 git 用 gh 作为凭据助手，推送时不需要手动输账号密码
& $gh auth setup-git *> $null 2>&1

# ---------- 创建仓库 ----------
Write-Host ''
Write-Host "创建仓库 $user/$RepoName（$Visibility）..." -ForegroundColor Cyan
& $gh repo view "$user/$RepoName" *> $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host '  仓库已存在，跳过创建。'
} else {
    & $gh repo create "$user/$RepoName" "--$Visibility" --description $Description
    if ($LASTEXITCODE -ne 0) { Write-Host '[错误] 创建仓库失败' -ForegroundColor Red; exit 1 }
}

# ---------- 关联远程 ----------
$useSsh = (-not $Proxy) -and (-not (Test-Tcp 'github.com' 443))
if ($useSsh) {
    Write-Host '未走代理且 443 不通，改用 SSH 推送' -ForegroundColor Yellow
    $sshDir = Join-Path $env:USERPROFILE '.ssh'
    if (-not (Test-Path -LiteralPath $sshDir)) { New-Item -ItemType Directory -Force -Path $sshDir | Out-Null }
    $keyPath = Join-Path $sshDir 'id_ed25519'
    if (-not (Test-Path -LiteralPath $keyPath)) {
        & ssh-keygen -q -t ed25519 -N '""' -C "my-ocr@$env:COMPUTERNAME" -f $keyPath
    }
    & $gh ssh-key add "$keyPath.pub" --title "my-ocr-$env:COMPUTERNAME" 2>&1 | ForEach-Object { '  ' + $_ }
    $remote = "git@github.com:$user/$RepoName.git"
} else {
    $remote = "https://github.com/$user/$RepoName.git"
}

& git remote remove origin *> $null 2>&1
& git remote add origin $remote
Write-Host ''
Write-Host "推送 main 到 $remote ..." -ForegroundColor Cyan
& git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host '[错误] 推送失败。排查：' -ForegroundColor Red
    Write-Host '  git ls-remote origin   # 看能否连通'
    Write-Host '  若超时，说明需要代理：-Proxy http://127.0.0.1:7897'
    exit 1
}
Write-Host "[完成] 仓库地址：https://github.com/$user/$RepoName" -ForegroundColor Green

# ---------- 可选：发布压缩包 ----------
if ($WithRelease) {
    if (-not $ReleaseZip -or -not (Test-Path -LiteralPath $ReleaseZip)) {
        $found = Get-ChildItem -Path (Split-Path -Parent $root) -Filter 'my-ocr-*.zip' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
        if ($found) { $ReleaseZip = $found.FullName }
    }
    if (-not $ReleaseZip) {
        Write-Host '[提示] 没找到发布包 zip，跳过 Release（可先运行 tools\build_release.ps1）' -ForegroundColor Yellow
    } else {
        Write-Host "创建 Release $Tag 并附上发布包 ..." -ForegroundColor Cyan
        & $gh release create $Tag $ReleaseZip --title $Tag --notes "局域网离线 OCR 系统 $Tag"
    }
}