<#
.SYNOPSIS
    打包"免安装运行时"：Python 3.8.10 嵌入式运行时 + 全部依赖。

.DESCRIPTION
    目标机是 Windows 7 时最省事的部署方式：不需要安装 Python、不写注册表，
    把生成的 vendor\runtime38 目录连同项目一起拷过去，双击 start_server.bat 即可。

    必须在有网络的机器上执行。该运行时已在本项目验证：
    99 项后端测试在 Python 3.8.10 下全部通过。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\build_runtime38.ps1
#>
param(
    [string]$Version = '3.8.10',
    [string]$OutDir = 'vendor\runtime38',
    [string]$WheelDir = 'vendor\wheels38'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host '[错误] 未找到 .venv（打包时需要它执行 pip download）' -ForegroundColor Red
    exit 1
}

$majorMinor = ($Version -split '\.')[0] + '.' + ($Version -split '\.')[1]
$abi = 'cp' + ($majorMinor -replace '\.', '')
$zip = Join-Path $root "vendor\python\python-$Version-embed-amd64.zip"

if (-not (Test-Path -LiteralPath $zip)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $zip) | Out-Null
    $urls = @(
        "https://www.python.org/ftp/python/$Version/python-$Version-embed-amd64.zip",
        "https://registry.npmmirror.com/-/binary/python/$Version/python-$Version-embed-amd64.zip"
    )
    foreach ($url in $urls) {
        Write-Host "下载 $url" -ForegroundColor Cyan
        & curl.exe -L --retry 2 --max-time 900 -o $zip $url
        if ((Test-Path -LiteralPath $zip) -and (Get-Item -LiteralPath $zip).Length -gt 5MB) { break }
    }
    if (-not (Test-Path -LiteralPath $zip)) {
        Write-Host '[错误] 嵌入式 Python 下载失败，请手动下载后放到 vendor\python 目录' -ForegroundColor Red
        exit 1
    }
}

Write-Host "准备运行时目录 $OutDir ..." -ForegroundColor Cyan
if (Test-Path -LiteralPath $OutDir) { Remove-Item -LiteralPath $OutDir -Recurse -Force }
Expand-Archive -LiteralPath $zip -DestinationPath $OutDir -Force

# 嵌入式发行版默认关闭 site，这里打开并把 site-packages 加进搜索路径
$tag = $majorMinor -replace '\.', ''
$pth = Join-Path $OutDir ("python" + $tag + "._pth")
if (Test-Path -LiteralPath $pth) {
    @("python" + $tag + ".zip", '.', 'Lib\site-packages', 'import site') |
        Set-Content -LiteralPath $pth -Encoding ascii
}

$site = Join-Path $OutDir 'Lib\site-packages'
New-Item -ItemType Directory -Force -Path $site | Out-Null
New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null

Write-Host "下载 $majorMinor 版依赖轮子 ..." -ForegroundColor Cyan
& $python -m pip download -r requirements.txt -d $WheelDir `
    --python-version $majorMinor --implementation cp --abi $abi --platform win_amd64 `
    --only-binary=:all: --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$count = 0
foreach ($wheel in Get-ChildItem -LiteralPath $WheelDir -Filter *.whl) {
    [System.IO.Compression.ZipFile]::ExtractToDirectory($wheel.FullName, $site, $true)
    $count++
}

Write-Host '验证运行时是否可用 ...' -ForegroundColor Cyan
& (Join-Path $OutDir 'python.exe') -c "import flask, cheroot, requests, openpyxl; print('OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Host '[错误] 运行时依赖导入失败' -ForegroundColor Red
    exit 1
}

Write-Host "[完成] 已解包 $count 个依赖到 $OutDir" -ForegroundColor Green
Write-Host '建议先确认运行时能跑通测试，再拷到离线机：'
Write-Host "  $(Join-Path $OutDir 'python.exe') -m pytest"