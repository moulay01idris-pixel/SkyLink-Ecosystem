@echo off
rem English only on purpose: Arabic text inside .bat breaks cmd parsing.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title MoMoLink Desktop Pro

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
    echo [X] Python was not found on this computer.
    echo     Install it from python.org and tick "Add Python to PATH".
    pause
    exit /b 1
)

%PY% "%~dp0momolink_launch.py"
if errorlevel 1 pause
endlocal
