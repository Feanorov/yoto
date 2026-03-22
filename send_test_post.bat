@echo off
setlocal
call "%~dp0yoto.bat" send-test %*
exit /b %ERRORLEVEL%
