@echo off
REM ============================================================================
REM Solar Mining System - Windows Autostart
REM ============================================================================
REM 
REM This script automatically:
REM 1. Detects if QuickMiner is running (preferred)
REM 2. Falls back to Excavator if QuickMiner not found
REM 3. Starts solar-powered crypto mining automation
REM 
REM For Autostart: Place shortcut to this file in Windows Startup folder
REM Press Win+R, type: shell:startup
REM ============================================================================

echo.
echo ========================================
echo   Solar Mining System - Starting
echo ========================================
echo.
echo QuickMiner Detection: Automatic
echo Fallback: Excavator
echo.

cd /d "%~dp0"

REM Start PowerShell script (stays open for monitoring)
PowerShell.exe -NoExit -ExecutionPolicy Bypass -File ".\start_solar_mining.ps1"
