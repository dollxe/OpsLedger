@echo off
setlocal
chcp 65001 > nul
title 대기배출시설 운영기록부

set APP_DIR=%~dp0
set PYTHON=%APP_DIR%python\python.exe

REM ── 최초 설치 확인 ───────────────────────────
if not exist "%PYTHON%" (
    echo  Python 이 없습니다. 설치를 시작합니다...
    call "%APP_DIR%setup.bat"
    if errorlevel 1 (
        echo  설치 실패. setup.bat 을 직접 실행해보세요.
        pause
        exit /b 1
    )
)

REM ── 라이브러리 확인 ──────────────────────────
"%PYTHON%" -c "import streamlit" 2>nul
if errorlevel 1 (
    echo  라이브러리가 없습니다. 설치를 시작합니다...
    call "%APP_DIR%setup.bat"
    if errorlevel 1 exit /b 1
)

REM ── 이미 실행 중인지 확인 ────────────────────
netstat -an 2>nul | findstr ":8501" > nul
if not errorlevel 1 (
    echo  앱이 이미 실행 중입니다. 브라우저를 엽니다...
    start "" "http://localhost:8501"
    exit /b 0
)

REM ── 앱 실행 ──────────────────────────────────
echo.
echo  =============================================
echo    대기배출시설 운영기록부
echo  =============================================
echo.
echo  앱이 시작됩니다. 잠시 기다려주세요...
echo  잠시 후 브라우저가 자동으로 열립니다.
echo.
echo  ※ 이 창을 닫으면 앱이 종료됩니다.
echo  =============================================
echo.

REM 4초 후 브라우저 열기 (백그라운드)
start /b cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8501"

"%PYTHON%" -m streamlit run "%APP_DIR%app_local.py" ^
    --server.port 8501 ^
    --browser.gatherUsageStats false ^
    --server.headless true

echo.
echo  앱이 종료되었습니다.
pause
