@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title SkyLink Desktop Pro

echo ============================================================
echo    SkyLink Desktop Pro   -   تشغيل التطبيق
echo ============================================================
echo.

REM ---------------- 1) العثور على بايثون ----------------
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Thonny\python.exe" set "PY=%LOCALAPPDATA%\Programs\Thonny\python.exe"
)
if not defined PY (
    echo [خطأ] لم أجد بايثون على هذا الحاسوب.
    echo نزّله من: https://www.python.org/downloads/
    echo وأثناء التثبيت ضع علامة على: Add Python to PATH
    echo.
    pause
    exit /b 1
)
echo [1/2] بايثون: %PY%

REM ---------------- 2) التأكد من مكتبة الواجهة ----------------
"%PY%" -c "import flet" >nul 2>nul
if errorlevel 1 (
    echo [2/2] تثبيت مكتبات التشغيل لأول مرة... قد تستغرق دقيقة.
    "%PY%" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [خطأ] فشل تثبيت المكتبات. تأكد من اتصال الإنترنت ثم أعد المحاولة.
        pause
        exit /b 1
    )
) else (
    echo [2/2] المكتبات جاهزة.
)

echo.
echo تشغيل التطبيق... (أغلق نافذة التطبيق لإيقافه)
echo.
"%PY%" skylink_desktop.py
if errorlevel 1 (
    echo.
    echo [خطأ] توقف التطبيق بكود %errorlevel%
    pause
)
endlocal
