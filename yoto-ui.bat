@echo off
setlocal

for %%I in ("%~dp0.") do set "ROOT=%%~fI"

pushd "%ROOT%" >nul
if errorlevel 1 (
    echo [YOTO] Failed to enter bundle root: %ROOT%
    exit /b 1
)

call "%ROOT%\yoto.bat" ui %*
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
