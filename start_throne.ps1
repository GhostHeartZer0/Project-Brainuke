# Project Brainuke Throne Server Launch Script
Set-Location -Path $PSScriptRoot
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting Project Brainuke Throne Server (Ports 8080/8443)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
python brainuke_throne/server/main.py
