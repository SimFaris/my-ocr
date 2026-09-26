@echo off
rem ==========================================================
rem  局域网离线 OCR 系统 —— 启动后端服务
rem
rem  用法：
rem    直接双击本文件即可启动
rem    带参数运行：start_server.bat --no-https --http-port 8088
rem    计划任务静默启动：start_server.bat --no-pause
rem
rem  停止服务：在本窗口按 Ctrl+C
rem ==========================================================
setlocal enabledelayedexpansion
title 局域网离线 OCR 服务
cd /d "%~dp0"

set "NOPAUSE="
if /i "%~1"=="--no-pause" (
  set "NOPAUSE=1"
  shift
)

rem 依次尝试：项目自带虚拟环境 -> 免安装运行时 -> 系统 PATH 中的 python
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0vendor\runtime38\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo === 局域网离线 OCR 系统 ===
echo.
echo 使用的 Python：%PY%

if not exist "%~dp0run.py" goto no_runpy
"%PY%" -c "import flask" 2>nul
if errorlevel 1 goto no_deps

echo.
echo [1/3] 运行环境自检
echo.
"%PY%" "%~dp0tools\check_env.py"
if errorlevel 1 (
  echo.
  echo 自检发现阻塞项，未启动服务，请按上面的提示处理后重试。
  set "EXITCODE=1"
  goto end
)

echo.
echo [2/3] 准备自签证书
if exist "%~dp0data\certs\server.crt" (
  echo        证书已存在，跳过生成。
) else (
  "%PY%" "%~dp0tools\gen_cert.py"
  if errorlevel 1 (
    echo        证书生成失败，未启动服务。
    set "EXITCODE=1"
    goto end
  )
)

echo.
echo [3/3] 启动服务，按 Ctrl+C 可停止
echo        提示：首次运行如弹出防火墙提示，请选择允许访问。
echo.
"%PY%" "%~dp0run.py" %*
set "EXITCODE=%ERRORLEVEL%"
echo.
echo 服务已退出，返回码 %EXITCODE%
if not "%EXITCODE%"=="0" echo 请查看 data\logs 目录下的日志排查原因。
goto end

:no_deps
echo [错误] 当前 Python 环境缺少依赖（未找到 flask）。
echo.
echo 请任选一种方式准备运行环境：
echo    方式A（推荐，免安装）：把打包好的 vendor\runtime38 目录放到项目根目录
echo    方式B（虚拟环境）：
echo        python -m venv .venv
echo        .venv\Scripts\python.exe -m pip install -r requirements.txt
echo    离线机请用 tools\build_offline_bundle.ps1 生成的离线包安装
set "EXITCODE=1"
goto end

:no_runpy
echo [错误] 未找到 run.py，请确认本文件放在项目根目录下。
set "EXITCODE=1"
goto end

:end
if not defined NOPAUSE (
  echo.
  pause
)
exit /b %EXITCODE%