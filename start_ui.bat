@echo off
title Project Brainuke - Cecilia Desktop Native UI
cd /d "%~dp0"
echo ========================================================
echo Launching Project Brainuke (Throne + Cecilia Desktop UI)
echo ========================================================

:: 1. Ensure ADB reverse tethering
adb reverse tcp:8443 tcp:8443 >nul 2>&1
adb reverse tcp:8080 tcp:8080 >nul 2>&1
adb reverse tcp:8081 tcp:8081 >nul 2>&1

:: 2. Ensure Throne Server is running
netstat -ano | findstr :8443 | findstr LISTENING >nul 2>&1
if errorlevel 1 (
    echo [Throne] Starting Throne Server in background...
    start /b python brainuke_throne\server\main.py
    timeout /t 2 /nobreak >nul 2>&1
)

:: 3. Launch UI
python brainuke_throne\ui_desktop\cecilia_ui.py
pause
