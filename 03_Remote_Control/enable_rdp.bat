@echo off
rem English only on purpose: Arabic text inside .bat breaks cmd parsing.
chcp 65001 >nul 2>&1
title MoMoLink Remote - Enable Remote Desktop (RDP)
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Thonny\python.exe" set "PY=%LOCALAPPDATA%\Programs\Thonny\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"

if not defined PY (
    echo [X] Python was not found.
    pause
    exit /b 1
)

%PY% "%~dp0momolink_admin.py" enable-rdp
endlocal
