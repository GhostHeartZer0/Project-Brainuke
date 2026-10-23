# Project Brainuke Throne Server Launch Script
Set-Location -Path $PSScriptRoot
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting Project Brainuke Throne Server (Ports 8080/8443)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
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

Write-Host "Using Python: $pyExe" -ForegroundColor Yellow
& $pyExe "brainuke_throne/server/main.py"
