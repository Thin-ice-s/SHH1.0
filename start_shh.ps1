# SHH 1.0 - Windows PowerShell Launcher
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "    SHH 1.0 - Smart Host Hub (Windows AI Bridge)" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
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

Write-Host "[1/2] Installing/Verifying dependencies..." -ForegroundColor Yellow
& $pyCmd -m pip install -r requirements.txt

Write-Host "[2/2] Launching SHH 1.0 Bridge..." -ForegroundColor Green
Write-Host ""
& $pyCmd -m shh start
