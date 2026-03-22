@echo off
setlocal
call "%~dp0yoto.bat" run %*
exit /b %ERRORLEVEL%
