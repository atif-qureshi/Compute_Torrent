@echo off
title ComputeTorrent - Global Coordinator Tunnel (Cloudflare)
color 0b
cls
echo ========================================================
echo   ComputeTorrent Global Coordinator Tunnel (Cloudflare)
echo ========================================================
echo.
echo [1/2] Make sure your Coordinator is running on port 8001:
echo       docker compose -f docker\docker-compose.yml up -d
echo.
echo [2/2] Starting Cloudflare Global Tunnel...
echo.
echo ========================================================
echo  LOOK BELOW FOR YOUR FREE CLOUDFLARE LINK:
echo  Example: https://xxxx-xxxx-xxxx.trycloudflare.com
echo.
echo  Copy that link into the Provider App on ANY internet connection!
echo  (And use join code: local-volunteer-join)
echo ========================================================
echo.

"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8001
pause
