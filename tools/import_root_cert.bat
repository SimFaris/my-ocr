@echo off
rem 在【客户端】电脑上导入服务器根证书（需要管理员权限）。
rem 用法：把浏览器下载的 my-ocr-root-ca.cer 与本文件放在一起，右键“以管理员身份运行”。
setlocal
if "%~1"=="" (
  set "CERTFILE=my-ocr-root-ca.cer"
) else (
  set "CERTFILE=%~1"
)
if not exist "%CERTFILE%" (
  echo [错误] 未找到证书文件 %CERTFILE%
  echo        请先访问 https://服务器IP:8443/api/system/root-cert 下载。
  pause
  exit /b 1
)
certutil -addstore -f Root "%CERTFILE%"
if errorlevel 1 (
  echo [错误] 导入失败，请确认以管理员身份运行。
) else (
  echo [完成] 根证书已导入“受信任的根证书颁发机构”。请重启浏览器后访问 https。
)
pause
endlocal