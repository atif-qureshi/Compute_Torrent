@echo off
title Sync Windows Clock with Google NTP
cd /d "%~dp0"

echo ========================================================
echo   Syncing Windows Clock with Google Time Server
echo ========================================================
echo.

w32tm /config /manualpeerlist:"time.google.com,0x1 pool.ntp.org,0x1" /syncfromflags:manual /reliable:yes /update
net start w32time >nul 2>&1
w32tm /resync /force

echo.
echo If it says 'The command completed successfully', your clock is synced!
echo.
pause
