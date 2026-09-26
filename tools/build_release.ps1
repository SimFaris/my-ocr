<#
.SYNOPSIS
    生成可拷贝到其他机器的发布包（zip）。

.DESCRIPTION
    打包内容：后端、前端产物、tools、docs、tests、启动脚本、配置样例，以及免安装运行时
    vendor\runtime38（目标机不用装 Python，也不用联网装依赖）。
    默认**不含 Umi-OCR**（体积大），用 -IncludeUmi 可以把 vendor\umi-ocr 一起打包。

    注意：本文件必须保存为 UTF-8 带 BOM。Windows PowerShell 5.1 对无 BOM 的文件按 GBK
    解读，含中文的脚本会被解析错乱（只执行部分语句却不报错），详见 docs\HANDOFF.md。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\build_release.ps1
    powershell -ExecutionPolicy Bypass -File tools\build_release.ps1 -IncludeUmi -OutDir D:\dist
#>
param(
    [string]$OutDir = '',
    [switch]$IncludeUmi,
    [switch]$SkipRuntime,
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $OutDir) { $OutDir = Split-Path -Parent $root }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$versionMatch = Select-String -LiteralPath (Join-Path $root 'backend\__init__.py') -Pattern "__version__\s*=\s*'([^']+)'"
$version = if ($versionMatch) { $versionMatch.Matches[0].Groups[1].Value } else { '0.1.0' }
$stamp = Get-Date -Format 'yyyyMMdd'
$name = "my-ocr-$version-$stamp"
$stage = Join-Path $OutDir $name

Write-Host "发布包暂存目录：$stage" -ForegroundColor Cyan
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

function Copy-Tree([string]$Source, [string]$Target) {
    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Host "  [跳过] 不存在：$Source" -ForegroundColor Yellow
        return
    }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    & robocopy $Source $Target /E /XD __pycache__ .pytest_cache .pytest-tmp node_modules .venv data .git /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "复制失败：$Source" }
}

if (-not $SkipFrontend -and -not (Test-Path -LiteralPath (Join-Path $root 'frontend\dist\index.html'))) {
    Write-Host '前端产物不存在，正在构建 ...' -ForegroundColor Cyan
    Push-Location (Join-Path $root 'frontend')
    & npm.cmd install --no-audit --no-fund
    & npm.cmd run build
    Pop-Location
}

if (-not $SkipRuntime -and -not (Test-Path -LiteralPath (Join-Path $root 'vendor\runtime38\python.exe'))) {
    Write-Host '免安装运行时不存在，正在构建 ...' -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\build_runtime38.ps1')
}
if (-not $SkipRuntime) {
    # 打包前必须验证运行时真的能用，避免把坏掉的运行时打进包里
    $runtimePython = Join-Path $root 'vendor\runtime38\python.exe'
    if (-not (Test-Path -LiteralPath $runtimePython)) { throw '免安装运行时缺失，无法打包' }
    & $runtimePython -c "import flask, cheroot, requests, openpyxl, pytest"
    if ($LASTEXITCODE -ne 0) {
        throw '免安装运行时不可用（依赖导入失败），请重新执行 tools\build_runtime38.ps1'
    }
    Write-Host '免安装运行时自检通过' -ForegroundColor Green
}

Write-Host '复制程序文件 ...' -ForegroundColor Cyan
Copy-Tree (Join-Path $root 'backend') (Join-Path $stage 'backend')
Copy-Tree (Join-Path $root 'frontend\dist') (Join-Path $stage 'frontend\dist')
Copy-Tree (Join-Path $root 'tools') (Join-Path $stage 'tools')
Copy-Tree (Join-Path $root 'docs') (Join-Path $stage 'docs')
Copy-Tree (Join-Path $root 'tests') (Join-Path $stage 'tests')
foreach ($file in 'run.py', 'requirements.txt', 'requirements-dev.txt', 'config.example.json', 'start_server.bat', 'pytest.ini', 'README.md') {
    $source = Join-Path $root $file
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $stage -Force }
}
if (-not $SkipRuntime) {
    Copy-Tree (Join-Path $root 'vendor\runtime38') (Join-Path $stage 'vendor\runtime38')
}
if ($IncludeUmi) {
    Copy-Tree (Join-Path $root 'vendor\umi-ocr') (Join-Path $stage 'vendor\umi-ocr')
}

$guide = Join-Path $root 'docs\install-and-usage.md'
if (Test-Path -LiteralPath $guide) {
    Copy-Item -LiteralPath $guide -Destination (Join-Path $stage '安装与使用说明.md') -Force
}

# 生成 config.json：尽量指向本机已解压的 Umi-OCR
$umiRelative = 'vendor/umi-ocr/Umi-OCR.exe'
$found = Get-ChildItem -Path (Join-Path $root 'vendor\umi-ocr') -Filter 'Umi-OCR.exe' -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName | Sort-Object { if ($_.FullName -like '*Rapid*') { 0 } else { 1 } } | Select-Object -First 1
if ($found) {
    $umiRelative = $found.FullName.Substring($root.Length + 1).Replace('\', '/')
}
$config = @{ umi_exe_path = $umiRelative } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $stage 'config.json'), $config, (New-Object System.Text.UTF8Encoding $false))

$startHere = @(
    '局域网离线 OCR 系统 —— 发布包',
    '',
    '第一步：打开「安装与使用说明.md」',
    '',
    '快速开始：',
    '  1. 确认 Umi-OCR 在 vendor\umi-ocr\ 下（本包若未包含，请自行解压放进去）',
    '  2. 双击 start_server.bat',
    '  3. 浏览器打开 http://本机IP:8080，用 admin 与 data\initial_admin_password.txt 中的密码登录',
    '  4. 登录后立刻点右上角「修改密码」改成自己的密码',
    '',
    '环境自检：vendor\runtime38\python.exe tools\check_env.py',
    '自测：    vendor\runtime38\python.exe -m pytest',
    '',
    '数据、证书、日志都在 data\ 目录下，备份就是复制它。'
) -join "`r`n"
[System.IO.File]::WriteAllText((Join-Path $stage '从这里开始.txt'), $startHere, (New-Object System.Text.UTF8Encoding $true))

$zip = Join-Path $OutDir ("$name.zip")
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Write-Host '正在压缩 ...' -ForegroundColor Cyan

# 优先用 tar.exe（Windows 10 起自带）：它生成规范 zip，条目分隔符是正斜杠，
# 在 macOS/Linux 上解压也能得到正确目录结构。.NET 的 ZipFile 在 Windows 上会写反斜杠，
# 那种包在 Windows 上没事，但换到别的系统解压会把路径压成一个文件名。
$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
$packed = $false
if ($tar) {
    Push-Location $OutDir
    try {
        & tar.exe -a -c -f "$name.zip" $name
        $packed = ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $zip))
    } finally {
        Pop-Location
    }
}
if (-not $packed) {
    Write-Host 'tar 不可用，回退到 .NET 压缩（Windows 上使用不受影响）' -ForegroundColor Yellow
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $stage, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)
$fileCount = (Get-ChildItem -LiteralPath $stage -Recurse -File | Measure-Object).Count
Write-Host "[完成] $zip" -ForegroundColor Green
Write-Host "       体积 $sizeMb MB，$fileCount 个文件"
Write-Host '       目标机解压后先看「安装与使用说明.md」或「从这里开始.txt」'
