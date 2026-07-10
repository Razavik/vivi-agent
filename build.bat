@echo off
setlocal
chcp 65001 > nul

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"

echo [1/4] Closing running Vivi processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'SilentlyContinue'; $root = $env:PROJECT_ROOT; Get-Process -Name Vivi | Stop-Process -Force; Get-Process -Name python | Where-Object { $_.Path -and $_.Path.StartsWith($root) } | Stop-Process -Force; exit 0"

echo [2/4] Cleaning previous dist-app...
if exist "%~dp0dist-app" rmdir /s /q "%~dp0dist-app"
if errorlevel 1 goto :error

echo [3/4] Building client and Electron app...
cd /d "%~dp0client"
call npm run dist
if errorlevel 1 goto :error

echo [4/4] Build completed.
echo EXE: %~dp0dist-app\Vivi\Vivi.exe
if not "%VIVI_NO_PAUSE%"=="1" pause
exit /b 0

:error
echo.
echo Build failed.
if not "%VIVI_NO_PAUSE%"=="1" pause
exit /b 1
