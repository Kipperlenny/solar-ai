# Registers solar_hub.py as a Windows scheduled task that starts at logon
# (hidden, via pythonw) and starts it right away.
# Usage: powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$taskName = 'SolarHub'

if (-not (Test-Path $pythonw)) { throw "Missing $pythonw - create the venv first (see README)" }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$root\solar_hub.py`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Register-ScheduledTask -TaskName $taskName -Description 'Solar hub: SDongle (read-only) -> Shelly devices' `
    -Action $action -Trigger $trigger -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Task '$taskName' registered and started. Log: $root\logs\hub.log"
