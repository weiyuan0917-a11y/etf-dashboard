@echo off
REM ETF Tools launcher for the installed application.
REM Uses the bundled Python runtime and never requires system Python.
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "PYTHON=%~dp0runtime\python.exe"
set "PORT=8501"

if not exist "%PYTHON%" goto :missing_runtime
if not exist "%~dp0app.py" goto :missing_app
if not exist "%~dp0data" mkdir "%~dp0data" >nul 2>&1

REM Reuse an existing local service, otherwise use the first free port.
:find_free_port
netstat -ano | findstr "LISTENING" | findstr ":!PORT! " >nul 2>&1
if errorlevel 1 goto :start_service
if !PORT! GEQ 8510 goto :reuse_service
set /a PORT+=1
goto :find_free_port

:start_service
start "" /B "%PYTHON%" -m streamlit run app.py --server.port !PORT! --server.headless true --browser.gatherUsageStats=false > "%~dp0streamlit.log" 2>&1
set /a WAITED=0

:wait_loop
ping 127.0.0.1 -n 2 >nul
set /a WAITED+=1
netstat -ano | findstr "LISTENING" | findstr ":!PORT! " >nul 2>&1
if not errorlevel 1 goto :open_browser
if !WAITED! GEQ 45 goto :startup_failed
goto :wait_loop

:reuse_service
REM All preferred ports are occupied. Open the default local service.
set "PORT=8501"

:open_browser
start "" "http://localhost:!PORT!/"
exit /b 0

:missing_runtime
echo ERROR: Bundled Python runtime is missing. Reinstall the application.
pause
exit /b 1

:missing_app
echo ERROR: Application files are incomplete. Reinstall the application.
pause
exit /b 1

:startup_failed
echo ERROR: Service did not start within 45 seconds.
if exist "%~dp0streamlit.log" type "%~dp0streamlit.log"
pause
exit /b 1
