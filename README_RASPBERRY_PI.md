# Solar Monitoring System - Raspberry Pi Edition# Solar Monitoring System - Raspberry Pi Edition



Monitoring system for Huawei Solar Inverter with email notifications.Monitoring-System für Huawei Solar Inverter mit E-Mail-Benachrichtigungen.



## 🎯 Features## 🎯 Features



- ✅ **Complete Solar Monitoring** (production, grid, consumption)- ✅ **Vollständiges Solar-Monitoring** (Produktion, Grid, Verbrauch)

- ✅ **Email Notifications** for alarms and critical errors- ✅ **E-Mail-Benachrichtigungen** bei Alarmen und kritischen Fehlern

- ✅ **Daily Summary** via email (optional)- ✅ **Tägliche Zusammenfassung** per E-Mail (optional)

- ✅ **Weather Integration** (Open-Meteo API)- ✅ **Wetter-Integration** (Open-Meteo API)

- ✅ **CSV Logging** for data analysis- ✅ **CSV-Logging** für Datenanalyse

- ✅ **Automatic Start** on boot- ✅ **Automatischer Start** beim Boot

- ✅ **Self-Installation** on first run- ✅ **Selbst-Installation** beim ersten Start

- 🌍 **Multilingual** (English/German via LANGUAGE env variable)

## 📦 Installation auf Raspberry Pi

## 📦 Installation on Raspberry Pi

### 1. Dateien auf Raspberry Pi kopieren

### 1. Copy Files to Raspberry Pi

```bash

```bash# Von Windows zu Pi (PowerShell):

# From Windows to Pi (PowerShell):scp setup_raspberry.sh pi@<raspberry-ip>:~/

scp setup_raspberry.sh pi@<raspberry-ip>:~/scp solar_mining_pi.py pi@<raspberry-ip>:~/

scp solar_mining_pi.py pi@<raspberry-ip>:~/scp start_solar_mining_pi.sh pi@<raspberry-ip>:~/

scp solar_core.py pi@<raspberry-ip>:~/scp install_autostart.sh pi@<raspberry-ip>:~/

scp translations.py pi@<raspberry-ip>:~/scp requirements_pi.txt pi@<raspberry-ip>:~/

scp start_solar_mining_pi.sh pi@<raspberry-ip>:~/```

scp install_autostart.sh pi@<raspberry-ip>:~/

scp requirements_pi.txt pi@<raspberry-ip>:~/### 2. Setup ausführen

```

```bash

### 2. Run Setup# SSH zum Raspberry Pi

ssh pi@<raspberry-ip>

```bash

# SSH to Raspberry Pi# Setup-Script ausführbar machen

ssh pi@<raspberry-ip>chmod +x setup_raspberry.sh



# Make setup script executable# Setup starten (installiert alles automatisch)

chmod +x setup_raspberry.sh./setup_raspberry.sh

```

# Run setup (installs everything automatically)

./setup_raspberry.shDas Script installiert automatisch:

```- Python Virtual Environment

- Alle benötigten Pakete

The script automatically installs:- Erstellt `.env` Konfigurationsdatei

- Python virtual environment- Erstellt `logs/` Verzeichnis

- All required packages

- Creates `.env` configuration file### 3. Konfiguration bearbeiten

- Creates `logs/` directory

```bash

### 3. Edit Configurationcd ~/solar-mining

nano .env

```bash```

cd ~/solar-mining

nano .env**Wichtige Einstellungen:**

```

```bash

**Important Settings:**# Inverter

INVERTER_HOST=192.168.18.206

```bashINVERTER_PORT=6607

# Language (Supported: en, de)

LANGUAGE=en# E-Mail (WICHTIG!)

EMAIL_ENABLED=true

# InverterEMAIL_FROM=deine-email@gmail.com

INVERTER_HOST=192.168.18.206EMAIL_TO=empfaenger@email.com

INVERTER_PORT=6607EMAIL_USERNAME=deine-email@gmail.com

EMAIL_PASSWORD=dein-app-passwort

# Email (REQUIRED for notifications!)

EMAIL_ENABLED=true# Gmail App-Passwort erstellen:

EMAIL_FROM=your-email@gmail.com# https://myaccount.google.com/apppasswords

EMAIL_TO=recipient@email.com

EMAIL_USERNAME=your-email@gmail.com# Wetter (Los Nietos, Spanien)

EMAIL_PASSWORD=your-app-passwordWEATHER_LATITUDE=37.6931

WEATHER_LONGITUDE=-0.8481

# Create Gmail App Password:```

# https://myaccount.google.com/apppasswords

### 4. Test-Start

# Weather (Los Nietos, Spain - adjust to your location)

WEATHER_LATITUDE=37.6931```bash

WEATHER_LONGITUDE=-0.8481cd ~/solar-mining

```./start_solar_mining_pi.sh

```

### 4. Test Run

Prüfe die Ausgabe - sollte so aussehen:

```bash```

cd ~/solar-mining==================================================

./start_solar_mining_pi.sh  Solar Monitoring System - Raspberry Pi

```==================================================

Inverter: 192.168.18.206:6607

Check the output - should look like:E-Mail: Aktiviert

```Wetter: Aktiviert

====================================================================================================

  Solar Monitoring System - Raspberry Pi✓ Inverter verbunden

==================================================🌤️  Hole initiale Wetterdaten...

Inverter: 192.168.18.206:6607   ✓ Temperatur: 23.1°C

Email: Enabled[15:30:00] Solar: 2500W | Grid:  1200W | Verbrauch:  800W | Temp: 23.1°C

Weather: Enabled```

==================================================

✓ Inverter connected### 5. Autostart einrichten

🌤️  Fetching initial weather data...

   ✓ Temperature: 23.1°C```bash

[15:30:00] Solar: 2500W | Grid:  1200W | Consumption:  800W | Temp: 23.1°C# Installiere als systemd Service

```sudo ./install_autostart.sh

```

### 5. Setup Autostart

Das System startet jetzt **automatisch beim Boot**!

```bash

# Install as systemd service## 🔧 Verwaltung

sudo ./install_autostart.sh

```### Service-Befehle



The system now starts **automatically on boot**!```bash

# Status anzeigen

## 🔧 Managementsudo systemctl status solar-mining



### Service Commands# Manuell starten

sudo systemctl start solar-mining

```bash

# Show status# Stoppen

sudo systemctl status solar-miningsudo systemctl stop solar-mining



# Start manually# Neustarten

sudo systemctl start solar-miningsudo systemctl restart solar-mining



# Stop# Autostart deaktivieren

sudo systemctl stop solar-miningsudo systemctl disable solar-mining



# Restart# Autostart aktivieren

sudo systemctl restart solar-miningsudo systemctl enable solar-mining

```

# Disable autostart

sudo systemctl disable solar-mining### Logs anzeigen



# Enable autostart```bash

sudo systemctl enable solar-mining# Live-Logs vom Service

```journalctl -u solar-mining -f



### View Logs# System-Log

tail -f ~/solar-mining/logs/system.log

```bash

# Live service logs# Error-Log

journalctl -u solar-mining -ftail -f ~/solar-mining/logs/errors.log



# System log# CSV-Daten

tail -f ~/solar-mining/logs/system.logtail ~/solar-mining/logs/solar_data.csv

```

# Error log

tail -f ~/solar-mining/logs/errors.log## 📧 E-Mail Konfiguration



# CSV data### Gmail

tail ~/solar-mining/logs/solar_data.csv

```1. **2-Faktor-Authentifizierung aktivieren**

   - https://myaccount.google.com/security

## 📧 Email Configuration

2. **App-Passwort erstellen**

### Gmail   - https://myaccount.google.com/apppasswords

   - App: "Mail"

1. **Enable 2-Factor Authentication**   - Gerät: "Raspberry Pi"

   - https://myaccount.google.com/security   - Generiertes Passwort in `.env` eintragen



2. **Create App Password**3. **In .env:**

   - https://myaccount.google.com/apppasswords   ```bash

   - App: "Mail"   EMAIL_SMTP_SERVER=smtp.gmail.com

   - Device: "Raspberry Pi"   EMAIL_SMTP_PORT=587

   - Enter generated password in `.env`   EMAIL_FROM=deine-email@gmail.com

   EMAIL_PASSWORD=aaaa bbbb cccc dddd  # App-Passwort

3. **In .env:**   ```

   ```bash

   EMAIL_SMTP_SERVER=smtp.gmail.com### Andere E-Mail-Anbieter

   EMAIL_SMTP_PORT=587

   EMAIL_FROM=your-email@gmail.com**Outlook/Hotmail:**

   EMAIL_PASSWORD=aaaa bbbb cccc dddd  # App password```bash

   ```EMAIL_SMTP_SERVER=smtp-mail.outlook.com

EMAIL_SMTP_PORT=587

### Other Email Providers```



**Outlook/Hotmail:****Yahoo:**

```bash```bash

EMAIL_SMTP_SERVER=smtp-mail.outlook.comEMAIL_SMTP_SERVER=smtp.mail.yahoo.com

EMAIL_SMTP_PORT=587EMAIL_SMTP_PORT=587

``````



**Yahoo:****Eigener SMTP Server:**

```bash```bash

EMAIL_SMTP_SERVER=smtp.mail.yahoo.comEMAIL_SMTP_SERVER=mail.deine-domain.de

EMAIL_SMTP_PORT=587EMAIL_SMTP_PORT=587

```EMAIL_SMTP_USE_TLS=true

```

**Custom SMTP Server:**

```bash## ⚙️ Erweiterte Konfiguration

EMAIL_SMTP_SERVER=mail.your-domain.com

EMAIL_SMTP_PORT=587### Check-Intervalle

EMAIL_SMTP_USE_TLS=true

``````bash

# Daten-Logging

## ⚙️ Advanced ConfigurationCHECK_INTERVAL_SEC=30  # Alle 30 Sekunden



### Check Intervals# Alarm-Prüfung

ALARM_CHECK_INTERVAL_SEC=5  # Alle 5 Sekunden

```bash

# Data logging# Wetter-Update

CHECK_INTERVAL_SEC=30  # Every 30 secondsWEATHER_UPDATE_INTERVAL_SEC=600  # Alle 10 Minuten

```

# Alarm check

ALARM_CHECK_INTERVAL_SEC=5  # Every 5 seconds### E-Mail Optionen



# Weather update```bash

WEATHER_UPDATE_INTERVAL_SEC=300  # Every 5 minutes# Bei Alarmen

```EMAIL_SEND_ON_ALARM=true



### Email Notifications# Bei kritischen Fehlern

EMAIL_SEND_ON_CRITICAL_ERROR=true

```bash

# Send email on alarms# Tägliche Zusammenfassung

EMAIL_ON_ALARM=trueEMAIL_SEND_DAILY_SUMMARY=true

EMAIL_DAILY_SUMMARY_TIME=18:00  # Um 18:00 Uhr

# Daily summary at specific time```

EMAIL_DAILY_SUMMARY=true

EMAIL_DAILY_SUMMARY_TIME=18:00## 📊 CSV-Daten



# Email on critical errorsDie Daten werden in `logs/solar_data.csv` gespeichert:

EMAIL_ON_ERROR=true

``````csv

timestamp,solar_production_w,grid_power_w,house_consumption_w,...

### Weather API2025-10-17T15:30:00,2500,1200,800,...

```

```bash

# Enable/disable**Spalten:**

WEATHER_ENABLED=true- Timestamp & Unix-Timestamp

- Solar-Produktion, Grid-Power, Verbrauch

# Your location (find at: https://www.openstreetmap.org)- PV-Strings (Spannung, Strom, Leistung)

WEATHER_LATITUDE=37.6931- Grid 3-Phasen (Spannung)

WEATHER_LONGITUDE=-0.8481- Inverter (Temperatur, Effizienz, Yields)

- Battery (Power, SoC)

# Update frequency- Wetter (7 Metriken)

WEATHER_UPDATE_INTERVAL_SEC=300- Alarme & Device-Status

```

## 🔍 Troubleshooting

## 📊 Data Logging

### Inverter nicht erreichbar

### CSV Format: `logs/solar_data.csv`

```bash

Logged every 30 seconds:# Ping testen

- **Solar:** Production, grid power, consumptionping 192.168.18.206

- **Strings:** PV1/PV2 voltage, current, power

- **Grid:** 3-phase details (voltage, current, power)# Port prüfen

- **Inverter:** Temperature, efficiency, daily/total yieldnc -zv 192.168.18.206 6607

- **Weather:** Temperature, cloud cover, wind, solar radiation```

- **Battery:** Charge/discharge power, SOC (if available)

### E-Mail funktioniert nicht

### System Logs

```bash

- `logs/system.log` - General system messages# Test-E-Mail senden (Python)

- `logs/errors.log` - Detailed error information with tracebackspython3 << EOF

- `logs/alarms.log` - Inverter alarm historyimport smtplib

from email.mime.text import MIMEText

## 🔧 Troubleshooting

msg = MIMEText('Test')

### Service won't startmsg['Subject'] = 'Test'

msg['From'] = 'deine-email@gmail.com'

```bashmsg['To'] = 'empfaenger@email.com'

# Check service status

sudo systemctl status solar-miningserver = smtplib.SMTP('smtp.gmail.com', 587)

server.starttls()

# View full logsserver.login('deine-email@gmail.com', 'app-passwort')

journalctl -u solar-mining -n 50server.send_message(msg)

server.quit()

# Check if virtual environment existsprint('✓ E-Mail gesendet!')

ls ~/solar-mining/.venvEOF

``````



### Can't connect to inverter### Service startet nicht



```bash```bash

# Test connection# Fehler-Details

ping 192.168.18.206sudo journalctl -u solar-mining -n 50



# Check port (requires netcat)# Python-Fehler testen

nc -zv 192.168.18.206 6607cd ~/solar-mining

source .venv/bin/activate

# Verify IP in .envpython3 solar_mining_pi.py

grep INVERTER_HOST ~/solar-mining/.env```

```

### Virtual Environment Probleme

### Email not working

```bash

```bash# Neu erstellen

# Test email manuallycd ~/solar-mining

cd ~/solar-miningrm -rf .venv

source .venv/bin/activatepython3 -m venv .venv

python3 -c "from solar_core import EmailNotifier; import os; from dotenv import load_dotenv; load_dotenv(); notifier = EmailNotifier(); notifier.send_email('Test Subject', 'Test message')"source .venv/bin/activate

```pip install -r requirements_pi.txt

```

**Common issues:**

- Wrong app password (Gmail requires app-specific password)## 🆕 Updates

- 2FA not enabled (Gmail requirement)

- Wrong SMTP server/port```bash

- Firewall blocking outbound port 587# Neue Version holen (z.B. via scp)

cd ~/solar-mining

### High CPU usagescp user@windows-pc:/path/solar_mining_pi.py .



```bash# Service neustarten

# Check processsudo systemctl restart solar-mining

top -p $(pgrep -f solar_mining_pi)```



# Increase check interval in .env## 🌐 Remote-Zugriff

CHECK_INTERVAL_SEC=60  # Check every 60s instead of 30s

```### VPN (empfohlen)

- WireGuard auf Pi installieren

### Logs too large- Zugriff von überall



```bash### Port-Forwarding

# Rotate logs manually- SSH: Port 22

cd ~/solar-mining/logs- **ACHTUNG:** Nur mit Schlüssel-Auth und fail2ban!

mv solar_data.csv solar_data_$(date +%Y-%m).csv

mv system.log system_$(date +%Y-%m).log### Grafana Dashboard (optional)

```bash

# Service will create new files automatically# Installation

```sudo apt-get install -y grafana



## 🔄 Updates# CSV zu Grafana mit Telegraf

# (siehe separate Anleitung)

```bash```

# Pull latest changes (if using git)

cd ~/solar-mining## 📱 Fernüberwachung

git pull

**E-Mail-Benachrichtigungen** reichen für die meisten Fälle:

# Restart service- ⚠️ Sofort bei Alarmen

sudo systemctl restart solar-mining- 🚨 Bei kritischen Fehlern  

```- 📊 Tägliche Zusammenfassung



## 🚀 Performance**Erweiterte Optionen:**

- Telegram Bot (TODO)

**Tested on:**- MQTT zu Home Assistant (TODO)

- Raspberry Pi 4B (4GB)- REST API für Mobile App (TODO)

- Raspberry Pi 3B+

## 🔒 Sicherheit

**Resource Usage:**

- CPU: ~5% average```bash

- RAM: ~50 MB# SSH Key-Auth aktivieren

- Disk: ~1 MB/day (CSV logs)ssh-keygen -t ed25519

ssh-copy-id pi@raspberry-ip

## 📚 Related Documentation

# Passwort-Login deaktivieren

- **[README.md](README.md)** - Main project documentationsudo nano /etc/ssh/sshd_config

- **[MULTILANG_GUIDE.md](MULTILANG_GUIDE.md)** - Multilingual implementation# PasswordAuthentication no

- **[QUICKSTART_PI.md](QUICKSTART_PI.md)** - Quick setup guide

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment instructions# Firewall

sudo apt-get install ufw

## 🆘 Supportsudo ufw allow 22/tcp

sudo ufw enable

**Check logs first:**

```bash# fail2ban (SSH-Schutz)

journalctl -u solar-mining -n 100sudo apt-get install fail2ban

tail -50 ~/solar-mining/logs/errors.log```

```

## 💾 Backup

**Test individual components:**

```bash```bash

cd ~/solar-mining# CSV-Daten sichern (täglich via cron)

source .venv/bin/activatecrontab -e



# Test inverter connection# Füge hinzu:

python3 -c "from solar_core import InverterConnection; conn = InverterConnection('192.168.18.206'); print(conn.read_solar_production())"0 2 * * * rsync -a ~/solar-mining/logs/*.csv backup-server:/backups/solar/

```

# Test weather API

python3 -c "from solar_core import WeatherAPI; import os; api = WeatherAPI(float(os.getenv('WEATHER_LATITUDE')), float(os.getenv('WEATHER_LONGITUDE'))); print(api.get_weather())"## 📈 Performance

```

**Raspberry Pi 3/4:**

## License- CPU: <5% im Durchschnitt

- RAM: ~50 MB

Private use. No warranty.- Disk: ~1 MB pro Tag (CSV)


**Empfohlen:**
- Raspberry Pi 3B+ oder neuer
- 16 GB SD-Karte (Minimum)
- Stabile Stromversorgung
- Kabelgebundenes Ethernet

## 🆘 Support

Bei Problemen:
1. Prüfe `logs/errors.log`
2. Prüfe `journalctl -u solar-mining`
3. Teste manuell: `./start_solar_mining_pi.sh`

## 📄 Lizenz

Siehe Hauptprojekt.
