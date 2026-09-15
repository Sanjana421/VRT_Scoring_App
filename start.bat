@echo off
:: VRT Scoring App - Launch script
:: Double-click this to start the server, then open Chrome to http://localhost:8000

setlocal
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"

:: Check if port 8000 is already in use
netstat -ano | findstr ":8000 " | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    echo Server already running on port 8000.
    echo Opening browser...
    start "" "http://localhost:8000"
    exit /b 0
)

echo.
echo ======================================================
echo  VRT Scoring App
echo  Gustafson Lab - Indiana University
echo ======================================================
echo.
echo  Starting backend server...
echo  Open Chrome to: http://localhost:8000
echo.
echo  Press Ctrl+C to stop the server.
echo  DO NOT close this window while scoring.
echo ======================================================
echo.

cd /d "%BACKEND%"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level warning

if errorlevel 1 (
    echo.
    echo ERROR: Server failed to start.
    echo Make sure you ran install.bat first.
    pause
)
endlocal
