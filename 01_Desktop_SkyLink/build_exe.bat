@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title SkyLink Desktop Pro - بناء ملف EXE

echo ============================================================
echo    SkyLink Desktop Pro   -   تحويل التطبيق إلى ملف EXE
echo ============================================================
echo.
echo هذه العملية تُنشئ ملفاً واحداً مستقلاً يعمل على أي ويندوز
echo بدون تثبيت بايثون ولا أي مكتبة. تستغرق 2 - 5 دقائق.
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
    pause
    exit /b 1
)
echo [1/5] بايثون: %PY%
echo.

REM ---------------- 2) تثبيت المتطلبات ----------------
echo [2/5] تجهيز المكتبات (مرة واحدة فقط)...
"%PY%" -m pip install --disable-pip-version-check --quiet --upgrade pip
"%PY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
"%PY%" -m pip install --disable-pip-version-check --quiet pyinstaller pillow
if errorlevel 1 (
    echo [خطأ] فشل تثبيت المتطلبات. تحقق من الإنترنت.
    pause
    exit /b 1
)
echo       تم.
echo.

REM ---------------- 3) الأيقونة ----------------
echo [3/5] تجهيز الأيقونة...
if not exist "assets\icon.ico" (
    "%PY%" "assets\make_icon.py"
)
if exist "assets\icon.ico" (echo       الأيقونة جاهزة.) else (echo       تنبيه: لا توجد أيقونة، سيُبنى الملف بدونها.)
echo.

REM ---------------- 4) عميل Flet المكتبي ----------------
echo [4/5] البحث عن عميل Flet المكتبي...
set "FLETCLIENT="
for /d %%D in ("%USERPROFILE%\.flet\client\flet-desktop-*") do (
    if exist "%%D\flet\flet.exe" set "FLETCLIENT=%%D\flet"
)
if defined FLETCLIENT (
    echo       وُجد: !FLETCLIENT!
    echo       سيُدمج داخل الملف = يعمل بلا إنترنت في أول تشغيل.
) else (
    echo       غير موجود حالياً.
    echo       سيُبنى الملف بحجم أصغر، ويُنزّل العميل عند أول تشغيل.
)
echo.

REM ---------------- 5) البناء ----------------
echo [5/5] جاري بناء الملف التنفيذي...
echo.

if defined FLETCLIENT (
    "%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name SkyLinkDesktopPro ^
        --icon "assets\icon.ico" ^
        --add-data "scrcpy;scrcpy" ^
        --add-data "!FLETCLIENT!;flet_client" ^
        --collect-all flet --collect-all flet_desktop ^
        skylink_desktop.py
) else (
    "%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name SkyLinkDesktopPro ^
        --icon "assets\icon.ico" ^
        --add-data "scrcpy;scrcpy" ^
        --collect-all flet --collect-all flet_desktop ^
        skylink_desktop.py
)

if exist "dist\SkyLinkDesktopPro.exe" (
    echo.
    echo ============================================================
    echo    تم البناء بنجاح
    echo ============================================================
    for %%F in ("dist\SkyLinkDesktopPro.exe") do echo    الملف: %%~fF
    for %%F in ("dist\SkyLinkDesktopPro.exe") do echo    الحجم: %%~zF بايت
    echo.
    echo    يمكنك نسخ هذا الملف إلى أي حاسوب ويندوز وتشغيله مباشرة.
    echo ============================================================
    echo.
    choice /c yn /n /m "هل تريد فتح مجلد الملف الآن؟ [y/n] "
    if !errorlevel! equ 1 start "" "dist"
) else (
    echo.
    echo [خطأ] لم يكتمل البناء. راجع الرسائل أعلاه.
    pause
)
endlocal
