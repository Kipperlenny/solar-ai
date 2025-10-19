# Solar Mining Controller

Automatic crypto mining with solar surplus. Starts mining only when enough solar power is available and automatically pauses when GPU is used by other programs.

## Features

- ⚡ **Solar-controlled Mining** - Starts/stops based on grid feed-in
- 🎮 **GPU Monitoring** - Pauses automatically for games/Stable Diffusion
- 🔄 **Auto-Restart** - Excavator restarts automatically on issues
- 💰 **Earnings Tracking** - Shows current BTC earnings
- 🌦️ **Weather Integration** - Cloud cover, temperature, solar radiation (Open-Meteo API)
- 📊 **Comprehensive Logging** - CSV data for analysis + error logs
- 🌍 **Multilingual** - English/German CLI support (via LANGUAGE environment variable)

## Prerequisites

- Python 3.10+
- Huawei Solar Inverter (SUN2000 series) on network
- NiceHash Excavator installed
- NVIDIA GPU (tested with GTX 1070 Ti)

## Installation

```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install packages
pip install huawei-solar GPUtil psutil requests python-dotenv
```

## Configuration

**Important:** Configuration is done via `.env` file (not in code!)

```powershell
# 1. Copy .env.example to .env
cp .env.example .env

# 2. Customize .env with your values
notepad .env
```

**Important settings in `.env`:**

```bash
# Language (Supported: en, de)
LANGUAGE=en

# Excavator path
EXCAVATOR_PATH=H:\miner\excavator.exe

# Inverter IP
INVERTER_HOST=192.168.18.206
INVERTER_PORT=6607

# NiceHash Wallet (REQUIRED!)
NICEHASH_WALLET=YOUR_WALLET.worker_name

# GPS coordinates for weather (customize!)
WEATHER_LATITUDE=37.6931
WEATHER_LONGITUDE=-0.8481

# Power thresholds (optional customization)
MIN_POWER_TO_START=200
MIN_POWER_TO_KEEP=150
CHECK_INTERVAL=120        # Check every 2 minutes (reduces Modbus conflicts)
ALARM_CHECK_INTERVAL=30   # Check alarms every 30 seconds

# GPU monitoring (optional disable)
GPU_CHECK_ENABLED=True
GPU_USAGE_THRESHOLD=10   # % - Pause on GPU usage

# Weather API (Open-Meteo - free!)
WEATHER_ENABLED=True
WEATHER_LATITUDE=40.4168    # Your GPS coordinates
WEATHER_LONGITUDE=-3.7038
```

## Starting

```powershell
# In project folder
python solar_mining_api.py
```

The script:
1. Starts Excavator automatically
2. Connects to inverter
3. Monitors solar feed-in every 30s
4. Starts mining at ≥200W feed-in (after 3x confirmation)
5. Stops mining at <150W (after 5x confirmation)
6. Pauses when GPU is used by other programs

**Stop:** `Ctrl+C`

## Output

```
[  5] 10:30:00
      ☀️  Solar:        1250 W
      🏠 Consumption:    480 W (House)
      📤 Grid Export:    770 W (to grid)
      ✨ Available:      770 W (for mining)
      ⛏️  Mining:        🟢 RUNNING
      📈 Hashrate:      27.12 MH/s
      ⏱️  Session:       15m 30s
      💰 Unpaid:        0.00012345 BTC
      🌡️  Weather:       23.5°C, ☁️ 35%, ☀️ 680 W/m²
```

## Logging

### Data Log: `logs/solar_data.csv`
Every 30 seconds:
- **Solar:** Production, feed-in, consumption, string data (PV1/PV2)
- **Grid:** 3-phase details (voltage, current, power)
- **Mining:** Status, hashrate, GPU temperature, GPU usage
- **Inverter:** Temperature, efficiency, daily/total yield
- **Weather:** Temperature, cloud cover, wind, solar radiation (W/m²)
- **Battery:** Charge/discharge power, State of Charge (if available)

**Use for:**
- Excel/Google Sheets
- Create graphs (Solar vs. cloud cover!)
- ML training (prediction models)
- Long-term analysis

### Error Log: `logs/errors.log`
Detailed error information:
- API connection problems
- Excavator crashes
- Inverter connection errors
- Complete tracebacks

## Tools

### Analyze Data
```powershell
# Statistics + plots (requires pandas + matplotlib)
pip install pandas matplotlib
python analyze_data.py
```

Creates:
- `logs/solar_mining_analysis.png` - Overview (solar, mining, hashrate, GPU)
- `logs/daily_pattern.png` - Daily patterns (hourly averages)
- `logs/ml_training_data.csv` - Prepared for ML

### View Errors
```powershell
python view_errors.py        # Last 24h
python view_errors.py 6      # Last 6h
```

## GPU Monitoring

Automatic pause for:
- 🎮 **Gaming**: Rocket League, CS2, Valorant, etc.
- 🎨 **Stable Diffusion**: Detects Python processes with SD keywords
- 🎬 **Video/3D**: Blender, Premiere, After Effects, etc.

**Add custom programs:**
```python
# In solar_mining_api.py, line ~175
gpu_intensive_processes = [
    'RocketLeague.exe',
    'MyGame.exe',  # <-- Add here
]
```

**Disable feature:**
```bash
GPU_CHECK_ENABLED=False
```

## Windows Service (24/7)

Install as service with NSSM:

```powershell
# Download NSSM: nssm.cc
nssm install SolarMining "C:\path\to\your\solar-ai\.venv\Scripts\python.exe"
nssm set SolarMining AppParameters "C:\path\to\your\solar-ai\solar_mining_api.py"
nssm set SolarMining AppDirectory "C:\path\to\your\solar-ai"
nssm set SolarMining Start SERVICE_AUTO_START

# Start service
nssm start SolarMining
```

## Troubleshooting

### "Excavator not responding"
- Excavator restarts automatically
- Check: `logs/errors.log`
- Manual: Close Excavator and restart script

### "Inverter connection" error
- IP correct? `INVERTER_HOST="192.168.18.206"`
- Inverter reachable? `ping 192.168.18.206`
- Port open? Check firewall

### Mining doesn't start
- Enough feed-in? Needs ≥200W for 3x30s
- GPU free? Other programs active?
- Check console output + `logs/errors.log`

### CSV file too large
```powershell
# Archive old data
Move-Item logs\solar_data.csv logs\solar_data_$(Get-Date -Format 'yyyy-MM').csv
# New CSV header will be created automatically
```

## Technical Details

**Hardware:**
- Huawei SUN2000-6KTL-L1 Inverter
- NVIDIA GeForce GTX 1070 Ti (~180W, ~27 MH/s)

**Software:**
- NiceHash Excavator v1.9.x
- Modbus TCP (Port 6607)
- Excavator API (TCP Port 3456)

**Algorithm:** DaggerHashimoto (Ethereum)

**Hysteresis:**
- 3x confirmations (90s) to start
- 5x confirmations (150s) to stop
- Prevents constant on/off with fluctuating solar

## Files

```
test/
├── solar_mining_api.py       # Main script (Windows)
├── solar_mining_pi.py        # Monitoring script (Raspberry Pi)
├── solar_core.py             # Shared components
├── translations.py           # Multilingual support (EN/DE)
├── analyze_data.py           # Data analysis tool
├── view_errors.py            # Error log viewer
├── README.md                 # This file
├── AUTOSTART_GUIDE.md        # Windows autostart setup
├── MULTILANG_GUIDE.md        # Multilingual implementation guide
├── .env                      # Configuration (create from .env.example)
├── logs/
│   ├── solar_data.csv        # Data log
│   └── errors.log            # Error log
└── .venv/                    # Python virtual environment
```

## Documentation

- **[AUTOSTART_GUIDE.md](AUTOSTART_GUIDE.md)** - Windows autostart setup guide
- **[MULTILANG_GUIDE.md](MULTILANG_GUIDE.md)** - Multilingual implementation details
- **[README_RASPBERRY_PI.md](README_RASPBERRY_PI.md)** - Raspberry Pi monitoring setup
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment and setup instructions
- **[QUICKSTART_PI.md](QUICKSTART_PI.md)** - Quick start guide for Raspberry Pi

## Contributing

Contributions are welcome! This project follows professional development standards:

**Code Quality Standards:**
- ✅ **Language:** All code, comments, and docstrings in English
- ✅ **Style:** PEP 8 compliant Python
- ✅ **Architecture:** Follow existing patterns (see `solar_core.py` for shared components)
- ✅ **Translations:** Add new languages via `translations.py` (see [MULTILANG_GUIDE.md](MULTILANG_GUIDE.md))

**How to Contribute:**

1. **Fork** the repository
2. **Create** a feature branch
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes**
   - Write English code/comments
   - Add translations if user-facing
   - Test on your hardware
4. **Commit** with clear messages
   ```bash
   git commit -m 'feat: Add support for XYZ inverter'
   ```
5. **Push** to your branch
   ```bash
   git push origin feature/amazing-feature
   ```
6. **Open** a Pull Request

**Areas for Contribution:**
- 🔌 Support for other inverter brands (Fronius, SolarEdge, etc.)
- 🌍 Additional language translations
- 📊 Enhanced data analysis features
- 🎮 More GPU-intensive process detection
- 🐛 Bug fixes and optimizations
- 📖 Documentation improvements

**Questions?** Open an issue or discussion on GitHub!

## License

**Solar Mining Controller** - Copyright (c) 2025 Lennart Kipper

Licensed under [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

**License Summary:**
- ✅ **Free for personal and hobby use** - Use, modify, and share freely
- ✅ **Share improvements** - Derivatives must use the same license
- ✅ **Give credit** - Must attribute original author
- ❌ **No commercial use** - Cannot sell, monetize, or use commercially
- 💼 **Commercial licensing available** - Contact author for commercial options

See [LICENSE](LICENSE) for full terms.

**No Warranty:** This software is provided "as is", without warranty of any kind.
