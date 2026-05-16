@echo off
title Still Point Engine
echo 🚀 Starting Still Point Engine...
echo.

:: Start FastAPI Backend
echo ▶ Starting FastAPI backend on http://127.0.0.1:8000
start "FastAPI Backend" cmd /c ".\stillpoint_env\Scripts\python.exe server.py"

:: Wait for backend to be ready
timeout /t 3 /nobreak >nul

:: Start React Frontend
echo ▶ Starting React frontend on http://localhost:5173
cd frontend
start "React Frontend" cmd /c "npm run dev"
cd ..

echo.
echo ✅ Still Point Engine running!
echo    → UI:  http://localhost:5173
echo    → API: http://127.0.0.1:8000
echo.
echo Close the newly opened command prompt windows to stop the servers.
pause
