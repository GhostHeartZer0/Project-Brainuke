@echo off
title Project Brainuke - Cecilia Desktop Native UI
cd /d "%~dp0"
echo ========================================================
echo Launching Project Brainuke (Throne + Cecilia Desktop UI)
echo ========================================================

:: 1. Resolve Python Interpreter (local, onedir parent, or SerenityPC repo venv)
set "PY_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0..\.venv\Scripts\python.exe"
) else if exist "%~dp0..\..\..\.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0..\..\..\.venv\Scripts\python.exe"
) else if exist "%~dp0..\..\..\SerenityDev\.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0..\..\..\SerenityDev\.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

:: 2. Ensure ADB reverse tethering
adb reverse tcp:8443 tcp:8443 >nul 2>&1
adb reverse tcp:8080 tcp:8080 >nul 2>&1
adb reverse tcp:8081 tcp:8081 >nul 2>&1

:: 3. Ensure Throne Server is running
netstat -ano | findstr :8443 | findstr LISTENING >nul 2>&1
if errorlevel 1 (
    echo [Throne] Starting Throne Server in background using %PY_EXE%...
    start /b "" "%PY_EXE%" brainuke_throne\server\main.py
    timeout /t 2 /nobreak >nul 2>&1
)

:: 4. Launch UI
"%PY_EXE%" brainuke_throne\ui_desktop\cecilia_ui.py
pause
