@echo off
setlocal
call "%~dp0yoto.bat" preview %*
exit /b %ERRORLEVEL%
