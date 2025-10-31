# GPU Safety & Thermal Management Guide

## Overview

The solar mining system now includes comprehensive safety features to prevent hardware damage and system crashes:

1. **Power Limiting** - Caps GPU power usage to prevent PSU overload
2. **Thermal Monitoring** - Tracks core and VRAM temperatures
3. **Automatic Throttling** - Reduces power when temperatures get too high
4. **Detailed Logging** - Records all thermal events for analysis

## Configuration

All settings can be configured via environment variables or directly in the code:

### Power Limits

```bash
# Default TDP limit (percentage of maximum)
GPU_POWER_LIMIT_TDP=85  # 85% TDP (recommended for stability)
```

- **Default: 85%** - Safe for 24/7 operation
- **Range: 50-100%** - Lower = safer, Higher = more performance
- **Recommendation**: Start at 85%, only increase if temps stay low

### Thermal Thresholds

```bash
# Core temperature targets (°C)
GPU_TEMP_TARGET=75        # Target temperature
GPU_TEMP_THROTTLE=80      # Start throttling here
GPU_TEMP_CRITICAL=85      # Emergency shutdown threshold

# VRAM temperature targets (°C)
GPU_VRAM_TEMP_TARGET=90   # Target VRAM temp
GPU_VRAM_TEMP_THROTTLE=95 # Start throttling VRAM
GPU_VRAM_TEMP_CRITICAL=100 # VRAM emergency threshold

# Monitoring interval
GPU_THERMAL_CHECK_INTERVAL=60  # Check every 60 seconds
```

## How It Works

### 1. Power Limiting (Startup)

When the mining script starts, it automatically applies the configured TDP limit to all GPUs:

```
🔋 Applying safe power limits (85% TDP)...
  ✓ GPU 0 power limit set to 85% TDP
  ✓ GPU 1 power limit set to 85% TDP
✓ Power limits applied to 2/2 GPU(s)
```

This prevents your PSU from being overloaded and reduces initial heat output.

### 2. Continuous Thermal Monitoring

Every 60 seconds (configurable), the system checks:
- Core temperature
- VRAM temperature  
- Fan speed
- Power usage
- GPU load

### 3. Automatic Throttling

The system responds to temperature changes automatically:

#### Normal Operation
- Temps below target → No action needed
- TDP remains at configured limit (e.g., 85%)

#### High Temperature (Throttle Start)
- Core temp ≥ 80°C **OR** VRAM temp ≥ 95°C
- System reduces TDP by 5% per 2°C over threshold
- Example: 82°C → Reduce TDP by 5% (85% → 80%)

```
🌡️  GPU 0 running hot: Core=82°C, VRAM=94°C
   Throttling TDP: 85% → 80%
```

#### Critical Temperature (Emergency)
- Core temp ≥ 85°C **OR** VRAM temp ≥ 100°C
- System immediately drops TDP to 50% (minimum)
- Logs critical event

```
🚨 CRITICAL TEMP on GPU 0: Core=85°C, VRAM=98°C
   Emergency throttling to 50% TDP!
```

#### Temperature Recovery
- When temps drop below target, TDP gradually increases
- +5% per check until back at configured limit

```
✅ GPU 0 temps normal: Core=72°C, VRAM=88°C
   Releasing throttle: 75% → 80%
```

## Monitoring & Logs

### Real-Time Display

During mining, you'll see thermal warnings in the console:

```
[123] 14:30:15
      ☀️  Solar Production:       1200 W
      🏠  House Consumption:       400 W
      ✨ Available Power:          800 W for mining
      ⛏️  Mining: ON (2 GPUs) | 85.2 MH/s
          GPU0: 45.1 MH/s (kawpow) | 72°C
          GPU1: 40.1 MH/s (kawpow) | 79°C

🌡️  GPU 1 running hot: Core=79°C, VRAM=92°C
   Throttling TDP: 85% → 80%
```

### Thermal Log File

All thermal events are logged to `logs/gpu_thermal.csv`:

```csv
timestamp,unix_timestamp,device_id,device_name,gpu_core_temp_c,gpu_vram_temp_c,gpu_fan_speed_percent,gpu_fan_rpm,gpu_power_usage_w,gpu_power_limit_w,gpu_tdp_percent,gpu_load_percent,gpu_mem_load_percent,gpu_core_clock_mhz,gpu_mem_clock_mhz,too_hot_flag,thermal_action,tdp_before,tdp_after,notes
2025-10-31 14:30:15,1730385015,0,GeForce RTX 5060 Ti,72,88,54,2100,153,180,85,100,95,2865,14001,0,normal,,,
2025-10-31 14:31:15,1730385075,1,GeForce GTX 1070 Ti,79,92,65,2450,144,180,85,100,98,1847,3802,0,throttle_start,85,80,Throttling: Core=79°C VRAM=92°C
```

### View Thermal Logs

Use the included viewer script for easy analysis:

```bash
# View all thermal events
python view_thermal_log.py

# Last 2 hours only
python view_thermal_log.py --hours=2

# Specific GPU only
python view_thermal_log.py --gpu=0

# Throttle events only (hide normal temps)
python view_thermal_log.py --throttle

# Combined filters
python view_thermal_log.py --hours=24 --gpu=1 --throttle
```

Output:
```
====================================================================================================
GPU THERMAL MONITORING LOG
====================================================================================================

📅 Showing events from last 2 hours
📊 Found 120 matching events
====================================================================================================

📋 THERMAL EVENTS:
----------------------------------------------------------------------------------------------------
Timestamp            GPU  Action             Core°C  VRAM°C  TDP%  Fan%  Notes                         
----------------------------------------------------------------------------------------------------
2025-10-31 14:30:15  GPU0 normal             72.0    88.0    85    54    
2025-10-31 14:31:15  GPU1 ⚠️  throttle_start   79.0    92.0    80    65    Throttling: Core=79°C VR
2025-10-31 14:32:15  GPU1 ⚠️  throttle_increase 81.0    94.0    75    70    Throttling: Core=81°C VR

====================================================================================================
📊 THERMAL STATISTICS
====================================================================================================

GPU 0 (GeForce RTX 5060 Ti):
  Core Temperature:
    Max:     75.0°C
    Average: 72.3°C
  VRAM Temperature:
    Max:     90.0°C
    Average: 88.5°C
  TDP Range: 85% - 85%
  Throttle Events: 0
  Critical Events: 0

GPU 1 (GeForce GTX 1070 Ti):
  Core Temperature:
    Max:     82.0°C
    Average: 79.1°C
  VRAM Temperature:
    Max:     95.0°C
    Average: 92.8°C
  TDP Range: 70% - 85%
  Throttle Events: 15
  Critical Events: 0
```

## Recommended Settings by Use Case

### Maximum Safety (24/7 Unattended)
```bash
GPU_POWER_LIMIT_TDP=75          # Very conservative
GPU_TEMP_TARGET=70
GPU_TEMP_THROTTLE=75
GPU_TEMP_CRITICAL=80
GPU_VRAM_TEMP_TARGET=85
GPU_VRAM_TEMP_THROTTLE=90
GPU_VRAM_TEMP_CRITICAL=95
```

### Balanced (Default)
```bash
GPU_POWER_LIMIT_TDP=85          # Good balance
GPU_TEMP_TARGET=75
GPU_TEMP_THROTTLE=80
GPU_TEMP_CRITICAL=85
GPU_VRAM_TEMP_TARGET=90
GPU_VRAM_TEMP_THROTTLE=95
GPU_VRAM_TEMP_CRITICAL=100
```

### Performance (Monitored Operation)
```bash
GPU_POWER_LIMIT_TDP=95          # Near maximum
GPU_TEMP_TARGET=80
GPU_TEMP_THROTTLE=85
GPU_TEMP_CRITICAL=90
GPU_VRAM_TEMP_TARGET=95
GPU_VRAM_TEMP_THROTTLE=100
GPU_VRAM_TEMP_CRITICAL=105
```

## Troubleshooting

### GPU Still Too Hot

1. **Increase fan speed** - Check case airflow
2. **Lower TDP further** - Try 75% or 70%
3. **Improve ventilation** - Add case fans
4. **Clean GPU** - Dust buildup reduces cooling
5. **Repaste GPU** - Thermal paste may be old

### Constant Throttling

If you see frequent throttling events:

1. **Lower initial TDP** - Start at 80% instead of 85%
2. **Reduce temperature thresholds** - Lower `GPU_TEMP_THROTTLE` to 75°C
3. **Check ambient temperature** - Room too hot?
4. **Verify fan operation** - Fans spinning properly?

### System Still Crashed

If you still experience crashes:

1. **Check PSU capacity** - May need bigger power supply
2. **Review Windows Event Logs** - `python analyze_data.py --events`
3. **Lower power even more** - Try 70% TDP
4. **Disable one GPU** - Test with single GPU first

## Safety Features Summary

✅ **Power Limiting** - Prevents PSU overload  
✅ **Temperature Monitoring** - Tracks core & VRAM temps  
✅ **Automatic Throttling** - Reduces power when hot  
✅ **Emergency Shutdown** - Drops to 50% TDP at critical temps  
✅ **Detailed Logging** - Full thermal history in CSV  
✅ **Easy Viewing** - Dedicated log viewer script  
✅ **Configurable** - All thresholds adjustable  
✅ **Smart Recovery** - Gradually restores power when temps normalize  

## Best Practices

1. **Start Conservative** - Use 85% TDP initially
2. **Monitor First Day** - Watch thermal logs closely
3. **Adjust Gradually** - Change TDP by 5% at a time
4. **Check Regularly** - Review `view_thermal_log.py` weekly
5. **Clean Hardware** - Dust GPUs every few months
6. **Improve Airflow** - Good case ventilation is key
7. **Use Ethernet** - WiFi adds latency to Modbus communication

## Technical Details

### API Endpoints Used

- `/devices_cuda` - Get GPU thermal status
- `/action/setpowerlimit?device=UUID&limit=TDP` - Set power limit

### Data Fields Monitored

- `gpu_temp` - Core temperature (°C)
- `__vram_temp` - VRAM temperature (°C)
- `gpu_fan_speed` - Fan speed (%)
- `gpu_fan_speed_rpm` - Fan speed (RPM)
- `gpu_power_usage` - Current power draw (W)
- `gpu_tdp_current` - Current TDP percentage
- `too_hot` - QuickMiner's overheat flag
- `gpu_load` - GPU utilization (%)
- `gpu_load_memctrl` - Memory controller load (%)

### Throttling Algorithm

```python
# Calculate overheat amount
core_overheat = max(0, core_temp - GPU_TEMP_THROTTLE)
vram_overheat = max(0, vram_temp - GPU_VRAM_TEMP_THROTTLE)
max_overheat = max(core_overheat, vram_overheat)

# Reduce TDP by 5% per 2°C over threshold
reduction = int(max_overheat / 2) * 5
new_tdp = max(50, current_tdp - reduction)

# Apply new limit
set_power_limit(device_id, tdp_percent=new_tdp)
```

## Support

If you experience issues:

1. Check `logs/errors.log` for errors
2. Run `python view_thermal_log.py --hours=24` to see thermal history
3. Review `logs/gpu_thermal.csv` for detailed data
4. Check Windows Event Viewer for system errors
5. Verify QuickMiner is running and API accessible

## Future Enhancements

Potential improvements:

- [ ] Email alerts for critical temps
- [ ] Automatic fan curve adjustment
- [ ] Machine learning based optimization
- [ ] Per-GPU temperature targets
- [ ] Thermal history graphs
- [ ] Integration with Home Assistant
