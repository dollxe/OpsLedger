@echo off
chcp 65001 > nul

set APP_DIR=%~dp0
set SHORTCUT_NAME=대기운영일지.lnk
set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT_PATH=%DESKTOP%\%SHORTCUT_NAME%

echo  바탕화면에 '대기운영일지' 바로가기를 만드는 중...

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s = $ws.CreateShortcut('%SHORTCUT_PATH%');" ^
    "$s.TargetPath = '%APP_DIR%실행.bat';" ^
    "$s.WorkingDirectory = '%APP_DIR%';" ^
    "$s.IconLocation = '%SystemRoot%\System32\shell32.dll, 14';" ^
    "$s.Description = '대기배출시설 운영기록부 관리';" ^
    "$s.WindowStyle = 1;" ^
    "$s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo.
    echo  완료! 바탕화면에 '대기운영일지' 아이콘이 생성되었습니다.
    echo  이제 그 아이콘을 더블클릭하면 앱이 실행됩니다.
) else (
    echo.
    echo  바로가기 생성에 실패했습니다.
    echo  실행.bat 파일을 직접 바탕화면으로 복사해서 사용하세요.
)

echo.
pause
