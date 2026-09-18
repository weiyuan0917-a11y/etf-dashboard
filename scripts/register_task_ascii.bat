@echo off
REM ============================================================
REM  ETF dashboard: register Windows scheduled task
REM  Trigger: Weekdays 17:00
REM  Action : C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe
REM           D:\etf-dashboard\scripts\daily_update.py
REM  Right-click -> "Run as administrator"
REM ============================================================

set "TASK_NAME=ETF-Daily-Update"
set "PYTHON_EXE=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "SCRIPT=D:\etf-dashboard\scripts\daily_update.py"

echo ============================================================
echo  ETF Dashboard - Register Scheduled Task
echo ============================================================
echo.

REM 1) Validate files
if not exist "%PYTHON_EXE%" (
    echo [ERR] Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo [ERR] Script not found: %SCRIPT%
    pause
    exit /b 1
)
echo [OK] Files validated
echo       Python : %PYTHON_EXE%
echo       Script : %SCRIPT%
echo.

REM 2) Admin check
net session >nul 2>&1
if errorlevel 1 (
    echo [ERR] Please right-click and "Run as administrator"
    pause
    exit /b 1
)
echo [OK] Running as administrator
echo.

REM 3) Clean old task
echo [1/3] Cleaning old task ...
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
echo       done
echo.

REM 4) Register new task
echo [2/3] Registering task ...
schtasks /Create ^ /TN "%TASK_NAME%" ^ /SC WEEKLY ^ /D MON,TUE,WED,THU,FRI ^ /ST 17:00 ^ /RL HIGHEST ^ /TR "\"%PYTHON_EXE%\" \"%SCRIPT%\"" ^ /F
if errorlevel 1 (
    echo.
    echo [ERR] schtasks /Create failed
    pause
    exit /b 1
)
echo       done
echo.

REM 5) Verify
echo [3/3] Verifying ...
schtasks /Query /TN "%TASK_NAME%" /V /FO LIST
echo.
echo ============================================================
echo  [DONE] Weekdays 17:00 auto-update enabled
echo  Log   : D:\etf-dashboard\logs\update_YYYYMMDD.log
echo ============================================================
echo.
pause
