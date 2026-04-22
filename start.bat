@echo off
chcp 65001 >nul
title Agent-1

echo [1/3] Installing dependencies...
.venv\Scripts\pip.exe install -r requirements.txt -q

echo [2/3] Starting backend...
start /b "" .venv\Scripts\python.exe run.py

timeout /t 2 /nobreak >nul

echo [3/3] Starting frontend...
echo   Backend:  http://127.0.0.1:8000
echo   Frontend: http://localhost:5500
echo.
cd client
npm run dev
