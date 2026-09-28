# scripts/setup_firewall.ps1
# Configures Windows Defender Firewall for Project Brainuke Throne & Discovery Server

Write-Host "Configuring Windows Defender Firewall for Project Brainuke..." -ForegroundColor Cyan

# Remove stale rules if present
Remove-NetFirewallRule -DisplayName "Brainuke Throne HTTPS (8443)" -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "Brainuke Discovery HTTP (8080)" -ErrorAction SilentlyContinue

# Add Inbound Rule for HTTPS Port 8443
New-NetFirewallRule -DisplayName "Brainuke Throne HTTPS (8443)" `
    -Direction Inbound `
    -LocalPort 8443 `
    -Protocol TCP `
    -Action Allow `
    -Profile Any `
    -Description "Allows incoming HTTPS traffic from SerenityDroid Android extension"

# Add Inbound Rule for HTTP Port 8080
New-NetFirewallRule -DisplayName "Brainuke Discovery HTTP (8080)" `
    -Direction Inbound `
    -LocalPort 8080 `
    -Protocol TCP `
    -Action Allow `
    -Profile Any `
    -Description "Allows incoming HTTP traffic for Root CA certificate download"

Write-Host "Firewall rules for ports 8443 and 8080 successfully configured!" -ForegroundColor Green
