@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
title 대기운영일지 - 최초 설치

set APP_DIR=%~dp0
set PYTHON_DIR=%APP_DIR%python
set PYTHON=%PYTHON_DIR%\python.exe
set PY_VERSION=3.11.9
set PY_ZIP=%APP_DIR%_python_temp.zip
set PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-embed-amd64.zip

echo.
echo  =============================================
echo    대기배출시설 운영기록부 - 최초 설치
echo  =============================================
echo.
echo  처음 한 번만 실행됩니다. 인터넷이 필요합니다.
echo  약 5~10분 소요될 수 있습니다.
echo.

REM ── Python 다운로드 ──────────────────────────
if not exist "%PYTHON%" (
    echo  [1/4] Python 3.11 다운로드 중...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'" 2>&1
    if not exist "%PY_ZIP%" (
        echo.
        echo  오류: Python 다운로드 실패.
        echo  인터넷 연결을 확인하고 다시 실행하세요.
        echo.
        pause
        exit /b 1
    )

    echo  [2/4] Python 압축 해제 중...
    powershell -NoProfile -Command "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
    del "%PY_ZIP%"

    REM site-packages 활성화 (python311._pth 에서 '#import site' 주석 해제)
    powershell -NoProfile -Command ^
        "(Get-Content '%PYTHON_DIR%\python311._pth') -replace '#import site', 'import site' | Set-Content '%PYTHON_DIR%\python311._pth'"

    echo  [3/4] pip 설치 중...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%APP_DIR%_get_pip.py'"
    "%PYTHON%" "%APP_DIR%_get_pip.py" --no-warn-script-location -q
    del "%APP_DIR%_get_pip.py"
) else (
    echo  Python 이 이미 준비되어 있습니다.
)

echo  [4/4] 라이브러리 설치 중... (3~5분 소요)
echo         streamlit, openpyxl, pandas, numpy, holidays ...
echo.
"%PYTHON%" -m pip install -r "%APP_DIR%requirements_local.txt" --no-warn-script-location -q

if errorlevel 1 (
    echo.
    echo  오류: 라이브러리 설치 실패.
    echo  인터넷 연결을 확인하고 setup.bat 을 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

echo.
echo  =============================================
echo    설치 완료! 이제 실행.bat 을 더블클릭하세요.
echo  =============================================
echo.
pause
