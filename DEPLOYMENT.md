# Deployment Guide# 📦 Deployment-Checkliste



Complete deployment instructions for both Windows and Raspberry Pi systems.## Windows → Raspberry Pi Transfer



## 📋 Overview### Dateien für Raspberry Pi:

```

This project consists of two main systems:✅ setup_raspberry.sh

✅ solar_mining_pi.py

1. **Windows Mining Controller** (`solar_mining_api.py`)✅ start_solar_mining_pi.sh

   - Automatic crypto mining with solar surplus✅ install_autostart.sh

   - GPU monitoring and pause functionality✅ requirements_pi.txt

   - Excavator integration✅ README_RASPBERRY_PI.md

✅ QUICKSTART_PI.md

2. **Raspberry Pi Monitor** (`solar_mining_pi.py`)```

   - Pure monitoring system

   - Email notifications### PowerShell Befehl (von Windows):

   - Lightweight for 24/7 operation```powershell

# Alle Dateien auf einmal kopieren

## 🪟 Windows Deployment$PI_IP = "192.168.x.x"  # Anpassen!

$files = @(

### Prerequisites    "setup_raspberry.sh",

    "solar_mining_pi.py",

- Windows 10/11    "start_solar_mining_pi.sh",

- Python 3.10+    "install_autostart.sh",

- NVIDIA GPU    "requirements_pi.txt",

- NiceHash Excavator installed    "README_RASPBERRY_PI.md",

- Huawei Solar Inverter on network    "QUICKSTART_PI.md"

)

### Installation Steps

foreach ($file in $files) {

1. **Clone or download repository**    scp $file pi@${PI_IP}:~/

   ```powershell}

   cd C:\Users\YourName```

   git clone https://github.com/Kipperlenny/solar-ai.git test

   cd test### SSH zum Pi und Installation:

   ``````bash

ssh pi@192.168.x.x

2. **Create virtual environment**chmod +x setup_raspberry.sh

   ```powershell./setup_raspberry.sh

   python -m venv .venvcd ~/solar-mining

   .venv\Scripts\Activate.ps1nano .env  # EMAIL_* konfigurieren!

   ```./start_solar_mining_pi.sh  # Testen

sudo ./install_autostart.sh  # Autostart

3. **Install dependencies**```

   ```powershell

   pip install huawei-solar GPUtil psutil requests python-dotenv## Windows Autostart

   ```

### Dateien für Windows:

4. **Configure .env**```

   ```powershell✅ start_solar_mining.bat

   cp .env.example .env✅ start_solar_mining.ps1

   notepad .env✅ AUTOSTART_ANLEITUNG.md

   ``````



   **Required settings:**### Installation:

   ```bash1. `Win + R` → `shell:startup`

   # Language2. Verknüpfung zu `start_solar_mining.bat` erstellen

   LANGUAGE=en3. Fertig!

   

   # Excavator## Checkliste vor Deployment

   EXCAVATOR_PATH=H:\miner\excavator.exe

   ### Windows-System:

   # Inverter- [ ] `.env` konfiguriert (Inverter, NiceHash, Excavator)

   INVERTER_HOST=192.168.18.206- [ ] Virtual Environment erstellt

   - [ ] Packages installiert: `pip install -r requirements.txt`

   # NiceHash- [ ] Script getestet: `python solar_mining_api.py`

   NICEHASH_WALLET=YOUR_WALLET.worker_name- [ ] Autostart-Verknüpfung erstellt

   

   # Weather### Raspberry Pi:

   WEATHER_LATITUDE=40.4168- [ ] Pi hat feste IP-Adresse (oder DHCP-Reservation)

   WEATHER_LONGITUDE=-3.7038- [ ] SSH-Zugriff funktioniert

   ```- [ ] Dateien kopiert

- [ ] `setup_raspberry.sh` ausgeführt

5. **Test run**- [ ] `.env` bearbeitet (E-Mail!)

   ```powershell- [ ] Gmail App-Passwort erstellt

   python solar_mining_api.py- [ ] Script getestet: `./start_solar_mining_pi.sh`

   ```- [ ] Autostart installiert: `sudo ./install_autostart.sh`

- [ ] Service läuft: `sudo systemctl status solar-mining`

6. **Setup autostart** (optional)

   - See [AUTOSTART_GUIDE.md](AUTOSTART_GUIDE.md)### E-Mail Test:

   - Or use Windows Task Scheduler```bash

   - Or install as Windows Service with NSSMcd ~/solar-mining

source .venv/bin/activate

### Windows Service Setup (NSSM)python3 << EOF

from solar_mining_pi import EmailNotifier

```powershellimport os

# Download NSSM from nssm.ccfrom dotenv import load_dotenv

nssm install SolarMining "C:\Users\Lennart\test\.venv\Scripts\python.exe"load_dotenv()

nssm set SolarMining AppParameters "C:\Users\Lennart\test\solar_mining_api.py"email = EmailNotifier()

nssm set SolarMining AppDirectory "C:\Users\Lennart\test"if email.enabled:

nssm set SolarMining AppStdout "C:\Users\Lennart\test\logs\service.log"    email.send_email('Setup-Test', 'Solar Monitoring System erfolgreich installiert!')

nssm set SolarMining AppStderr "C:\Users\Lennart\test\logs\errors.log"    print('✓ Test-E-Mail gesendet!')

nssm set SolarMining Start SERVICE_AUTO_STARTelse:

    print('✗ E-Mail nicht aktiviert in .env')

# Start serviceEOF

nssm start SolarMining```

```

## Post-Installation

## 🥧 Raspberry Pi Deployment

### Windows:

### Prerequisites- [ ] PC neustarten → Script sollte automatisch starten

- [ ] Terminal bleibt offen und zeigt Ausgabe

- Raspberry Pi 3B+ or newer- [ ] CSV wird geschrieben: `logs\solar_data.csv`

- Raspberry Pi OS (Bullseye or newer)- [ ] Mining startet bei genug Solar-Power

- Network connection

- Huawei Solar Inverter on network### Raspberry Pi:

- [ ] Pi neustarten: `sudo reboot`

### Quick Setup- [ ] Nach Boot: `sudo systemctl status solar-mining` → sollte "active (running)" zeigen

- [ ] Logs prüfen: `tail -f ~/solar-mining/logs/system.log`

Use the automated setup script:- [ ] CSV wird geschrieben: `~/solar-mining/logs/solar_data.csv`

- [ ] Bei Alarm → E-Mail kommt an

```bash

# Copy files to Pi## Monitoring

scp setup_raspberry.sh solar_mining_pi.py solar_core.py translations.py requirements_pi.txt pi@<pi-ip>:~/

### Täglich prüfen:

# SSH to Pi- Windows: Terminal-Fenster zeigt aktuelle Werte

ssh pi@<pi-ip>- Pi: `journalctl -u solar-mining -n 20` zeigt letzte 20 Zeilen



# Run setup### Wöchentlich prüfen:

chmod +x setup_raspberry.sh- CSV-Dateigröße (sollte ca. 1 MB pro Woche sein)

./setup_raspberry.sh- Fehler-Log: `tail logs/errors.log`

```

### Bei Problemen:

### Manual Setup1. Prüfe Netzwerk-Verbindung zum Inverter

2. Prüfe `errors.log`

1. **Install dependencies**3. Bei Pi: `sudo systemctl status solar-mining`

   ```bash4. Bei Windows: Schau ins Terminal-Fenster

   sudo apt update

   sudo apt install python3-pip python3-venv## Backup-Strategie

   ```

### CSV-Daten sichern (empfohlen):

2. **Create project directory**```bash

   ```bash# Raspberry Pi - Cronjob für tägliches Backup

   mkdir ~/solar-miningcrontab -e

   cd ~/solar-mining# Füge hinzu:

   ```0 3 * * * rsync -a ~/solar-mining/logs/*.csv /media/usb-backup/solar/

```

3. **Create virtual environment**

   ```bash### Windows:

   python3 -m venv .venv- Manuell: Kopiere `logs\solar_data.csv` regelmäßig

   source .venv/bin/activate- Oder: Google Drive / Dropbox in `logs\` Ordner

   ```

## Updates

4. **Install packages**

   ```bash### Windows:

   pip install -r requirements_pi.txt```powershell

   ```# Neues Script holen (z.B. von Git)

git pull

5. **Configure .env**# Oder manuell ersetzen

   ```bash# Service neustarten: Schließe Terminal und starte neu

   cp .env.example .env```

   nano .env

   ```### Raspberry Pi:

```bash

   **Required settings:**cd ~/solar-mining

   ```bash# Neue Datei kopieren (z.B. via scp)

   # Languagesudo systemctl restart solar-mining

   LANGUAGE=en```

   

   # Inverter## Deinstallation

   INVERTER_HOST=192.168.18.206

   ### Windows:

   # Email- Lösche Verknüpfung aus Autostart-Ordner

   EMAIL_ENABLED=true- Lösche Projekt-Ordner

   EMAIL_FROM=your-email@gmail.com

   EMAIL_TO=your-email@gmail.com### Raspberry Pi:

   EMAIL_PASSWORD=app-password```bash

   # Service stoppen und deaktivieren

   # Weathersudo systemctl stop solar-mining

   WEATHER_LATITUDE=37.6931sudo systemctl disable solar-mining

   WEATHER_LONGITUDE=-0.8481sudo rm /etc/systemd/system/solar-mining.service

   ```sudo systemctl daemon-reload



6. **Test run**# Dateien löschen (optional)

   ```bashrm -rf ~/solar-mining

   ./start_solar_mining_pi.sh```

   ```

7. **Install systemd service**
   ```bash
   sudo ./install_autostart.sh
   ```

## 🔧 Configuration Reference

### Common Settings (Both Systems)

```bash
# Language (en = English, de = German)
LANGUAGE=en

# Inverter connection
INVERTER_HOST=192.168.18.206
INVERTER_PORT=6607

# Data logging interval
CHECK_INTERVAL=30  # seconds

# Alarm check interval
ALARM_CHECK_INTERVAL=5  # seconds

# Weather API (Open-Meteo - free)
WEATHER_ENABLED=true
WEATHER_LATITUDE=40.4168
WEATHER_LONGITUDE=-3.7038
```

### Windows-Specific Settings

```bash
# Excavator configuration
EXCAVATOR_PATH=H:\miner\excavator.exe
EXCAVATOR_REGION=eu  # or usa
EXCAVATOR_API_PORT=3456

# NiceHash wallet
NICEHASH_WALLET=YOUR_WALLET_ADDRESS.worker_name

# Mining thresholds
MIN_POWER_TO_START=200  # Watts
MIN_POWER_TO_KEEP=150   # Watts

# GPU monitoring
GPU_CHECK_ENABLED=true
GPU_USAGE_THRESHOLD=10  # Percent
GPU_CHECK_INTERVAL=5    # Seconds
```

### Raspberry Pi-Specific Settings

```bash
# Email notifications
EMAIL_ENABLED=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient@email.com
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=app-password

# Daily summary
EMAIL_DAILY_SUMMARY=true
EMAIL_DAILY_SUMMARY_TIME=18:00

# Email on events
EMAIL_ON_ALARM=true
EMAIL_ON_ERROR=true
```

## 🧪 Testing

### Test Inverter Connection

```powershell
# Windows
python -c "from solar_core import InverterConnection; conn = InverterConnection('192.168.18.206'); print(conn.read_solar_production())"
```

```bash
# Raspberry Pi
python3 -c "from solar_core import InverterConnection; conn = InverterConnection('192.168.18.206'); print(conn.read_solar_production())"
```

### Test Email (Pi only)

```bash
cd ~/solar-mining
source .venv/bin/activate
python3 -c "from solar_core import EmailNotifier; notifier = EmailNotifier(); notifier.send_email('Test Subject', 'Test message')"
```

### Test Weather API

```powershell
# Windows
python -c "from solar_core import WeatherAPI; api = WeatherAPI(40.4168, -3.7038); print(api.get_weather())"
```

### Test Translations

```powershell
# Test English
$env:LANGUAGE="en"; python -c "from translations import t; print(t('system_title'))"

# Test German
$env:LANGUAGE="de"; python -c "from translations import t; print(t('system_title'))"
```

## 📊 Monitoring

### Check Logs

**Windows:**
```powershell
# Data log
Get-Content logs\solar_data.csv -Tail 10

# Error log
Get-Content logs\errors.log -Tail 20
```

**Raspberry Pi:**
```bash
# Service logs
journalctl -u solar-mining -f

# Data log
tail -f ~/solar-mining/logs/solar_data.csv

# Error log
tail -f ~/solar-mining/logs/errors.log
```

### Analyze Data

```powershell
# Install analysis tools
pip install pandas matplotlib

# Run analysis
python analyze_data.py
```

This creates:
- `logs/solar_mining_analysis.png` - Overview charts
- `logs/daily_pattern.png` - Daily patterns
- `logs/ml_training_data.csv` - ML-ready dataset

## 🔄 Updates

### Windows

```powershell
cd C:\Users\Lennart\test
git pull
pip install -r requirements.txt --upgrade

# Restart service or script
```

### Raspberry Pi

```bash
cd ~/solar-mining
git pull
source .venv/bin/activate
pip install -r requirements_pi.txt --upgrade
sudo systemctl restart solar-mining
```

## 🛡️ Security

### Protect .env File

```bash
# Linux/Pi
chmod 600 .env

# Windows - Remove inheritance and grant only current user access
icacls .env /inheritance:r /grant:r "%USERNAME%:F"
```

### Email Security

- Always use app-specific passwords (never your main password)
- Enable 2FA on email account
- Limit EMAIL_TO to trusted addresses
- Consider using dedicated monitoring email account

### Network Security

- Keep inverter on isolated VLAN if possible
- Use firewall rules to limit access
- Regularly update Raspberry Pi OS: `sudo apt update && sudo apt upgrade`

## 📈 Performance Tuning

### Windows

- Adjust `CHECK_INTERVAL` to reduce CPU usage
- Disable weather if not needed
- Use SSD for log files if available

### Raspberry Pi

- Use Raspberry Pi 4 for better performance
- Increase `CHECK_INTERVAL` if CPU usage is high
- Consider log rotation for long-term operation
- Use quality SD card (Class 10 or better)

## 🆘 Troubleshooting

See main documentation:
- [README.md](README.md) - Windows system
- [README_RASPBERRY_PI.md](README_RASPBERRY_PI.md) - Pi system
- [QUICKSTART_PI.md](QUICKSTART_PI.md) - Quick Pi setup

## 📝 License

Private use. No warranty.
