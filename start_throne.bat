@echo off
title Brainuke Throne Server
cd /d "%~dp0"
echo ========================================================
echo Starting Project Brainuke Throne Server (Ports 8080/8443)
echo ========================================================
:: Resolve Python Interpreter (local, onedir parent, or SerenityPC repo venv)
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

echo Using Python: %PY_EXE%
"%PY_EXE%" brainuke_throne\server\main.py
pause
