@echo off
title Stop ComputeTorrent
cd /d "%~dp0"

echo ========================================================
echo            Stopping ComputeTorrent Stack
echo ========================================================
echo.

echo Stopping Docker containers...
docker compose -f docker-compose.local.yml --profile petals down
if errorlevel 1 (
    echo [ERROR] Could not stop containers cleanly.
) else (
    echo [OK] All ComputeTorrent containers stopped successfully.
    echo Database data has been preserved.
)

echo.
echo ========================================================
echo Stack has been stopped.
echo ========================================================
echo.
pause
