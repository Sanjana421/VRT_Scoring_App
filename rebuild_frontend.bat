@echo off
:: Re-build the React frontend after any UI changes.
:: Only needed when you edit files in frontend\src\

setlocal
set "ROOT=%~dp0"
set "FRONTEND_SRC=%~dp0frontend"

if not exist "%FRONTEND_SRC%" (
    echo ERROR: Frontend source not found at %FRONTEND_SRC%
    pause
    exit /b 1
)

echo Building frontend...
pushd "%FRONTEND_SRC%"
call npm run build
if errorlevel 1 (
    echo Build failed.
    popd
    pause
    exit /b 1
)
popd
echo Done. Restart start.bat to serve the updated frontend.
pause
endlocal
