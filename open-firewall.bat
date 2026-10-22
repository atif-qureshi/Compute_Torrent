@echo off
echo ========================================================
echo   Opening ComputeTorrent Ports in Windows Firewall
echo ========================================================
netsh advfirewall firewall delete rule name="ComputeTorrent Petals DHT" >nul 2>&1
netsh advfirewall firewall delete rule name="ComputeTorrent Orchestrator" >nul 2>&1
netsh advfirewall firewall add rule name="ComputeTorrent Petals DHT" dir=in action=allow protocol=TCP localport=31331
netsh advfirewall firewall add rule name="ComputeTorrent Orchestrator" dir=in action=allow protocol=TCP localport=8001
echo.
echo [OK] Ports 31331 (Petals DHT) and 8001 (Orchestrator) are now open!
echo Laptops on the same Wi-Fi can now connect without being blocked.
echo.
pause
