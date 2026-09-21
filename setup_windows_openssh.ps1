# SHH 1.0 - Windows Native OpenSSH Server Setup Script
# Please run in PowerShell as Administrator

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  SHH 1.0 - Windows Native OpenSSH Server Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Install OpenSSH Server capability
$capability = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($capability.State -ne "Installed") {
    Write-Host "[1/3] Installing Windows OpenSSH.Server capability..." -ForegroundColor Yellow
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
} else {
    Write-Host "[1/3] OpenSSH.Server capability is already installed." -ForegroundColor Green
}

# 2. Configure sshd service
Write-Host "[2/3] Configuring sshd service for automatic startup..." -ForegroundColor Yellow
Set-Service -Name sshd -StartupType 'Automatic'
Start-Service sshd

# 3. Configure Windows Firewall
Write-Host "[3/3] Configuring Windows Firewall inbound rule..." -ForegroundColor Yellow
if (!(Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
}

Write-Host ""
Write-Host "[SUCCESS] Windows OpenSSH Server is active on port 22!" -ForegroundColor Green
Read-Host "Press Enter to exit..."
