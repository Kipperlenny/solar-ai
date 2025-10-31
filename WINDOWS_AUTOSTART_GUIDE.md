# Windows Autostart Setup Guide

## Overview

This guide explains how to set up both QuickMiner and the Solar Mining script to automatically start when Windows boots.

## Key Concept: Startup Synchronization

**Important**: QuickMiner needs to start AND begin mining BEFORE our script can take control.

The script now includes intelligent startup detection that waits for:
1. ✅ QuickMiner process to launch
2. ✅ Excavator API to become available  
3. ✅ GPUs to be detected
4. ✅ DAG files to build (1-2 minutes)
5. ✅ Mining workers to start

**Default wait time**: 120 seconds (2 minutes)

## Setup Steps

### 1. Configure QuickMiner for Auto-Mining

QuickMiner must be configured to automatically start mining on launch:

1. Open QuickMiner
2. Go to **Settings** → **General**
3. Enable: **"Start mining when QuickMiner starts"**
4. Enable: **"Start QuickMiner when Windows starts"** (optional but recommended)
5. Click **Save**

### 2. Add QuickMiner to Windows Startup (if not done in step 1)

**Option A: Via QuickMiner Settings**
- Use the setting from step 1.4 above

**Option B: Manual Startup Folder**
1. Press `Win + R`
2. Type: `shell:startup`
3. Press Enter
4. Create shortcut to QuickMiner:
   - Right-click → New → Shortcut
   - Browse to: `H:\miner\NiceHashQuickMiner.exe` (adjust path)
   - Name it: "NiceHash QuickMiner"

### 3. Add Solar Mining Script to Windows Startup

1. Press `Win + R`
2. Type: `shell:startup`
3. Press Enter
4. Create shortcut to the batch file:
   - Right-click → New → Shortcut
   - Browse to: `C:\Users\Lennart\solar-ai\start_solar_mining.bat`
   - Name it: "Solar Mining Automation"

### 4. Configure Startup Delay (Recommended)

To ensure QuickMiner starts before the script:

**Option A: Task Scheduler (Recommended)**

1. Press `Win + R`, type `taskschd.msc`, press Enter
2. Click **Create Basic Task**
3. Name: "Solar Mining Automation"
4. Trigger: **When I log on**
5. Action: **Start a program**
6. Program: `C:\Users\Lennart\solar-ai\start_solar_mining.bat`
7. Click **Finish**
8. Right-click the task → **Properties**
9. Go to **Triggers** tab → **Edit**
10. Click **Advanced settings**
11. Enable: **Delay task for:** `30 seconds`
12. Click **OK**

This gives QuickMiner a 30-second head start, then the script's built-in wait handles the rest.

**Option B: Simple Delay in Batch File**

Edit `start_solar_mining.bat` to add a delay:

```batch
@echo off
echo Waiting 30 seconds for QuickMiner to start...
timeout /t 30 /nobreak > nul
echo Starting Solar Mining Automation...
cd /d "%~dp0"
PowerShell.exe -NoExit -ExecutionPolicy Bypass -File ".\start_solar_mining.ps1"
```

### 5. Test the Setup

**Test before relying on autostart:**

1. Close QuickMiner and the script if running
2. Restart Windows
3. After login, you should see:
   - QuickMiner starts first
   - After ~30 seconds, Solar script starts
   - Script displays:
     ```
     ⏳ WAITING FOR QUICKMINER TO START
     ⏳ [0s] Waiting for QuickMiner API...
     ✅ [15s] QuickMiner API available (Excavator v1.9.7.0)
     ✅ [18s] GPUs detected: 0: GeForce RTX 5060 Ti, 1: GeForce GTX 1070 Ti
     ⏳ [25s] Workers exist but not mining yet (DAG building?)...
     ✅ [95s] Mining active: GPU0:kawpow, GPU1:kawpow
     ✅ QUICKMINER FULLY STARTED AND MINING
     Total startup time: 95 seconds
     ```
4. Script then applies power limits and begins monitoring

## Configuration

### Adjust Wait Time

If QuickMiner takes longer to start (e.g., slow SSD, many GPUs):

**In script** (edit `solar_mining_api.py`):
```python
QUICKMINER_STARTUP_WAIT = int(os.getenv("QUICKMINER_STARTUP_WAIT", "180"))  # 3 minutes
```

**Or via environment variable**:
1. Press `Win + R`, type `sysdm.cpl`, press Enter
2. Go to **Advanced** → **Environment Variables**
3. Under **User variables**, click **New**
4. Variable name: `QUICKMINER_STARTUP_WAIT`
5. Variable value: `180` (seconds)
6. Click **OK**

### Startup Behavior

The script will:
- ✅ Wait up to 2 minutes for QuickMiner to start mining
- ✅ Check every 5 seconds for progress
- ✅ Show detailed status messages
- ✅ Continue even if timeout (with warning)
- ✅ Apply power limits once QuickMiner is ready
- ✅ Take control and manage mining based on solar power

## Startup Sequence Timeline

**Optimal autostart sequence:**

```
00:00 - Windows boots, user logs in
00:05 - QuickMiner auto-starts (via startup folder or Task Scheduler)
00:35 - Solar script starts (30 second delay via Task Scheduler)
00:35 - Script: "Waiting for QuickMiner API..."
00:50 - Script: "QuickMiner API available"
00:53 - Script: "GPUs detected"
01:05 - Script: "Workers exist but not mining yet (DAG building?)"
02:10 - Script: "Mining active: GPU0:kawpow, GPU1:kawpow"
02:10 - Script: "QuickMiner fully started and mining"
02:11 - Script applies 85% TDP power limits
02:12 - Script connects to solar inverter
02:15 - Script begins monitoring and control
```

**Total startup time**: ~2-3 minutes from Windows login to full operation

## Troubleshooting

### Script Times Out Waiting for QuickMiner

**Symptoms:**
```
⚠️  TIMEOUT WAITING FOR QUICKMINER
QuickMiner did not fully start after 120 seconds
```

**Solutions:**
1. **Increase wait time** - Set `QUICKMINER_STARTUP_WAIT=180` (3 minutes)
2. **Check QuickMiner settings** - Ensure "Start mining when QuickMiner starts" is enabled
3. **Check QuickMiner logs** - Look for errors in QuickMiner
4. **Check GPU drivers** - Outdated drivers can slow startup
5. **Free up disk space** - DAG file creation needs space
6. **Disable antivirus temporarily** - Some AVs slow miner startup

### Script Starts Before QuickMiner

**Symptoms:**
```
⏳ [0s] Waiting for QuickMiner API...
⏳ [5s] Waiting for QuickMiner API...
... continues for 120 seconds, then timeout
```

**Solutions:**
1. **Add startup delay** - Use Task Scheduler method with 30-60 second delay
2. **Remove script from startup folder** - Use only Task Scheduler with delay
3. **Manual QuickMiner start** - Add QuickMiner to startup, not the script

### QuickMiner Doesn't Auto-Start Mining

**Symptoms:**
```
✅ QuickMiner API available
✅ GPUs detected
⏳ Waiting for mining to start...
⏳ Waiting for mining to start...
... continues until timeout
```

**Solutions:**
1. **Check QuickMiner settings** - "Start mining when QuickMiner starts" must be ON
2. **Check optimization profile** - Ensure "Auto" profile is active
3. **Manually start once** - Start mining in QuickMiner, let it save the state
4. **Check NiceHash account** - Ensure wallet address is configured
5. **Check firewall** - May be blocking NiceHash connection

### Script Says "QuickMiner may not be fully ready"

**This is a warning, not an error.** The script will continue but may not work correctly.

**Check:**
1. Open QuickMiner GUI - Is mining actually running?
2. Check workers - Are GPUs showing hashrate?
3. Review script output - What step failed?

**Common causes:**
- DAG building took longer than expected (normal for first start)
- Network issues connecting to NiceHash pool
- GPU driver crash during startup

### Both Start But Script Doesn't Control Mining

**Symptoms:**
- QuickMiner runs and mines
- Script runs and monitors solar
- But script doesn't stop/start mining based on solar power

**Solutions:**
1. **Check API port** - Script must detect QuickMiner API on port 18000
2. **Check API auth** - Ensure `nhqm.conf` has correct auth token
3. **Review logs** - Check `logs/errors.log` for API errors
4. **Test manually** - Run script while QuickMiner is already mining

## Advanced Configuration

### Run Script as Different User

If running as a different user (e.g., service account):

1. Update startup folder path for that user
2. Or use Task Scheduler and set user account
3. Ensure user has permissions to:
   - Read `nhqm.conf`
   - Write to `logs/` folder
   - Access QuickMiner API (localhost:18000)

### Multiple GPU Rigs

If running multiple rigs:

1. Each rig needs its own script instance
2. Each script monitors its own inverter (or shared inverter with different ports)
3. Configure different `DEVICE_ID` for each rig
4. Use Task Scheduler to stagger start times (Rig1: +30s, Rig2: +60s, etc.)

### Headless/Remote Operation

For remote/headless servers:

1. Use Task Scheduler instead of startup folder
2. Set "Run whether user is logged on or not"
3. Store credentials in Task Scheduler
4. Configure QuickMiner to run as Windows service (if available)

## Verification Checklist

Before considering autostart configured correctly:

- [ ] QuickMiner auto-starts on Windows boot
- [ ] QuickMiner automatically begins mining
- [ ] Script starts 30-60 seconds after QuickMiner
- [ ] Script successfully waits for QuickMiner to be ready
- [ ] Script displays "QuickMiner fully started and mining"
- [ ] Script applies power limits (85% TDP by default)
- [ ] Script connects to solar inverter
- [ ] Script begins monitoring and control
- [ ] Script stops/starts mining based on solar availability
- [ ] All of above survives a Windows reboot

## Example Successful Startup Log

```
Windows Login: 08:00:00

QuickMiner starts: 08:00:05
[QuickMiner initializing...]

Solar Script starts: 08:00:35
========================================
  Solar Mining System - Starting
========================================

⏳ WAITING FOR QUICKMINER TO START
⏳ [0s] Waiting for QuickMiner API...
⏳ [5s] Waiting for QuickMiner API...
⏳ [10s] Waiting for QuickMiner API...
✅ [15s] QuickMiner API available (Excavator v1.9.7.0)
✅ [18s] GPUs detected: 0: GeForce RTX 5060 Ti, 1: GeForce GTX 1070 Ti
⏳ [23s] Waiting for mining to start...
⏳ [28s] Workers exist but not mining yet (DAG building?)...
⏳ [88s] Workers exist but not mining yet (DAG building?)...
✅ [93s] Mining active: GPU0:kawpow, GPU1:kawpow

✅ QUICKMINER FULLY STARTED AND MINING
Total startup time: 93 seconds

🔋 Applying safe power limits (85% TDP)...
  ✓ GPU 0 power limit set to 85% TDP
  ✓ GPU 1 power limit set to 85% TDP
✓ Power limits applied to 2/2 GPU(s)

🔌 Connecting to inverter 192.168.18.206:6607...
✅ Inverter connection success
✅ Connection test successful (Solar: 1250W)

⚡ SOLAR MINING AUTOMATION v2.0
GPU Devices: 0, 1
Algorithm: kawpow
Miner: QuickMiner
Mining active: Yes
Solar: 1250W | Available: 850W

🔄 Monitoring started...
```

## Support

If you continue having startup issues:

1. Check `logs/errors.log` for detailed error messages
2. Run script manually first to ensure it works
3. Test QuickMiner auto-start separately from script
4. Use Task Scheduler logs to debug startup timing
5. Consider increasing `QUICKMINER_STARTUP_WAIT` to 180-300 seconds for first boot after Windows updates

## Summary

✅ QuickMiner must start and begin mining BEFORE script takes control  
✅ Script includes smart wait (up to 2 minutes) for QuickMiner startup  
✅ Use Task Scheduler with 30-60 second delay for best results  
✅ Script verifies QuickMiner is fully ready before proceeding  
✅ Configure "Start mining when QuickMiner starts" in QuickMiner settings  
✅ Test thoroughly before relying on autostart
