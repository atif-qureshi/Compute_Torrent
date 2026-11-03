@echo off
title ComputeTorrent - Public Ngrok Tunnel
cd /d "%~dp0"

echo ========================================================
echo        Starting Global Tunnel for ComputeTorrent
echo ========================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-ngrok.ps1

echo.
pause
