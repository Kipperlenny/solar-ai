#!/bin/bash
# Solar Mining System - Raspberry Pi Setup Script
# Automatische Installation und Konfiguration

set -e  # Bei Fehler abbrechen

echo "================================================"
echo "  Solar Mining System - Raspberry Pi Setup"
echo "================================================"
echo ""

# Farben für Output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Projekt-Verzeichnis
PROJECT_DIR="$HOME/solar-mining"
VENV_DIR="$PROJECT_DIR/.venv"

# Erstelle Projekt-Verzeichnis
echo -e "${GREEN}1. Erstelle Projekt-Verzeichnis...${NC}"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Prüfe ob Python3 installiert ist
echo -e "${GREEN}2. Prüfe Python Installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 nicht gefunden! Installiere Python3...${NC}"
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}   ✓ $PYTHON_VERSION gefunden${NC}"

# Erstelle Virtual Environment (falls nicht vorhanden)
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${GREEN}3. Erstelle Virtual Environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}   ✓ Virtual Environment erstellt${NC}"
else
    echo -e "${YELLOW}3. Virtual Environment existiert bereits${NC}"
fi

# Aktiviere Virtual Environment
echo -e "${GREEN}4. Aktiviere Virtual Environment...${NC}"
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo -e "${GREEN}5. Update pip...${NC}"
pip install --upgrade pip

# Installiere Requirements
echo -e "${GREEN}6. Installiere Python-Pakete...${NC}"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}   ✓ Alle Pakete installiert${NC}"
else
    echo -e "${YELLOW}   ! requirements.txt nicht gefunden, installiere Basis-Pakete...${NC}"
    pip install huawei-solar python-dotenv requests psutil
    echo -e "${GREEN}   ✓ Basis-Pakete installiert${NC}"
fi

# Erstelle .env falls nicht vorhanden
if [ ! -f ".env" ]; then
    echo -e "${GREEN}7. Erstelle .env Konfiguration...${NC}"
    cat > .env << 'EOF'
# Huawei Solar Inverter
INVERTER_HOST=192.168.18.206
INVERTER_PORT=6607
INVERTER_SLAVE_ID=1

# Mining Configuration (nur für Mining, nicht für Pi)
MINING_MIN_POWER_W=200
MINING_START_CONFIRMATIONS=3
MINING_STOP_CONFIRMATIONS=5
MINING_CHECK_INTERVAL_SEC=30
EXCAVATOR_API_HOST=127.0.0.1
EXCAVATOR_API_PORT=38080

# Alarm Configuration
ALARM_CHECK_INTERVAL_SEC=5

# Weather API (Open-Meteo)
WEATHER_ENABLED=true
WEATHER_LATITUDE=37.6931
WEATHER_LONGITUDE=-0.8481
WEATHER_UPDATE_INTERVAL_SEC=600

# Logging
LOG_DIR=logs
CSV_FILENAME=solar_data.csv
ERROR_LOG_FILENAME=errors.log

# Email Benachrichtigungen (Raspberry Pi)
EMAIL_ENABLED=false
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USE_TLS=true
EMAIL_FROM=
EMAIL_TO=
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_SEND_ON_ALARM=true
EMAIL_SEND_ON_CRITICAL_ERROR=true
EMAIL_SEND_DAILY_SUMMARY=false
EMAIL_DAILY_SUMMARY_TIME=18:00
EOF
    echo -e "${GREEN}   ✓ .env erstellt - BITTE KONFIGURIEREN!${NC}"
    echo -e "${YELLOW}   → Bearbeite .env und trage deine Email-Daten ein${NC}"
else
    echo -e "${YELLOW}7. .env existiert bereits${NC}"
fi

# Erstelle logs Verzeichnis
mkdir -p logs

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Setup abgeschlossen!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "${YELLOW}Nächste Schritte:${NC}"
echo -e "1. Bearbeite die .env Datei:"
echo -e "   ${GREEN}nano $PROJECT_DIR/.env${NC}"
echo -e ""
echo -e "2. Kopiere solar_mining_api.py in das Verzeichnis:"
echo -e "   ${GREEN}$PROJECT_DIR/${NC}"
echo -e ""
echo -e "3. Teste das Script:"
echo -e "   ${GREEN}$PROJECT_DIR/start_solar_mining_pi.sh${NC}"
echo -e ""
echo -e "4. Richte Autostart ein:"
echo -e "   ${GREEN}$PROJECT_DIR/install_autostart.sh${NC}"
echo ""
