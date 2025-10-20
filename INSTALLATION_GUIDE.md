# Quick Setup Guide - Solar Mining Controller v2.0

## Initial Installation

### 1. Install Python Dependencies

```powershell
# Navigate to project directory
cd C:\path\to\your\solar-ai

# Activate virtual environment (if using one)
.venv\Scripts\Activate.ps1

# Install all required packages
pip install -r requirements.txt
```

### 2. Configure .env File

```powershell
# Copy example configuration
cp .env.example .env

# Edit with your settings
notepad .env
```

**Required settings:**
- `NICEHASH_WALLET` - Your NiceHash wallet address
- `EXCAVATOR_PATH` - Path to excavator.exe
- `INVERTER_HOST` - Your inverter IP address
- `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` - Your GPS coordinates

### 3. First Run

```powershell
# Test run
python solar_mining_api.py
```

**On first run, the script will:**
1. Check for updates (huawei-solar package and Excavator)
2. Connect to inverter
3. Start Excavator if not running
4. Begin monitoring solar power

## Troubleshooting First Run

### Import Error: No module named 'packaging'

```powershell
# Install in virtual environment
.venv\Scripts\python.exe -m pip install packaging
```

### Import Error: No module named 'GPUtil'

```powershell
# Install GPU monitoring tools
pip install GPUtil psutil
```

### Excavator Update Permission Denied

**Cause:** Excavator is already running

**Solution:**
1. Close Excavator manually
2. Restart the script
3. Or: Skip update and use existing version

### Connection Timeout

**Cause:** Another program accessing inverter (FusionSolar App, etc.)

**Solution:**
1. Close FusionSolar mobile app
2. Close any other monitoring software
3. Script will retry automatically every 30 seconds

## Auto-Update Behavior

### On Every Startup

The script automatically checks for updates:

1. **huawei-solar package** - Updates from PyPI if newer version available
2. **Excavator** - Downloads from GitHub if newer version available

### Disabling Auto-Update

Edit `solar_mining_api.py`, comment out in `main()` function:

```python
# check_and_update_huawei_solar()
# check_and_update_excavator(EXCAVATOR_PATH)
```

### Manual Updates

```powershell
# Update huawei-solar only
pip install --upgrade huawei-solar

# Update all packages
pip install --upgrade -r requirements.txt
```

## Testing the Installation

### 1. Check Imports

```powershell
python -c "import huawei_solar, GPUtil, psutil, packaging; print('OK')"
```

Should output: `OK`

### 2. Check Excavator Connection

```powershell
# Start Excavator manually first
python -c "import requests; print(requests.get('http://127.0.0.1:3456').json())"
```

Should output Excavator version info

### 3. Check Inverter Connection

```powershell
python -c "
import asyncio
from huawei_solar import HuaweiSolarBridge

async def test():
    bridge = await HuaweiSolarBridge.create('192.168.18.206', port=6607)
    power = await bridge.client.get('input_power')
    print(f'Solar Power: {power.value}W')
    await bridge.stop()

asyncio.run(test())
"
```

Should output current solar power

## Windows Service Setup (24/7 Operation)

### Using NSSM (Non-Sucking Service Manager)

```powershell
# Download NSSM from nssm.cc

# Install as service
nssm install SolarMining "C:\path\to\your\solar-ai\.venv\Scripts\python.exe"
nssm set SolarMining AppParameters "C:\path\to\your\solar-ai\solar_mining_api.py"
nssm set SolarMining AppDirectory "C:\path\to\your\solar-ai"
nssm set SolarMining Start SERVICE_AUTO_START

# Start service
nssm start SolarMining

# Check status
nssm status SolarMining

# View logs
Get-Content C:\path\to\your\solar-ai\logs\errors.log -Tail 50
```

### Using Task Scheduler

See `AUTOSTART_GUIDE.md` for detailed instructions.

## Updating from v1.x to v2.0

### What's New

- Continuous health monitoring (every 2 minutes)
- Immediate mining retry on failures (3 attempts within 30s)
- Auto-update for Excavator and huawei-solar
- Rotating error logs (5MB max, 5 backups)
- Excavator process logging

### Migration Steps

1. **Backup your configuration**
   ```powershell
   cp .env .env.backup
   cp logs\solar_data.csv logs\solar_data_backup.csv
   ```

2. **Update dependencies**
   ```powershell
   pip install --upgrade -r requirements.txt
   ```

3. **Test the new version**
   ```powershell
   python solar_mining_api.py
   ```

4. **Review new documentation**
   - `ENHANCED_STABILITY_UPDATE.md` - New features
   - `README.md` - Updated usage guide

### Rollback (if needed)

```powershell
# Restore old configuration
cp .env.backup .env

# Reinstall old version of huawei-solar
pip install huawei-solar==2.3.0

# Use git to checkout old version
git checkout v1.0 solar_mining_api.py
```

## Common Issues

### "Module not found" errors

**Solution:** Ensure virtual environment is activated
```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### High CPU usage

**Cause:** CHECK_INTERVAL too low

**Solution:** Set `CHECK_INTERVAL=120` in .env (2 minutes)

### Mining starts/stops too often

**Cause:** Confirmation thresholds too low

**Solution:** Increase in .env:
- `START_CONFIRMATIONS_NEEDED=5` (default: 3)
- `STOP_CONFIRMATIONS_NEEDED=7` (default: 5)

### GPU not detected

**Cause:** GPUtil doesn't support your GPU or drivers missing

**Solution:** Disable GPU monitoring:
```bash
GPU_CHECK_ENABLED=False
```

### Excavator keeps restarting

**Check logs:**
```powershell
Get-Content logs\excavator\excavator_err.log -Tail 50
Get-Content logs\errors.log -Tail 50
```

**Common causes:**
- Invalid wallet address
- Network issues
- GPU driver problems

## Performance Optimization

### For Maximum Uptime

```bash
# Reduce Modbus conflicts
CHECK_INTERVAL=120
ALARM_CHECK_INTERVAL=30

# Faster mining start
START_CONFIRMATIONS_NEEDED=2

# Slower mining stop (avoid false stops)
STOP_CONFIRMATIONS_NEEDED=7
```

### For Maximum Efficiency

```bash
# Higher power threshold (only mine with good solar)
MIN_POWER_TO_START=300
MIN_POWER_TO_KEEP=250

# More confirmations (avoid short mining sessions)
START_CONFIRMATIONS_NEEDED=5
```

## Monitoring & Maintenance

### Daily Checks

```powershell
# Check if service is running
Get-Process python -ErrorAction SilentlyContinue

# Check recent errors
Get-Content logs\errors.log -Tail 20

# Check mining status
Get-Content logs\solar_data.csv -Tail 5
```

### Weekly Analysis

```powershell
# Generate analysis plots
pip install pandas matplotlib
python analyze_data.py

# View plots
explorer logs\solar_mining_analysis.png
```

### Monthly Maintenance

1. Review log sizes (rotating logs should handle this automatically)
2. Check for software updates (automatic on startup)
3. Verify earnings on NiceHash dashboard
4. Review mining patterns and adjust thresholds if needed

## Getting Help

### Check Documentation

1. `README.md` - Overview and basic usage
2. `ENHANCED_STABILITY_UPDATE.md` - v2.0 features
3. `MODBUS_CONFLICT_GUIDE.md` - Connection issues
4. `LOGGING_AND_BUG_FIX.md` - Logging system

### Debug Mode

Enable detailed logging by checking `logs/errors.log`:
```powershell
Get-Content logs\errors.log -Tail 100 -Wait
```

### Report Issues

Include in bug reports:
1. Last 50 lines of `logs/errors.log`
2. Your `.env` configuration (remove wallet address!)
3. Python version: `python --version`
4. Package versions: `pip list | findstr "huawei-solar GPUtil psutil"`

---

**Version:** 2.0
**Last Updated:** October 2025
