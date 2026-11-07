@echo off
echo Adding Windows Firewall rules for ComputeTorrent Petals (Ports 31330 and 31331)...
netsh advfirewall firewall delete rule name="ComputeTorrent Petals" >nul 2>&1
netsh advfirewall firewall add rule name="ComputeTorrent Petals" dir=in action=allow protocol=TCP localport=31330,31331
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===================================================
    echo [SUCCESS] Ports 31330 and 31331 are now open in Windows Firewall!
    echo ===================================================
) else (
    echo.
    echo [ERROR] Failed to add firewall rule. Please run this as Administrator.
)
timeout /t 3
