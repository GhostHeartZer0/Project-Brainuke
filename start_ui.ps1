# Project Brainuke - Desktop Native Cecilia-UI Launcher
Set-Location -Path $PSScriptRoot
Write-Host "========================================================" -ForegroundColor Green
Write-Host "Launching Project Brainuke (Throne + Cecilia Desktop UI)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

# Locate Python Interpreter
$pyCandidates = @(
    "$PSScriptRoot\.venv\Scripts\python.exe",
    "$PSScriptRoot\..\.venv\Scripts\python.exe",
    "$PSScriptRoot\..\..\..\.venv\Scripts\python.exe",
    "$PSScriptRoot\..\..\..\SerenityDev\.venv\Scripts\python.exe"
)
$pyExe = "python"
foreach ($cand in $pyCandidates) {
    if (Test-Path $cand) {
        $pyExe = (Resolve-Path $cand).Path
        break
    }
}

# 1. Ensure ADB reverse tethering for connected Android devices (ports 8443, 8080, 8081)
try {
    adb reverse tcp:8443 tcp:8443 2>$null
    adb reverse tcp:8080 tcp:8080 2>$null
    adb reverse tcp:8081 tcp:8081 2>$null
} catch {}

# 2. Ensure Throne Server (Port 8443) is running
$throneRunning = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
if (-not $throneRunning) {
    Write-Host "[Throne] Starting Throne Server in background using $pyExe..." -ForegroundColor Cyan
    Start-Process -FilePath $pyExe -ArgumentList "brainuke_throne/server/main.py" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# 3. Launch Desktop Native UI
& $pyExe "brainuke_throne/ui_desktop/cecilia_ui.py"
