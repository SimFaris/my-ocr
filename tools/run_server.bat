@echo off
rem 启动 OCR 服务：首次会自动生成自签证书，然后监听 http 与 https。
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到 .venv，请先按 docs\deploy-win7.md 安装依赖。
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "tools\gen_cert.py"
".venv\Scripts\python.exe" "run.py" %*
endlocal