@echo off
title Brainuke Throne Server
cd /d "%~dp0"
echo ========================================================
echo Starting Project Brainuke Throne Server (Ports 8080/8443)
echo ========================================================
python brainuke_throne\server\main.py
pause
