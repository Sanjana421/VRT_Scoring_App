@echo off
:: VRT Scoring App - One-time setup
:: Run this ONCE on each desktop (Woody / Buzz) after copying the Score_Data folder.
:: Requires Python 3.10+ and Node 18+ on PATH.

setlocal
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND_SRC=%~dp0frontend"
set "FRONTEND_DIST=%ROOT%frontend\dist"

echo.
echo ======================================================
echo  VRT Scoring App - Installation
echo ======================================================
echo.

:: -- 1. Python packages -----------------------------------------------
echo [1/3] Installing Python packages...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%BACKEND%\requirements.txt" --break-system-packages --quiet 2>nul || ^
python -m pip install -r "%BACKEND%\requirements.txt" --quiet
if errorlevel 1 (
    echo  ERROR: pip install failed. Make sure Python 3.10+ is installed and on PATH.
    pause
    exit /b 1
)
echo  Python packages OK.
echo.

:: -- 2. Node packages -------------------------------------------------
echo [2/3] Installing Node packages...
if not exist "%FRONTEND_SRC%" (
    echo  WARNING: Frontend source not found at %FRONTEND_SRC%
    echo           Skipping Node install. Scoring will work without the frontend build
    echo           if you already have a built dist folder.
    goto :build_skip
)
pushd "%FRONTEND_SRC%"
call npm install --silent
if errorlevel 1 (
    echo  ERROR: npm install failed. Make sure Node 18+ is installed and on PATH.
    popd
    pause
    exit /b 1
)
echo  Node packages OK.

:: -- 3. Build React frontend ------------------------------------------
echo [3/3] Building React frontend...
call npm run build
if errorlevel 1 (
    echo  ERROR: npm run build failed.
    popd
    pause
    exit /b 1
)
popd
echo  Frontend built to: %FRONTEND_DIST%
goto :done

:build_skip
echo [3/3] Skipped (no frontend source).

:done
echo.
echo ======================================================
echo  Installation complete!
echo  Run START.bat to launch the scoring app.
echo ======================================================
echo.
pause
endlocal
