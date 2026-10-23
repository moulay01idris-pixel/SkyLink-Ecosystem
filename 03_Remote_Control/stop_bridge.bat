@echo off
rem English only on purpose: Arabic text inside .bat breaks cmd parsing.
chcp 65001 >nul 2>&1
title MoMoLink Remote - Stop the bridge
setlocal

echo Stopping MoMoLink Remote bridge...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*momolink_bridge.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('  stopped PID ' + $_.ProcessId) }"
echo.
echo Done. Port 8756 is now free.
timeout /t 3 >nul
endlocal
