@echo off
title ComputeTorrent - Provider Node
cd /d "%~dp0"

echo ========================================================
echo        ComputeTorrent Volunteer Provider Node
echo ========================================================
echo.

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

:: Ensure dependencies are installed
echo Checking required Python dependencies...
python -c "import customtkinter, websockets, psutil, PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo.
echo Starting Provider Application UI...
python main.py
if errorlevel 1 (
    echo.
    echo Provider node stopped with error code %errorlevel%.
    pause
)
