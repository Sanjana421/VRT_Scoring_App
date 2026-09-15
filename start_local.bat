@echo off
:: VRT - Run locally on YOUR LAPTOP using D:\Data_Scoring data
:: No lab server needed. Uses the real v5 data already on this machine.

setlocal

:: -- Point to real local data -----------------------------------------------
set "DISTVRT_DATA_FOLDER=C:\Users\Sanjana\Documents\Data_Scoring_MATLAB\v5_data"
set "DISTVRT_SCORING_LOG=%DISTVRT_DATA_FOLDER%\DistVRT_v5_DataScoringLog.xlsx"
set "DISTVRT_RECHECKS_LOG=%DISTVRT_DATA_FOLDER%\DistVRT_v5_Rechecks.xlsx"

:: -- Sanity check ----------------------------------------------------------
if not exist "%DISTVRT_SCORING_LOG%" (
    echo ERROR: Scoring log not found at %DISTVRT_SCORING_LOG%
    echo Make sure D:\Data_Scoring exists on this machine.
    pause
    exit /b 1
)
if not exist "%DISTVRT_DATA_FOLDER%" (
    echo ERROR: Data folder not found at %DISTVRT_DATA_FOLDER%
    pause
    exit /b 1
)

echo.
echo ======================================================
echo  VRT - LOCAL MODE (laptop)
echo  Scoring log : %DISTVRT_SCORING_LOG%
echo  Data folder : %DISTVRT_DATA_FOLDER%
echo ======================================================
echo.
echo  Open Chrome to: http://localhost:8000
echo  Press Ctrl+C to stop.
echo.

cd /d "%~dp0backend"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info

if errorlevel 1 (
    echo.
    echo ERROR: Server failed. Run install.bat first.
    pause
)
endlocal
