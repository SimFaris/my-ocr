@echo off
rem ==========================================================
rem  在【客户端】电脑上导入服务器根证书，需要管理员权限。
rem
rem  用法：把浏览器下载的 my-ocr-root-ca.cer 与本文件放在一起，
rem        右键“以管理员身份运行”。
rem        也可直接指定证书路径：import_root_cert.bat D:\ca.cer
rem ==========================================================
setlocal
if "%~1"=="" (
  set "CERTFILE=my-ocr-root-ca.cer"
) else (
  set "CERTFILE=%~1"
)

if not exist "%CERTFILE%" (
  echo.
  echo [错误] 未找到证书文件：%CERTFILE%
  echo        请先访问 https://服务器IP:8443/api/system/root-cert 下载。
  echo.
  pause
  exit /b 1
)

certutil -addstore -f Root "%CERTFILE%"
if errorlevel 1 (
  echo.
  echo [错误] 导入失败。请确认是以“管理员身份”运行本文件。
) else (
  echo.
  echo [完成] 根证书已导入“受信任的根证书颁发机构”。
  echo        请关闭并重新打开浏览器，再用 https 访问服务。
)
echo.
pause
exit /b 0