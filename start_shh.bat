@echo off
setlocal enabledelayedexpansion
title SHH 1.0 - Windows AI Remote Bridge

:: Always run from the folder that contains this .bat file
cd /d "%~dp0"

echo ========================================================
echo     SHH 1.0 - Smart Host Hub (Windows AI Bridge)
echo ========================================================
echo.

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
echo [2/3] Checking and installing required dependencies...
%PY_CMD% -m pip install -r requirements.txt --quiet

echo.
echo [3/3] Starting SHH 1.0 Bridge and Integrated Tunnel...
echo.
%PY_CMD% -m shh start

echo.
pause
