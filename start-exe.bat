@echo off
setlocal
chcp 65001 > nul

cd /d "%~dp0"
set "EXE=%~dp0dist-app\Vivi\Vivi.exe"

if not exist "%EXE%" (
    echo EXE not found: %EXE%
    echo Build app first: build.bat
    pause
    exit /b 1
)

start "" "%EXE%"
exit /b 0
