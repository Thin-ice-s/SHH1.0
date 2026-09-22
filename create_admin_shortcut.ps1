<#
    SHH 1.0 - Create a "Run as administrator" shortcut

    Creates two shortcuts that ALWAYS start SHH in Administrator mode
    (no need to right-click -> Run as administrator every time):
        1. On the Windows Desktop
        2. Inside the SHH folder

    Usage (normal PowerShell is fine, the shortcut itself holds the admin flag):
        powershell -ExecutionPolicy Bypass -File .\create_admin_shortcut.ps1
#>

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$targetBat = Join-Path $scriptDir "start_shh_admin.bat"

if (-not (Test-Path -LiteralPath $targetBat)) {
    Write-Host "[ERROR] start_shh_admin.bat not found in $scriptDir" -ForegroundColor Red
    exit 1
}

function New-AdminShortcut {
    param([string]$ShortcutPath)

    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($ShortcutPath)
    $lnk.TargetPath = $targetBat
    $lnk.WorkingDirectory = $scriptDir
    $lnk.Description = "SHH 1.0 - Windows AI Bridge (Administrator mode)"
    $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,77"
    $lnk.WindowStyle = 1
    $lnk.Save()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null

    # Byte 0x15 bit 0x20 = "Run as administrator" flag inside the .lnk file
    $bytes = [System.IO.File]::ReadAllBytes($ShortcutPath)
    $bytes[0x15] = $bytes[0x15] -bor 0x20
    [System.IO.File]::WriteAllBytes($ShortcutPath, $bytes)
}

$targets = @(
    (Join-Path $scriptDir "SHH 1.0 (Admin).lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "SHH 1.0 (Admin).lnk")
)

foreach ($t in $targets) {
    try {
        New-AdminShortcut -ShortcutPath $t
        Write-Host "[OK] Created shortcut: $t" -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Could not create $t : $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Done. Double-click 'SHH 1.0 (Admin)' anywhere:" -ForegroundColor Cyan
Write-Host "  - Windows still shows the UAC prompt once (that is a Windows security requirement)."
Write-Host "  - SHH then runs with full Administrator rights for its whole lifetime."
