@echo off
title ComputeTorrent Launcher
cd /d "%~dp0"

echo ========================================================
echo            ComputeTorrent - All-in-One Launcher
echo ========================================================
echo.

:: 1. Check Docker Desktop status
echo [1/4] Checking Docker Desktop status...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running!
    echo Please start Docker Desktop first, then double-click this file again.
    echo.
    pause
    exit /b 1
)
echo [OK] Docker Desktop is running.
echo.

:: 2. Start Docker Compose Stack (Petals, Orchestrator, Swarm, Postgres, Portal)
:: 2. Start Docker Compose Stack (Petals, Orchestrator, Swarm, Postgres, Portal)
echo [2/4] Syncing active Wi-Fi/LAN IP and starting ComputeTorrent containers...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-host-ip.ps1"
set "LAN_IP="
for /f "tokens=1,* delims==" %%A in ('findstr /b "COMPUTETORRENT_PROVIDER_LAN_HOST=" "%~dp0.env" 2^>nul') do set "LAN_IP=%%B"
docker compose -f docker-compose.local.yml --profile petals up -d
if errorlevel 1 (
    echo [ERROR] Failed to start Docker containers.
    pause
    exit /b 1
)
echo [OK] All containers started successfully.
echo.

:: 3. Launch the Web Portal in default browser
echo [3/4] Opening Submitter Portal in browser (http://localhost:3000)...
ping -n 3 127.0.0.1 >nul
start http://localhost:3000
echo.

:: 4. Start the Provider Desktop Application
echo [4/4] Starting Provider Node Desktop UI...
start "ComputeTorrent Provider" python desktop\main.py
echo.

echo ========================================================
echo   ComputeTorrent is now running!
echo ========================================================
echo  * Web Portal:       http://localhost:3000
echo  * Portal Password:  ComputeTorrentAdmin2026!
echo  * Provider URL:     ws://127.0.0.1:8001/ws/seeder
if defined LAN_IP echo  * LAN Provider URL: ws://%LAN_IP%:8001/ws/seeder
echo  * Enrollment Token: local-volunteer-join
echo.
echo You can close this command window anytime without stopping the services.
echo To stop everything, double-click 'Stop-All.bat'.
echo ========================================================
echo.
pause
