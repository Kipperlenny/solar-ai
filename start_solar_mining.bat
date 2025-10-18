@echo off
REM Solar Mining Autostart - CMD Version
REM Startet PowerShell Script mit sichtbarem Fenster

echo.
echo ========================================
echo   Solar Mining System - Autostart
echo ========================================
echo.

cd /d "C:\Users\Lennart\test"

REM Starte PowerShell mit ExecutionPolicy Bypass (für Autostart)
PowerShell.exe -NoExit -ExecutionPolicy Bypass -File ".\start_solar_mining.ps1"
