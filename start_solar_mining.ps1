# Solar Mining Autostart Script
# Startet das Solar Mining System mit sichtbarem Terminal

# Wechsle ins Script-Verzeichnis
Set-Location -Path $PSScriptRoot

# Aktiviere Virtual Environment und starte Script
Write-Host "Starte Solar Mining System..." -ForegroundColor Green
Write-Host "Arbeitsverzeichnis: $(Get-Location)" -ForegroundColor Cyan
Write-Host "Python Environment: .venv" -ForegroundColor Cyan
Write-Host ""

# Starte mit aktiviertem venv
& ".\.venv\Scripts\python.exe" ".\solar_mining_api.py"

# Falls Script beendet wird, warte auf Tastendruck
Write-Host ""
Write-Host "Script beendet. Druecke eine Taste zum Schliessen..." -ForegroundColor Yellow
Read-Host "Druecke Enter zum Beenden"
