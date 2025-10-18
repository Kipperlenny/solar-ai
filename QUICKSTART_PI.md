# Quick Start Guide - Raspberry Pi# 🚀 Raspberry Pi - Schnellstart



Get your Solar Monitoring System running in 5 minutes!## Schritt-für-Schritt Installation



## 🚀 Prerequisites### 1️⃣ Dateien kopieren (von Windows)



- Raspberry Pi (3B+ or newer recommended)```powershell

- Raspberry Pi OS installed# PowerShell auf Windows:

- Network connectionscp setup_raspberry.sh pi@192.168.x.x:~/

- Huawei Solar Inverter on same networkscp solar_mining_pi.py pi@192.168.x.x:~/

scp start_solar_mining_pi.sh pi@192.168.x.x:~/

## ⚡ Installation (One Command!)scp install_autostart.sh pi@192.168.x.x:~/

scp requirements_pi.txt pi@192.168.x.x:~/

```bash```

# Download and run automated setup

curl -sSL https://raw.githubusercontent.com/Kipperlenny/solar-ai/main/setup_raspberry.sh | bash### 2️⃣ SSH zum Raspberry Pi

```

```bash

Or manual method:ssh pi@192.168.x.x

```

### 1️⃣ Copy Files

### 3️⃣ Setup ausführen

```bash

# From your PC to Raspberry Pi```bash

scp -r solar_mining_pi.py solar_core.py translations.py requirements_pi.txt setup_raspberry.sh pi@<raspberry-ip>:~/chmod +x setup_raspberry.sh

```./setup_raspberry.sh

```

### 2️⃣ SSH to Pi

### 4️⃣ E-Mail konfigurieren

```bash

ssh pi@<raspberry-ip>```bash

```cd ~/solar-mining

nano .env

### 3️⃣ Run Setup```



```bash**Mindestens ändern:**

chmod +x setup_raspberry.sh```bash

./setup_raspberry.shEMAIL_ENABLED=true

```EMAIL_FROM=deine-email@gmail.com

EMAIL_TO=empfaenger@email.com

This installs everything automatically! ✨EMAIL_PASSWORD=dein-gmail-app-passwort

```

### 4️⃣ Configure

**Gmail App-Passwort erstellen:**

```bashhttps://myaccount.google.com/apppasswords

cd ~/solar-mining

nano .env### 5️⃣ Testen

```

```bash

**Minimal configuration:**./start_solar_mining_pi.sh

```

```bash

# Language**Erwartete Ausgabe:**

LANGUAGE=en```

✓ Inverter verbunden

# Your inverter IP (find in Huawei FusionSolar app)✓ Temperatur: 23.1°C

INVERTER_HOST=192.168.1.XXX[15:30:00] Solar: 2500W | Grid: 1200W | ...

```

# Email for notifications

EMAIL_ENABLED=true### 6️⃣ Autostart einrichten

EMAIL_FROM=your-email@gmail.com

EMAIL_TO=your-email@gmail.com```bash

EMAIL_PASSWORD=your-app-passwordsudo ./install_autostart.sh

``````



**Create Gmail App Password:**### ✅ Fertig!

1. Go to https://myaccount.google.com/apppasswords

2. Select "Mail" → "Raspberry Pi"Das System läuft jetzt und startet automatisch beim Boot.

3. Copy generated password to .env

## 📧 E-Mail Test

### 5️⃣ Test Run

```bash

```bashcd ~/solar-mining

./start_solar_mining_pi.shsource .venv/bin/activate

```python3 -c "

from solar_mining_pi import EmailNotifier

Expected output:email = EmailNotifier()

```email.send_email('Test', 'Das ist ein Test!')

=================================================="

  Solar Monitoring System - Raspberry Pi```

==================================================

Inverter: 192.168.1.206:6607## 🔍 Status prüfen

Email: Enabled

Weather: Enabled```bash

==================================================# Service-Status

✓ Inverter connectedsudo systemctl status solar-mining

[15:30:00] Solar: 2500W | Grid: 1200W | Consumption: 800W

```# Live-Logs

journalctl -u solar-mining -f

Press `Ctrl+C` to stop.

# CSV-Daten

### 6️⃣ Enable Autostarttail -f ~/solar-mining/logs/solar_data.csv

```

```bash

sudo ./install_autostart.sh## ⚠️ Bei Problemen

```

```bash

Done! Your system now runs 24/7 and survives reboots! 🎉# Logs prüfen

tail -50 ~/solar-mining/logs/errors.log

## 📊 Check Status

# Manuell starten (zeigt Fehler)

```bashcd ~/solar-mining

# Service status./start_solar_mining_pi.sh

sudo systemctl status solar-mining

# Service neu starten

# Live logssudo systemctl restart solar-mining

journalctl -u solar-mining -f```



# Data file## 📱 Alarm-Test

tail ~/solar-mining/logs/solar_data.csv

```Ziehe kurz den Netzstecker vom Inverter → Du solltest eine E-Mail erhalten!



## 🔧 Manage Service---



```bash**Vollständige Dokumentation:** README_RASPBERRY_PI.md

# Stop
sudo systemctl stop solar-mining

# Start
sudo systemctl start solar-mining

# Restart (after config changes)
sudo systemctl restart solar-mining
```

## 📧 Test Email

```bash
cd ~/solar-mining
source .venv/bin/activate
python3 -c "from solar_core import EmailNotifier; notifier = EmailNotifier(); notifier.send_email('Test', 'Hello from Pi!')"
```

## ❓ Troubleshooting

### "Can't connect to inverter"
- Check inverter IP: `ping 192.168.1.XXX`
- Verify IP in `.env` matches your inverter
- Ensure inverter is on same network as Pi

### "Email not working"
- Gmail requires app-specific password (not your regular password)
- Enable 2FA first: https://myaccount.google.com/security
- Create app password: https://myaccount.google.com/apppasswords

### "Service fails to start"
```bash
# View error details
journalctl -u solar-mining -n 50 --no-pager

# Check if .env exists
ls ~/solar-mining/.env

# Verify Python packages
source ~/solar-mining/.venv/bin/activate
pip list
```

## 🎯 What's Next?

- **View detailed guide:** [README_RASPBERRY_PI.md](README_RASPBERRY_PI.md)
- **Customize settings:** See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Analyze data:** Use `analyze_data.py` on CSV logs
- **Add more features:** Check [MULTILANG_GUIDE.md](MULTILANG_GUIDE.md)

## 🌍 Language Settings

Change language to German:
```bash
nano ~/solar-mining/.env
# Change: LANGUAGE=de
sudo systemctl restart solar-mining
```

## 📈 Next Steps

1. Let it run for 24 hours
2. Check logs: `tail ~/solar-mining/logs/solar_data.csv`
3. Import CSV to Excel/Google Sheets for analysis
4. Set up daily email summary in `.env`

Enjoy your automated solar monitoring! ☀️
