# Project Brainuke - Desktop Native Cecilia-UI Launcher
Set-Location -Path $PSScriptRoot
Write-Host "========================================================" -ForegroundColor Green
Write-Host "Launching Project Brainuke (Throne + Cecilia Desktop UI)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

# 1. Ensure ADB reverse tethering for connected Android devices (ports 8443, 8080, 8081)
try {
    adb reverse tcp:8443 tcp:8443 2>$null
    adb reverse tcp:8080 tcp:8080 2>$null
    adb reverse tcp:8081 tcp:8081 2>$null
} catch {}

# 2. Ensure Throne Server (Port 8443) is running
$throneRunning = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
if (-not $throneRunning) {
    Write-Host "[Throne] Starting Throne Server in background..." -ForegroundColor Cyan
    Start-Process -FilePath "python" -ArgumentList "brainuke_throne/server/main.py" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# 3. Launch Desktop Native UI
python brainuke_throne/ui_desktop/cecilia_ui.py
