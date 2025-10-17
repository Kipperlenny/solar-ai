# Solar Mining Controller

Automatisches Crypto-Mining mit Solar-Überschuss. Startet Mining nur wenn genug Solarstrom verfügbar ist und pausiert automatisch bei GPU-Nutzung durch andere Programme.

## Features

- ⚡ **Solar-gesteuertes Mining** - Startet/stoppt basierend auf Einspeisung
- 🎮 **GPU-Monitoring** - Pausiert für Games/Stable Diffusion automatisch
- 🔄 **Auto-Restart** - Excavator wird bei Problemen neu gestartet
- 💰 **Earnings Tracking** - Zeigt aktuelle BTC-Verdienste
- 🌦️ **Wetter-Integration** - Cloud-Cover, Temperatur, Solar-Strahlung (Open-Meteo API)
- 📊 **Umfassendes Logging** - CSV-Daten für Auswertungen + Error-Logs

## Voraussetzungen

- Python 3.10+
- Huawei Solar Inverter (SUN2000 Serie) im Netzwerk
- NiceHash Excavator installiert
- NVIDIA GPU (1070 Ti getestet)

## Installation

```powershell
# Virtual Environment aktivieren
.venv\Scripts\Activate.ps1

# Pakete installieren
pip install huawei-solar GPUtil psutil requests python-dotenv
```

## Konfiguration

**Wichtig:** Konfiguration erfolgt über `.env`-Datei (nicht im Code!)

```powershell
# 1. .env.example zu .env kopieren
cp .env.example .env

# 2. .env mit eigenen Werten anpassen
notepad .env
```

**Wichtige Einstellungen in `.env`:**

```bash
# Excavator Pfad
EXCAVATOR_PATH=H:\miner\excavator.exe

# Inverter IP
INVERTER_HOST=192.168.18.206
INVERTER_PORT=6607

# NiceHash Wallet (WICHTIG!)
NICEHASH_WALLET=DEINE_WALLET.worker_name

# GPS-Koordinaten für Wetter (anpassen!)
WEATHER_LATITUDE=37.6931
WEATHER_LONGITUDE=-0.8481

# Power-Schwellwerte (optional anpassen)
MIN_POWER_TO_START=200
MIN_POWER_TO_KEEP=150
CHECK_INTERVAL=30
ALARM_CHECK_INTERVAL=5

# GPU-Monitoring (optional deaktivieren)
GPU_CHECK_ENABLED = True
GPU_USAGE_THRESHOLD = 10   # % - Pause bei GPU-Nutzung

# Wetter-API (Open-Meteo - kostenlos!)
WEATHER_ENABLED = True
WEATHER_LATITUDE = 40.4168    # Deine GPS-Koordinaten
WEATHER_LONGITUDE = -3.7038
```

## Starten

```powershell
# Im Projektordner
python solar_mining_api.py
```

Das Script:
1. Startet Excavator automatisch
2. Verbindet mit Inverter
3. Überwacht Solar-Einspeisung alle 30s
4. Startet Mining bei ≥200W Einspeisung (nach 3x Bestätigung)
5. Stoppt Mining bei <150W (nach 5x Bestätigung)
6. Pausiert bei GPU-Nutzung durch andere Programme

**Beenden:** `Ctrl+C`

## Ausgabe

```
[  5] 10:30:00
      ☀️  Solar:       1250 W
      🏠 Verbrauch:    480 W (Haus)
      📤 Einspeisung:  770 W (ins Netz)
      ✨ Verfügbar:    770 W (für Mining)
      ⛏️  Mining:      🟢 AKTIV
      📈 Hashrate:    27.12 MH/s
      ⏱️  Session:     15m 30s
      💰 Unbezahlt:   0.00012345 BTC
      🌡️  Wetter:      23.5°C, ☁️ 35%, ☀️ 680 W/m²
```

## Logging

### Daten-Log: `logs/solar_data.csv`
Alle 30 Sekunden:
- **Solar:** Produktion, Einspeisung, Verbrauch, String-Daten (PV1/PV2)
- **Grid:** 3-Phasen Details (Spannung, Strom, Leistung)
- **Mining:** Status, Hashrate, GPU-Temperatur, GPU-Auslastung
- **Inverter:** Temperatur, Effizienz, Tages-/Gesamt-Ertrag
- **Wetter:** Temperatur, Cloud-Cover, Wind, Solar-Strahlung (W/m²)
- **Batterie:** Lade-/Entladeleistung, State of Charge (falls vorhanden)

**Verwendung:**
- Excel/Google Sheets
- Graphen erstellen (Solar vs. Cloud-Cover!)
- ML Training (Prognose-Modelle)
- Langzeit-Analysen

### Error-Log: `logs/errors.log`
Detaillierte Fehler-Informationen:
- API-Verbindungsprobleme
- Excavator-Abstürze
- Inverter-Verbindungsfehler
- Komplette Tracebacks

## Tools

### Daten analysieren
```powershell
# Statistiken + Plots (benötigt pandas + matplotlib)
pip install pandas matplotlib
python analyze_data.py
```

Erstellt:
- `logs/solar_mining_analysis.png` - Übersicht (Solar, Mining, Hashrate, GPU)
- `logs/daily_pattern.png` - Tages-Muster (stündliche Durchschnitte)
- `logs/ml_training_data.csv` - Aufbereitet für ML

### Fehler anzeigen
```powershell
python view_errors.py        # Letzte 24h
python view_errors.py 6      # Letzte 6h
```

## GPU-Monitoring

Automatische Pause bei:
- 🎮 **Gaming**: Rocket League, CS2, Valorant, etc.
- 🎨 **Stable Diffusion**: Erkennt Python-Prozesse mit SD-Keywords
- 🎬 **Video/3D**: Blender, Premiere, After Effects, etc.

**Eigene Programme hinzufügen:**
```python
# In solar_mining_api.py, Zeile ~175
gpu_intensive_processes = [
    'RocketLeague.exe',
    'MeinGame.exe',  # <-- Hier hinzufügen
]
```

**Feature deaktivieren:**
```python
GPU_CHECK_ENABLED = False
```

## Windows Service (24/7)

Mit NSSM als Service installieren:

```powershell
# NSSM herunterladen: nssm.cc
nssm install SolarMining "C:\Users\Lennart\test\.venv\Scripts\python.exe"
nssm set SolarMining AppParameters "C:\Users\Lennart\test\solar_mining_api.py"
nssm set SolarMining AppDirectory "C:\Users\Lennart\test"
nssm set SolarMining Start SERVICE_AUTO_START

# Service starten
nssm start SolarMining
```

## Troubleshooting

### "Excavator antwortet nicht"
- Excavator wird automatisch neu gestartet
- Check: `logs/errors.log`
- Manuell: Excavator schließen und Script neu starten

### "Inverter verbunden" Fehler
- IP korrekt? `INVERTER_HOST = "192.168.18.206"`
- Inverter erreichbar? `ping 192.168.18.206`
- Port offen? Firewall prüfen

### Mining startet nicht
- Genug Einspeisung? Braucht ≥200W für 3x30s
- GPU frei? Andere Programme aktiv?
- Check Console-Ausgabe + `logs/errors.log`

### CSV-Datei zu groß
```powershell
# Alte Daten archivieren
Move-Item logs\solar_data.csv logs\solar_data_$(Get-Date -Format 'yyyy-MM').csv
# Neuer CSV-Header wird automatisch erstellt
```

## Technische Details

**Hardware:**
- Huawei SUN2000-6KTL-L1 Inverter
- NVIDIA GeForce GTX 1070 Ti (~180W, ~27 MH/s)

**Software:**
- NiceHash Excavator v1.9.x
- Modbus TCP (Port 6607)
- Excavator API (TCP Port 3456)

**Algorithmus:** DaggerHashimoto (Ethereum)

**Hysterese:**
- 3x Bestätigungen (90s) zum Starten
- 5x Bestätigungen (150s) zum Stoppen
- Vermeidet ständiges An/Aus bei schwankender Sonne

## Dateien

```
test/
├── solar_mining_api.py    # Haupt-Script
├── analyze_data.py        # Daten-Analyse Tool
├── view_errors.py         # Error-Log Viewer
├── README.md              # Diese Datei
├── logs/
│   ├── solar_data.csv     # Daten-Log
│   └── errors.log         # Error-Log
└── .venv/                 # Python Virtual Environment
```

## Lizenz

Privat-Nutzung. Keine Garantie.
