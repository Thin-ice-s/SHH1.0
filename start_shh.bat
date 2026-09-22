@echo off
setlocal enabledelayedexpansion
title SHH 1.0 - Windows AI Remote Bridge

:: Always run from the folder that contains this .bat file
cd /d "%~dp0"

echo ========================================================
echo     SHH 1.0 - Smart Host Hub (Windows AI Bridge)
echo ========================================================
echo.

:: ---------------------------------------------------------------
:: Detect privilege level (Administrator or Standard user)
:: ---------------------------------------------------------------
set "SHH_IS_ADMIN="
for /f "delims=" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "([System.Security.Principal.WindowsPrincipal][System.Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)" 2^>nul') do set "SHH_IS_ADMIN=%%A"
if not defined SHH_IS_ADMIN (
    fltmc >nul 2>&1 && set "SHH_IS_ADMIN=True"
)
if /i "%SHH_IS_ADMIN%"=="True" (
    echo [PRIVILEGE] Administrator mode  ^(UAC elevated^)
) else (
    echo [PRIVILEGE] Standard user mode
    echo             For full power run:  start_shh_admin.bat    or:  start_shh.bat admin
)
echo.

:: ---------------------------------------------------------------
:: Optional auto-elevation: "start_shh.bat admin"
:: ---------------------------------------------------------------
if /i "%~1"=="admin" if /i not "%SHH_IS_ADMIN%"=="True" (
    echo [SHH] Requesting Administrator privileges ^(UAC prompt^)...
    echo       A NEW elevated window will open. You may close this one.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -WorkingDirectory '%~dp0' -Verb RunAs"
    if errorlevel 1 (
        echo [WARN] Elevation cancelled. Continuing in standard user mode...
        echo.
    ) else (
        echo [OK] Elevated window launched.
        timeout /t 3 >nul
        exit /b 0
    )
)

:: 1. Check Python installation
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python was not found on your system!
        echo Please install Python 3.8+ from https://www.python.org/
        echo Make sure to check "Add python.exe to PATH" during installation.
        echo.
        pause
        exit /b 1
    ) else (
        set "PY_CMD=py"
    )
) else (
    set "PY_CMD=python"
)

:: 2. Check and auto-download cloudflared.exe if missing
if not exist "cloudflared.exe" (
    echo [1/3] cloudflared.exe not found. Downloading integrated tunnel engine...
    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe' -UseBasicParsing" >nul 2>&1
    if exist "cloudflared.exe" (
        echo [SUCCESS] Integrated Cloudflare Tunnel engine downloaded!
    ) else (
        echo [INFO] Skipped tunnel download. Will use native dynamic IP/SSH fallback.
    )
) else (
    echo [1/3] Integrated Cloudflare Tunnel engine is ready.
)

echo.
echo [TIP] Stable tunnel: SHH supervises cloudflared and keeps the SAME address
echo       while it runs. For a PERMANENT address (never changes) use one of:
echo         python -m shh start --tunnel tailscale
echo         python -m shh start --tunnel ngrok --tunnel-domain your-name.ngrok-free.app --ngrok-token TOKEN
echo         python -m shh start --tunnel cloudflare_token --cloudflare-token TOKEN --tunnel-domain your.domain.com
echo       Details: TUNNEL_STABILITY.md   Large files: FILE_TRANSFER.md
echo.
echo [2/3] Checking and installing required dependencies...
%PY_CMD% -m pip install -r requirements.txt --quiet

echo.
echo [3/3] Starting SHH 1.0 Bridge and Integrated Tunnel...
echo.
%PY_CMD% -m shh start

echo.
pause
