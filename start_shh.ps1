<#
    SHH 1.0 - Windows PowerShell Launcher
    Usage:
        .\start_shh.ps1              # normal (standard user) mode
        .\start_shh.ps1 -Admin       # self-elevate with UAC, then start as Administrator
#>
param(
    [switch]$Admin
)

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "    SHH 1.0 - Smart Host Hub (Windows AI Bridge)" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Privilege detection
# ---------------------------------------------------------------------------
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    Write-Host "[PRIVILEGE] Administrator mode (UAC elevated)" -ForegroundColor Green
} else {
    Write-Host "[PRIVILEGE] Standard user mode" -ForegroundColor Yellow
    Write-Host "            Use  .\start_shh.ps1 -Admin  for full power." -ForegroundColor Yellow
}
Write-Host ""

# ---------------------------------------------------------------------------
# Optional self-elevation
# ---------------------------------------------------------------------------
if ($Admin -and -not $isAdmin) {
    Write-Host "[SHH] Requesting Administrator privileges (UAC prompt)..." -ForegroundColor Yellow
    $bat = Join-Path $PSScriptRoot "start_shh_admin.bat"
    if (Test-Path -LiteralPath $bat) {
        Start-Process -FilePath $bat -WorkingDirectory $PSScriptRoot -Verb RunAs
        Write-Host "[OK] Elevated window launched. You may close this one." -ForegroundColor Green
        exit 0
    }
    Write-Host "[ERROR] start_shh_admin.bat not found next to this script." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Locate Python
# ---------------------------------------------------------------------------
$pyCmd = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pyCmd = "py"
    } else {
        Write-Host "[ERROR] Python was not found in PATH." -ForegroundColor Red
        Write-Host "Please install Python 3.8+ from https://www.python.org/ and check 'Add to PATH'." -ForegroundColor Yellow
        Read-Host "Press Enter to exit..."
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Integrated tunnel engine (cloudflared.exe)
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "cloudflared.exe"))) {
    Write-Host "[1/3] Downloading integrated tunnel engine (cloudflared.exe)..." -ForegroundColor Yellow
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile (Join-Path $PSScriptRoot "cloudflared.exe") -UseBasicParsing
        Write-Host "[SUCCESS] Tunnel engine downloaded." -ForegroundColor Green
    } catch {
        Write-Host "[INFO] Tunnel download skipped (will use IP/SSH fallback)." -ForegroundColor Yellow
    }
} else {
    Write-Host "[1/3] Integrated Cloudflare Tunnel engine is ready." -ForegroundColor Green
}

Write-Host "[2/3] Installing/Verifying dependencies..." -ForegroundColor Yellow
& $pyCmd -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet

Write-Host "[3/3] Launching SHH 1.0 Bridge..." -ForegroundColor Green
Write-Host ""
& $pyCmd -m shh start
