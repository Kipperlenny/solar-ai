# Setup Autostart for Solar Mining System
# This script configures Windows to automatically start Solar Mining on boot

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Solar Mining Autostart Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

$solarBatPath = "$PSScriptRoot\start_solar_mining.bat"
$startupFolder = [Environment]::GetFolderPath("Startup")

# Create Solar Mining shortcut in Startup folder
Write-Host "Erstelle Autostart-Verknüpfung..." -ForegroundColor Yellow

$solarShortcut = "$startupFolder\Solar Mining.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($solarShortcut)
$Shortcut.TargetPath = $solarBatPath
$Shortcut.WorkingDirectory = "$PSScriptRoot"
$Shortcut.Description = "Solar Mining Automation (auto-detects QuickMiner)"
$Shortcut.Save()

Write-Host "   ✓ Verknüpfung erstellt" -ForegroundColor Green
Write-Host "     $solarShortcut" -ForegroundColor Gray

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "Autostart eingerichtet!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Was passiert beim Windows-Start:" -ForegroundColor Cyan
Write-Host "1. Solar Mining startet automatisch" -ForegroundColor White
Write-Host "2. Erkennt QuickMiner (falls läuft)" -ForegroundColor White
Write-Host "3. Oder startet Excavator (Fallback)" -ForegroundColor White
Write-Host ""
Write-Host "💡 Empfehlung für QuickMiner:" -ForegroundColor Yellow
Write-Host "   Aktiviere in QuickMiner: 'Mit Windows starten'" -ForegroundColor White
Write-Host "   Dann läuft QuickMiner immer vor diesem Script" -ForegroundColor White
Write-Host ""
Write-Host "Zum Testen jetzt:" -ForegroundColor Cyan
Write-Host "   .\start_solar_mining.bat" -ForegroundColor White
Write-Host ""
