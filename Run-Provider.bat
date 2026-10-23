@echo off
title ComputeTorrent Provider Node
cd /d "%~dp0"
echo ========================================================
echo   ComputeTorrent Provider Desktop Application
echo ========================================================
echo Starting provider node UI...
python desktop\main.py
if errorlevel 1 (
    echo.
    echo Provider node exited with error code %errorlevel%.
    pause
)
