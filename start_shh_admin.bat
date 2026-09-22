@echo off
setlocal enabledelayedexpansion
title SHH 1.0 - Administrator Mode Launcher

:: Always operate inside the folder that contains this file
cd /d "%~dp0"

echo ========================================================
echo     SHH 1.0 - ADMINISTRATOR MODE LAUNCHER
echo ========================================================
echo.

:: ---------------------------------------------------------------
:: Step 1: are we already elevated?
:: ---------------------------------------------------------------
set "SHH_IS_ADMIN="
for /f "delims=" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "([System.Security.Principal.WindowsPrincipal][System.Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)" 2^>nul') do set "SHH_IS_ADMIN=%%A"
if not defined SHH_IS_ADMIN (
    fltmc >nul 2>&1 && set "SHH_IS_ADMIN=True"
)

if /i "%SHH_IS_ADMIN%"=="True" goto :run_elevated

:: ---------------------------------------------------------------
:: Step 2: not elevated -> relaunch THIS file with the runas verb
:: ---------------------------------------------------------------
echo [SHH] Administrator privileges are required.
echo [SHH] A Windows UAC window will pop up - please click [YES].
echo.
echo       After you click Yes, a NEW elevated window opens and runs SHH.
echo       This current window can be closed safely.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"

if errorlevel 1 (
    echo.
    echo [WARN] Elevation was cancelled or blocked by policy.
    echo [INFO] Starting SHH in STANDARD USER mode instead...
    echo.
    timeout /t 3 >nul
    call "%~dp0start_shh.bat"
    exit /b %errorlevel%
)

echo.
echo [OK] Elevated SHH window launched. You can close this window.
timeout /t 5 >nul
exit /b 0

:: ---------------------------------------------------------------
:: Step 3: we are Administrator -> hand over to the normal launcher
:: ---------------------------------------------------------------
:run_elevated
echo [PRIVILEGE] Confirmed: running as ADMINISTRATOR
echo [SHH] Administrator extras enabled:
echo       - Auto-open Windows Firewall inbound ports 18888 / 2222
echo       - Silent elevated commands (no UAC popup per command)
echo       - netsh port forwarding / portproxy available
echo.
call "%~dp0start_shh.bat" elevated
exit /b %errorlevel%
