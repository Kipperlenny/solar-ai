# Solar Mining System - Windows Autostart Guide

## 🚀 Autostart Setup

### Method 1: Windows Startup Folder (Recommended)

1. **Press:** `Win + R`
2. **Type:** `shell:startup` + Enter
3. **Create Shortcut:**
   - Right-click → "New" → "Shortcut"
   - Target: `C:\path\to\your\solar-ai\start_solar_mining.bat`
   - Name: "Solar Mining System"
4. **Done!** Script will start on next Windows login

### Method 2: Task Scheduler (Advanced)

For more control (e.g. delay, admin rights):

```powershell
# Run in PowerShell (as Administrator):
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoExit -ExecutionPolicy Bypass -File `"C:\path\to\your\solar-ai\start_solar_mining.ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "Solar Mining System" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Starts the Solar Mining System automatically on Windows login"
```

**Task Scheduler Advantages:**
- ✅ Startup delay possible (prevents boot overload)
- ✅ Admin rights optional
- ✅ Central management
- ✅ Logs in Task Scheduler

### Method 3: Registry (Not Recommended)

If Startup folder doesn't work:

```powershell
# PowerShell as Administrator:
$scriptPath = "C:\path\to\your\solar-ai\start_solar_mining.bat"
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "SolarMining" -Value $scriptPath
```

**Remove:**
```powershell
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "SolarMining"
```

## 📋 Manual Start Options

### Double-click file:
- `start_solar_mining.bat` - Simple start with CMD
- `start_solar_mining.ps1` - PowerShell (Right-click → "Run with PowerShell")

### From existing terminal:
```powershell
cd C:\path\to\your\solar-ai
.\start_solar_mining.bat
```

## 🔧 Troubleshooting

### PowerShell Execution Policy Error
```powershell
# Run as Administrator:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Script doesn't start automatically
1. Check Startup folder: `shell:startup`
2. Check Task Scheduler: `taskschd.msc`
3. Event Viewer for errors: `eventvwr.msc`

### Terminal closes immediately
- The `.bat` script uses `-NoExit` flag
- If needed, add `Read-Host "Press Enter"` at end of `.ps1`

## ⚙️ Customizations

### Add startup delay (in start_solar_mining.ps1):
```powershell
Write-Host "Waiting 30 seconds before start..." -ForegroundColor Yellow
Start-Sleep -Seconds 30
```

### Run as Administrator:
- Right-click on `.bat` → "Properties" → "Advanced" → "Run as administrator"

### Start minimized:
Change in Task Scheduler: "Run" → "Minimized"

## 📊 Check Status

After autostart you can verify everything is running:
- Terminal window should be open with live output
- CSV is being written: `logs\solar_data.csv`
- Errors are logged: `logs\errors.log`

## 🛑 Disable Autostart

**Startup Folder:**
1. `Win + R` → `shell:startup`
2. Delete shortcut

**Task Scheduler:**
```powershell
Unregister-ScheduledTask -TaskName "Solar Mining System" -Confirm:$false
```

**Registry:**
```powershell
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "SolarMining"
```
