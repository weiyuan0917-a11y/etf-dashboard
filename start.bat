@echo off
REM ================================================================
REM  A 股 ETF 工具台 · Windows 一键启动
REM  作者：weiyuan0917-a11y  许可证：MIT
REM  用法：双击本文件即可
REM ================================================================
chcp 65001 >nul 2>&1
setlocal ENABLEDELAYEDEXPANSION

REM 切到本文件所在目录（支持桌面快捷方式 / 双击）
cd /d "%~dp0"

echo.
echo ============================================================
echo   A 股 ETF 工具台 · Windows 一键启动
echo ============================================================
echo.

REM ---- 1. 检测 Python ----
where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 没检测到 Python。
    echo.
    echo   这是个 Python 项目,需要先装 Python 3.10 或更高版本:
    echo     1. 打开 https://www.python.org/downloads/
    echo     2. 下载 "Windows installer (64-bit)"
    echo     3. 双击安装,**务必勾上** "Add Python to PATH"
    echo     4. 装完回来再双击 start.bat
    echo.
    echo  3 秒后自动打开下载页...
    timeout /t 3 /nobreak >nul
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('py --version 2^>^&1') do set PYVER=%%i
echo [OK] 检测到 Python !PYVER!

REM ---- 2. 装依赖（首次需要 1-3 分钟,之后秒过） ----
echo.
echo [1/3] 检查依赖...
py -m pip install --upgrade pip --quiet --disable-pip-version-check 2>nul
py -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] 装依赖失败,可能是网络问题。
    echo   试手动跑这条看详细错误:
    echo     py -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo [OK] 依赖就绪

REM ---- 3. 选端口（8501 占用就 +1） ----
set PORT=8501
netstat -ano | findstr "LISTENING" | findstr ":8501 " >nul 2>&1
if not errorlevel 1 (
    echo [WARN] 8501 端口被占用,换 8502
    set PORT=8502
)

REM ---- 4. 启 streamlit + 等就绪后开浏览器 ----
echo.
echo [2/3] 启动服务(端口 !PORT!)...
echo   按 Ctrl+C 关闭
echo.

REM 后台启 streamlit,把日志写文件方便排查
start "etf-dashboard" /B py -m streamlit run app.py --server.port !PORT! --server.headless true --browser.gatherUsageStats false > streamlit.log 2>&1

REM 等 streamlit 起来(最多 30 秒)
set /a WAITED=0
:WAIT_LOOP
timeout /t 1 /nobreak >nul
set /a WAITED+=1
netstat -ano | findstr "LISTENING" | findstr ":!PORT! " >nul 2>&1
if not errorlevel 1 goto STARTED
if !WAITED! GEQ 30 (
    echo [ERROR] 30 秒内 streamlit 没起来,日志 tail:
    powershell -Command "Get-Content streamlit.log -Tail 20"
    pause
    exit /b 1
)
goto WAIT_LOOP

:STARTED
echo [3/3] 服务已就绪,打开浏览器...
timeout /t 2 /nobreak >nul
start "" http://localhost:!PORT!/

echo.
echo ============================================================
echo   服务在跑,浏览器已打开。
echo   日志: streamlit.log
echo   关闭: 关掉这个黑色窗口,或 Ctrl+C
echo ============================================================
echo.

REM 阻塞当前脚本,用户关窗即停 streamlit
title ETF Dashboard - 按任意键退出
pause >nul

echo.
echo 正在关闭 streamlit...
taskkill /FI "WINDOWTITLE eq etf-dashboard*" /T /F >nul 2>&1
exit /b 0
