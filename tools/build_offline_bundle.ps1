<#
.SYNOPSIS
    打包离线依赖（给"安装官方 Python + 虚拟环境"的部署方式用）。

.DESCRIPTION
    在有网络的机器上执行，生成 vendor\offline 目录，内含全部依赖轮子与安装脚本。
    把整个项目目录（含 vendor\offline）拷到离线机后，运行其中的 install_offline.bat 即可。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\build_offline_bundle.ps1
#>
param(
    [string]$OutDir = 'vendor\offline',
    [string]$PythonVersion = '3.8'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host '[错误] 未找到 .venv，请先创建虚拟环境并安装 requirements-dev.txt' -ForegroundColor Red
    exit 1
}

$abi = 'cp' + ($PythonVersion -replace '\.', '')
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Write-Host "正在下载 $PythonVersion 版依赖到 $OutDir ..." -ForegroundColor Cyan

& $python -m pip download -r requirements.txt -d $OutDir `
    --python-version $PythonVersion --implementation cp --abi $abi --platform win_amd64 `
    --only-binary=:all: --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Host '[错误] 依赖下载失败，请检查网络或 pip 源' -ForegroundColor Red
    exit $LASTEXITCODE
}

# 安装脚本用纯 ASCII 写成，避免不同代码页下乱码
$lines = @(
    '@echo off',
    'rem Install offline dependencies into .venv (run this on the offline machine).',
    'setlocal',
    'cd /d "%~dp0..\.."',
    'set "PY=%~dp0..\..\.venv\Scripts\python.exe"',
    'if not exist "%PY%" (',
    '  echo Creating virtual environment...',
    '  python -m venv .venv',
    ')',
    'if not exist "%PY%" (',
    '  echo [ERROR] Python not found. Install Python 3.8.10 x64 first.',
    '  pause',
    '  exit /b 1',
    ')',
    '"%PY%" -m pip install --no-index --find-links "%~dp0" -r requirements.txt',
    'if errorlevel 1 (',
    '  echo [ERROR] Install failed.',
    ') else (',
    '  echo [OK] Dependencies installed.',
    ')',
    'pause'
)
$installer = ($lines -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText((Join-Path $OutDir 'install_offline.bat'), $installer, (New-Object System.Text.ASCIIEncoding))

$count = (Get-ChildItem -LiteralPath $OutDir -Filter *.whl | Measure-Object).Count
Write-Host "[完成] 已打包 $count 个依赖轮子到 $OutDir" -ForegroundColor Green
Write-Host '把整个项目目录拷到离线机，运行 vendor\offline\install_offline.bat'