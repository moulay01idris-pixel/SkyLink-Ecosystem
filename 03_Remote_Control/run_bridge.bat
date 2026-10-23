@echo off
rem English only on purpose: Arabic text inside .bat breaks cmd parsing.
chcp 65001 >nul 2>&1
title SkyLink Remote
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem ---------- locate python ----------
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Thonny\python.exe" set "PY=%LOCALAPPDATA%\Programs\Thonny\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

if not defined PY (
    echo [X] Python was not found on this computer.
    echo     Install it from python.org then run this file again.
    pause
    exit /b 1
)

rem ---------- make sure packages exist ----------
%PY% -c "import fastapi, uvicorn, qrcode" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages, one time only...
    %PY% -m pip install --quiet --disable-pip-version-check fastapi uvicorn qrcode pillow
)

rem ---------- open firewall port 8756 for the home network only ----------
%PY% "%~dp0skylink_admin.py" firewall --no-wait

rem ---------- run the bridge (browser opens automatically) ----------
%PY% "%~dp0skylink_bridge.py"

echo.
echo Bridge stopped.
pause
endlocal
